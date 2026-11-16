#!/usr/bin/env python3
"""Real RTSP/TCP receive-path acceptance with a deliberately tiny PCMA fixture."""
from datetime import datetime, timezone
import json
import socketserver
import struct
import threading
import time
import urllib.parse
import urllib.request
import uuid
from instances import ROOT, config_for


class Fixture(socketserver.StreamRequestHandler):
    def handle(self):
        send_lock = threading.Lock()
        started = False
        self.request.settimeout(20)

        def send(data):
            with send_lock:
                self.request.sendall(data)

        def packets():
            try:
                time.sleep(0.1)
                for seq, timestamp in [(65534, 0), (0, 320), (65535, 160), (65535, 160), (1, 480)]:
                    packet = struct.pack("!BBHII", 0x80, 8, seq, timestamp, 0x12345678) + bytes([0xd5]) * 160
                    send(b"$\x00" + struct.pack("!H", len(packet)) + packet)
                    time.sleep(0.05)
                # Second SSRC must be accepted by upstream's 3-second guard.
                while not self.server.finish.is_set():
                    if self.server.switch_ssrc.wait(0.1):
                        time.sleep(3.3)
                        for seq in (10, 11, 10):
                            packet = struct.pack("!BBHII", 0x80, 8, seq, seq * 160, 0x23456789) + bytes([0xd5]) * 160
                            send(b"$\x00" + struct.pack("!H", len(packet)) + packet)
                            time.sleep(0.05)
                        break
            except OSError:
                pass

        try:
            while not self.server.finish.is_set():
                first = self.rfile.read(1)
                if not first:
                    break
                if first == b"$":
                    frame = self.rfile.read(3)
                    if len(frame) != 3:
                        break
                    self.rfile.read(struct.unpack("!H", frame[1:])[0])
                    continue
                request = (first + self.rfile.readline()).decode("ascii").strip()
                method, url, _ = request.split(" ", 2)
                headers = {}
                while True:
                    line = self.rfile.readline()
                    if line in (b"\r\n", b"\n", b""):
                        break
                    name, value = line.decode("ascii").split(":", 1)
                    headers[name.lower()] = value.strip()
                length = int(headers.get("content-length", "0"))
                if length:
                    self.rfile.read(length)
                body = b""
                extra = "Session: mg-fixture\r\n"
                if method == "OPTIONS":
                    extra += "Public: OPTIONS, DESCRIBE, SETUP, PLAY, GET_PARAMETER, TEARDOWN\r\n"
                elif method == "DESCRIBE":
                    body = ("v=0\r\no=- 1 1 IN IP4 127.0.0.1\r\ns=MG RTP quality test\r\n"
                            "c=IN IP4 127.0.0.1\r\nt=0 0\r\na=control:*\r\n"
                            "m=audio 0 RTP/AVP 8\r\na=rtpmap:8 PCMA/8000/1\r\na=control:trackID=0\r\n").encode()
                    extra += "Content-Type: application/sdp\r\nContent-Base: " + url.rstrip("/") + "/\r\n"
                elif method == "SETUP":
                    extra += "Transport: RTP/AVP/TCP;unicast;interleaved=0-1;ssrc=12345678\r\n"
                response = ("RTSP/1.0 200 OK\r\nCSeq: " + headers.get("cseq", "1") + "\r\n"
                            + extra + "Content-Length: " + str(len(body)) + "\r\n\r\n").encode() + body
                send(response)
                if method == "PLAY" and not started:
                    started = True
                    threading.Thread(target=packets, daemon=True).start()
                if method == "TEARDOWN":
                    break
        except (OSError, ValueError):
            pass


class Server(socketserver.ThreadingTCPServer):
    daemon_threads = True
    allow_reuse_address = True


