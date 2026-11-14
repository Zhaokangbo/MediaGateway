#!/usr/bin/env python3
"""T2 local-only ZLM instance lifecycle. Linux /proc required."""
import argparse
import configparser
import json
import os
from pathlib import Path
import signal
import socket
import subprocess
import sys
import time
import urllib.parse
import urllib.request
import uuid

ROOT = Path(__file__).resolve().parent.parent
PORTS = {"source": (18554, 18081, 11935), "gateway": (8554, 18080, 1935)}


def settings():
    lock = json.loads((ROOT / "upstream.lock.json").read_text(encoding="utf-8"))
    rev = lock["repositories"]["ZLMediaKit"]["commit"]
    src = ROOT / "upstream/ZLMediaKit"
    binary = src / "release/linux/RelWithDebInfo/MediaServer"
    return src, binary, rev


def config_for(name):
    src, binary, rev = settings()
    folder = ROOT / "runtime" / name
    folder.mkdir(parents=True, exist_ok=True, mode=0o700)
    path = folder / "config.ini"
    if not path.exists():
        cfg = configparser.ConfigParser(interpolation=None)
        cfg.optionxform = str
        with (src / "conf/config.ini").open(encoding="utf-8-sig") as stream:
            cfg.read_file(stream)
        rtsp, http, rtmp = PORTS[name]
        edits = {
            "api": {"secret": uuid.uuid4().hex, "apiDebug": "0"},
            "general": {"listen_ip": "127.0.0.1", "mediaServerId": "MediaGateway-" + name},
            "http": {"port": str(http), "sslport": "0", "rootPath": str(folder / "www"), "dirMenu": "0", "virtualPath": ""},
            "rtsp": {"port": str(rtsp), "sslport": "0"},
            "rtmp": {"port": str(rtmp), "sslport": "0"},
            "shell": {"port": "0"}, "hook": {"enable": "0"},
            "rtp_proxy": {"port": "0"}, "srt": {"port": "0"},
            "rtc": {"port": "0", "tcpPort": "0", "enableTurn": "0"},
            "protocol": {
                "enable_hls": "1" if name == "gateway" else "0",
                "enable_rtsp": "1", "enable_rtmp": "1",
                "enable_mp4": "0", "enable_hls_fmp4": "0",
                "enable_ts": "0", "enable_fmp4": "0",
                "add_mute_audio": "0", "auto_close": "0",
                "hls_save_path": str(folder / "www"),
                "mp4_save_path": str(folder / "www"),
                "hls_demand": "0", "rtsp_demand": "0", "rtmp_demand": "0",
            },
        }
        for section, values in edits.items():
            if not cfg.has_section(section):
                cfg.add_section(section)
            for key, value in values.items():
                cfg.set(section, key, value)
        (folder / "www").mkdir(exist_ok=True)
        with path.open("x", encoding="utf-8") as stream:
            cfg.write(stream, space_around_delimiters=False)
        path.chmod(0o600)
    cfg = configparser.ConfigParser(interpolation=None)
    cfg.optionxform = str
    cfg.read(path, encoding="utf-8")
    # Existing runtime config is never silently rewritten.
    if cfg["general"]["listen_ip"] != "127.0.0.1":
        raise RuntimeError("T2 requires loopback bind; inspect existing runtime config")
    actual = tuple(cfg.getint(section, "port") for section in ("rtsp", "http", "rtmp"))
    if actual != PORTS[name]:
        raise RuntimeError("Existing runtime ports differ from T2 defaults")
    return folder, path, cfg, binary


def proc_info(pid):
    proc = Path("/proc") / str(pid)
    try:
        stat = (proc / "stat").read_text()
        tail = stat.rsplit(")", 1)[1].split()
        if tail[0] == "Z":
            return None
        return {
            "start": tail[19], "exe": str((proc / "exe").resolve(strict=True)),
            "args": (proc / "cmdline").read_bytes().decode().strip("\0").split("\0"),
        }
    except (OSError, ValueError):
        return None


def owned(state, binary, config):
    current = proc_info(state["pid"])
    return bool(current and current["start"] == state["start"]
                and current["exe"] == str(binary.resolve())
                and current["args"] == [str(binary), "-c", str(config),
                                       "--log-dir", str(config.parent / "logs"), "-t", "2"])


