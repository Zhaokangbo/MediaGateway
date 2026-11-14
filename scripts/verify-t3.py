#!/usr/bin/env python3
"""Bounded RTSP ingest/pull/decode acceptance; requires running T2 instances."""
import argparse
from datetime import datetime, timezone
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.parse
import urllib.request
import urllib.error
import uuid

from instances import ROOT, config_for, owned


def decoded_counts(text):
    counts = {0: 0, 1: 0}
    for line in text.splitlines():
        if not line.strip() or line.startswith("#"):
            continue
        fields = line.split(",")
        if len(fields) == 6 and int(fields[4]) > 0:
            index = int(fields[0])
            if index in counts:
                counts[index] += 1
    return counts


def run():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", choices=("t3", "t4"), default="t3")
    args = parser.parse_args()
    if not sys.platform.startswith("linux"):
        parser.error("Run on Ubuntu with the T2 instances started")
    if not shutil.which("ffmpeg"):
        parser.error("ffmpeg is required")
    os.umask(0o077)
    tag = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:12]
    evidence = ROOT / "artifacts" / args.stage / tag
    evidence.mkdir(parents=True)
    configs = {}
    publisher = None
    proxy_attempted = False
    proxy_key = None
    stream = args.stage + "_" + uuid.uuid4().hex
    params = {"vhost": "__defaultVhost__", "app": "mgtest", "stream": stream}
    summary = {"stage": args.stage.upper(), "stream": stream, "status": "FAIL", "cleanup_errors": [], "protocols": {}}
    # FFmpeg HTTP inputs must stay local even when the shell uses a proxy.
    media_env = {k: v for k, v in os.environ.items() if k.lower() not in
                 ("http_proxy", "https_proxy", "all_proxy")}
    media_env.update(no_proxy="127.0.0.1,localhost", NO_PROXY="127.0.0.1,localhost")

    def save(name, value):
        (evidence / name).write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")

    def log(message):
        print(message, flush=True)
        with (evidence / "run.log").open("a", encoding="utf-8") as out:
            out.write(message + "\n")

    def api(instance, method, values=None, filename=None):
        cfg = configs[instance]
        payload = dict(values or {}, secret=cfg["api"]["secret"])
        req = urllib.request.Request(
            f"http://127.0.0.1:{cfg['http']['port']}/index/api/{method}",
            data=urllib.parse.urlencode(payload).encode())
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open(req, timeout=15) as response:
            result = json.load(response)
        if filename:
            save(filename, result)
        if result.get("code") != 0:
            raise RuntimeError(f"{instance} {method} code={result.get('code')}; see API evidence")
        return result

    def wait_media(instance):
        deadline = time.monotonic() + 25
        while time.monotonic() < deadline:
            if publisher.poll() is not None:
                raise RuntimeError("Publisher exited; inspect publisher.log")
            result = api(instance, "getMediaList", dict(params, schema="rtsp"), instance + "-media.json")
            rows = result.get("data") or []
            if any(row.get("stream") == stream and row.get("app") == "mgtest"
                   and row.get("schema") == "rtsp" for row in rows):
                log(f"PASS: {instance} RTSP registered")
                return
            time.sleep(0.5)
        raise RuntimeError(instance + " RTSP registration timed out")

    def wait_hls(url):
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        deadline = time.monotonic() + 45
        while time.monotonic() < deadline:
            if publisher.poll() is not None:
                raise RuntimeError("Publisher exited while waiting for HLS")
            try:
                with opener.open(url, timeout=3) as response:
                    playlist = response.read().decode("utf-8")
                (evidence / "hls-playlist.m3u8").write_text(playlist, encoding="utf-8")
                if playlist.startswith("#EXTM3U") and "#EXTINF:" in playlist:
                    return
            except urllib.error.HTTPError as ex:
                if ex.code != 404:
                    raise
            except (TimeoutError, urllib.error.URLError):
                pass
            time.sleep(0.5)
        raise RuntimeError("HLS playlist with media segments not ready within 45 seconds")

    log("Evidence: " + str(evidence))
    try:
        for name in ("source", "gateway"):
            folder, path, cfg, binary = config_for(name)
            state = json.loads((folder / "process.json").read_text())
            if not owned(state, binary, path):
                raise RuntimeError(name + " is not a managed running instance; run start.sh")
            configs[name] = cfg
            api(name, "getMediaList", params, name + "-before.json")
        version = subprocess.run(["ffmpeg", "-version"], capture_output=True, text=True, check=True, timeout=10)
        (evidence / "ffmpeg-version.txt").write_text(version.stdout, encoding="utf-8")
        source_url = f"rtsp://127.0.0.1:18554/mgtest/{stream}"
        gateway_url = f"rtsp://127.0.0.1:8554/mgtest/{stream}"
        command = ["ffmpeg", "-hide_banner", "-nostdin", "-loglevel", "info",
                   "-re", "-f", "lavfi", "-i", "testsrc2=size=640x360:rate=25",
                   "-re", "-f", "lavfi", "-i", "sine=frequency=1000:sample_rate=48000",
                   "-map", "0:v:0", "-map", "1:a:0", "-c:v", "libx264",
                   "-preset", "ultrafast", "-tune", "zerolatency", "-pix_fmt", "yuv420p",
                   "-threads", "2", "-g", "50", "-keyint_min", "50", "-sc_threshold", "0",
                   "-c:a", "aac", "-b:a", "64k", "-ac", "1",
                   "-f", "rtsp", "-rtsp_transport", "tcp", source_url]
        save("publisher-command.json", command)
        with (evidence / "publisher.log").open("wb") as out:
            publisher = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=out, stderr=out, env=media_env)
        wait_media("source")
        proxy_attempted = True
        proxy_key = "__defaultVhost__/mgtest/" + stream
        result = api("gateway", "addStreamProxy", dict(params, url=source_url,
                     rtp_type=0, retry_count=0, timeout_sec=10, enable_rtsp=1,
                     enable_rtmp=1, enable_hls=1, enable_mp4=0, auto_close=0), "proxy-add.json")
        proxy_key = result["data"]["key"]
        wait_media("gateway")
        targets = {"rtsp": gateway_url}
        if args.stage == "t4":
            targets.update(rtmp=f"rtmp://127.0.0.1:1935/mgtest/{stream}",
                           http_flv=f"http://127.0.0.1:18080/mgtest/{stream}.live.flv",
                           hls=f"http://127.0.0.1:18080/mgtest/{stream}/hls.m3u8")
        save("playback-urls.json", targets)
        for protocol, url in targets.items():
            prefix = "" if args.stage == "t3" else protocol + "-"
            result = {"status": "FAIL"}
            summary["protocols"][protocol] = result
            try:
                log("Testing: " + protocol)
                if protocol == "hls":
                    wait_hls(url)
                command = ["ffmpeg", "-hide_banner", "-nostdin", "-loglevel", "info", "-xerror"]
                if protocol == "rtsp":
                    command += ["-rtsp_transport", "tcp"]
                command += ["-i", url, "-map", "0:v:0", "-map", "0:a:0", "-t", "5",
                            "-c:v", "rawvideo", "-threads:v", "1", "-c:a", "pcm_s16le",
                            "-f", "framemd5", str(evidence / (prefix + "decoded.framemd5"))]
                save(prefix + "decoder-command.json", command)
                with (evidence / (prefix + "decoder.log")).open("wb") as out:
                    subprocess.run(command, stdout=out, stderr=out, stdin=subprocess.DEVNULL,
                                   check=True, timeout=40, env=media_env)
                counts = decoded_counts((evidence / (prefix + "decoded.framemd5")).read_text())
                if counts[0] < 100 or counts[1] < 100:
                    raise RuntimeError(f"Insufficient decoded output: {counts}")
                if publisher.poll() is not None:
                    raise RuntimeError("Publisher exited during decode")
                result.update(status="PASS", decoded_video_frames=counts[0], decoded_audio_blocks=counts[1])
                if args.stage == "t3":
                    summary.update(decoded_video_frames=counts[0], decoded_audio_blocks=counts[1])
                log(f"PASS: {protocol} decoded video_frames={counts[0]}, audio_blocks={counts[1]}")
            except Exception as ex:
                result["error"] = f"{type(ex).__name__}: {ex}"
                log(f"FAIL: {protocol}: {result['error']}")
            save("summary.json", summary)
        if any(item["status"] != "PASS" for item in summary["protocols"].values()):
            raise RuntimeError("One or more playback protocols failed; inspect per-protocol logs")
        api("gateway", "getMediaList", params, "gateway-all-schemas.json")
        summary["status"] = "PASS"
    except (Exception, KeyboardInterrupt) as ex:
        summary["error"] = f"{type(ex).__name__}: {ex}"
        log("FAIL: " + summary["error"])
    finally:
        if proxy_attempted:
            try:
                api("gateway", "delStreamProxy", {"key": proxy_key}, "proxy-delete.json")
            except Exception as ex:
                summary["cleanup_errors"].append("proxy cleanup: " + str(ex))
        if publisher is not None:
            if publisher.poll() is None:
                publisher.terminate()
                try:
                    publisher.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    publisher.kill()
                    publisher.wait(timeout=5)
            summary["publisher_exit_after_cleanup"] = publisher.returncode
        if proxy_attempted:
            try:
                for name in ("source", "gateway"):
                    for attempt in range(20):
                        rows = api(name, "getMediaList", params, name + "-after.json").get("data") or []
                        if not rows:
                            break
                        time.sleep(0.25)
                    else:
                        raise RuntimeError(name + " test media still registered")
            except Exception as ex:
                summary["cleanup_errors"].append(str(ex))
        if summary["cleanup_errors"]:
            summary["status"] = "FAIL"
        save("summary.json", summary)
        log(summary["status"] + ": " + summary["stage"] + "; details in summary.json")
        log("NOT TESTED: " + ("RTMP/HTTP-FLV/HLS playback, " if args.stage == "t3" else "")
            + "browser playback, viewer counts, reconnection, latency")
    return 0 if summary["status"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(run())