def main():
    tag = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:8]
    evidence = ROOT / "artifacts/quality-live" / tag
    evidence.mkdir(parents=True)
    _, _, cfg, _ = config_for("gateway")
    stream = "quality_" + uuid.uuid4().hex
    key = "__defaultVhost__/mgtest/" + stream
    summary = {"status": "FAIL", "checks": [], "key": key}
    attempted = False
    counter = 0
    def api(method, **params):
        nonlocal counter
        params["secret"] = cfg["api"]["secret"]
        req = urllib.request.Request(f"http://127.0.0.1:{cfg['http']['port']}/index/api/{method}",
                                     data=urllib.parse.urlencode(params).encode())
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open(req, timeout=15) as response:
            result = json.load(response)
        counter += 1
        (evidence / f"{counter:03d}-{method}.json").write_text(json.dumps(result, indent=2))
        if result.get("code") != 0:
            raise RuntimeError(method + " returned code " + str(result.get("code")))
        return result.get("data")

    def check(name, condition):
        if not condition:
            raise RuntimeError(name)
        summary["checks"].append(name)
        print("PASS: " + name, flush=True)

    def wait_track(ssrc, count):
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            data = api("getProxyRtpQuality", key=key)
            if not data or not data.get("supported"):
                raise RuntimeError("RTSP quality API unsupported")
            for track in data["tracks"]:
                if track["ssrc"] == ssrc and track["received"] >= count:
                    return data, track
            time.sleep(0.1)
        raise RuntimeError("Quality snapshot timed out")

    print("Evidence: " + str(evidence), flush=True)
    with Server(("127.0.0.1", 0), Fixture) as server:
        server.finish = threading.Event()
        server.switch_ssrc = threading.Event()
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            attempted = True
            api("addStreamProxy", vhost="__defaultVhost__", app="mgtest", stream=stream,
                url=f"rtsp://127.0.0.1:{server.server_address[1]}/quality", rtp_type=0,
                retry_count=0, timeout_sec=5, enable_rtsp=1, enable_rtmp=0,
                enable_hls=0, enable_mp4=0, auto_close=0)
            data, first = wait_track(0x12345678, 5)
            expected = dict(received=5, unique=4, reordered=1, duplicates=1, too_old=0,
                            discontinuities=0, highest_extended=65537)
            check("pre-sort counters match injected wrap/reorder/duplicate sequence",
                  all(first[k] == value for k, value in expected.items()))
            check("PCMA clock and transport", first["sample_rate"] == 8000 and data["transport"] == 0)
            server.switch_ssrc.set()
            data2, second = wait_track(0x23456789, 3)
            check("accepted SSRC change starts a new epoch", data2["instance_id"] == data["instance_id"]
                  and second["epoch"] == first["epoch"] + 1)
            check("new SSRC does not inherit counters", second["received"] == 3 and second["unique"] == 2
                  and second["duplicates"] == 1 and second["reordered"] == 0)
            # Recreate proxy: MediaPlayer replaces its delegate, so instance ID changes.
            api("delStreamProxy", key=key)
            server.switch_ssrc.clear()
            api("addStreamProxy", vhost="__defaultVhost__", app="mgtest", stream=stream,
                url=f"rtsp://127.0.0.1:{server.server_address[1]}/quality", rtp_type=0,
                retry_count=0, timeout_sec=5, enable_rtsp=1, enable_rtmp=0,
                enable_hls=0, enable_mp4=0, auto_close=0)
            data3, third = wait_track(0x12345678, 5)
            check("new player instance has fresh receive statistics", data3["instance_id"] != data["instance_id"]
                  and all(third[k] == value for k, value in expected.items()))
            summary["status"] = "PASS"
        except Exception as ex:
            summary["error"] = str(ex)
            print("FAIL: " + str(ex), flush=True)
        finally:
            if attempted:
                try:
                    api("delStreamProxy", key=key)
                except Exception as ex:
                    summary["status"] = "FAIL"
                    summary["cleanup_error"] = str(ex)
            server.finish.set()
            server.shutdown()
            thread.join(timeout=3)
            (evidence / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(summary["status"] + ": live RTSP quality API; NOT TESTED: automatic reconnection, UDP, jitter/loss, performance")
    return int(summary["status"] != "PASS")


if __name__ == "__main__":
    raise SystemExit(main())