def api(cfg):
    # Bypass proxy environment for local health requests.
    body = urllib.parse.urlencode({"secret": cfg["api"]["secret"]}).encode()
    request = urllib.request.Request(
        "http://127.0.0.1:" + cfg["http"]["port"] + "/index/api/getMediaList",
        data=body)
    with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(request, timeout=2) as response:
        result = json.load(response)
    if result.get("code") != 0:
        raise RuntimeError("API returned a nonzero code")
    return len(result.get("data") or [])


def execute(action, name):
    folder, config, cfg, binary = config_for(name)
    statepath = folder / "process.json"
    state = json.loads(statepath.read_text()) if statepath.exists() else None
    active = state is not None and owned(state, binary, config)
    if action == "logs":
        log = folder / "console.log"
        if log.exists():
            for line in log.read_text(errors="replace").splitlines()[-60:]:
                print(line)
        else:
            print(name + ": no console log")
        return
    if action == "status":
        if not active:
            print(name + ": STOPPED (or stale identity)")
            return False
        print(f"{name}: RUNNING pid={state['pid']}, API OK, media_sources={api(cfg)}")
        return True
    if action == "stop":
        if not active:
            print(name + ": no matching managed process; no signal sent")
            return
        os.kill(state["pid"], signal.SIGTERM)
        for _ in range(100):
            if not owned(state, binary, config):
                statepath.unlink(missing_ok=True)
                print(name + ": STOPPED")
                return
            time.sleep(0.1)
        raise RuntimeError("Graceful stop timed out; process retained, no forced kill")
    if active:
        api(cfg)
        print(name + ": already running; no duplicate started")
        return
    if not binary.is_file() or not os.access(binary, os.X_OK):
        raise RuntimeError("Build MediaServer first")
    src, _, rev = settings()
    actual = subprocess.check_output(["git", "-C", str(src), "rev-parse", "HEAD"], text=True).strip()
    if actual != rev:
        raise RuntimeError("Source HEAD does not match lock")
    # Preflight is advisory; actual bind and API readiness remain authoritative.
    for port in PORTS[name]:
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", port))
    (folder / "logs").mkdir(exist_ok=True)
    args = [str(binary), "-c", str(config), "--log-dir", str(folder / "logs"), "-t", "2"]
    with (folder / "console.log").open("ab") as out:
        child = subprocess.Popen(args, cwd=folder, stdout=out, stderr=out,
                                 stdin=subprocess.DEVNULL, start_new_session=True)
    current = None
    for _ in range(50):
        current = proc_info(child.pid)
        if current and current["exe"] == str(binary.resolve()):
            break
        if child.poll() is not None:
            raise RuntimeError("MediaServer exited; inspect console.log")
        time.sleep(0.02)
    if not current or current["exe"] != str(binary.resolve()):
        raise RuntimeError("Could not capture process identity; inspect runtime manually")
    state = {"pid": child.pid, "start": current["start"]}
    statepath.write_text(json.dumps(state) + "\n")
    for _ in range(30):
        if child.poll() is not None:
            raise RuntimeError("MediaServer exited; inspect console.log")
        try:
            count = api(cfg)
            if not owned(state, binary, config):
                raise RuntimeError("Process identity changed")
            print(f"{name}: STARTED pid={child.pid}, API OK, media_sources={count}")
            return
        except (OSError, ValueError, RuntimeError):
            time.sleep(0.3)
    raise RuntimeError("API readiness timed out; process retained for logs/stop")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["start", "stop", "status", "logs"])
    parser.add_argument("instance", choices=["source", "gateway", "all"], default="all", nargs="?")
    args = parser.parse_args()
    if not sys.platform.startswith("linux"):
        parser.error("Linux required")
    import fcntl
    runtime = ROOT / "runtime"
    runtime.mkdir(exist_ok=True, mode=0o700)
    # One lock serializes lifecycle calls, avoiding duplicate starts.
    with (runtime / "control.lock").open("a") as guard:
        fcntl.flock(guard, fcntl.LOCK_EX)
        names = list(PORTS) if args.instance == "all" else [args.instance]
        failed = False
        for name in names:
            try:
                if execute(args.action, name) is False:
                    failed = True
            except Exception as ex:
                print(f"{name}: FAIL ({type(ex).__name__}: {ex}); inspect runtime/{name}/console.log", file=sys.stderr)
                failed = True
        return int(failed)


if __name__ == "__main__":
    sys.exit(main())

