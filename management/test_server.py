import json
from pathlib import Path
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

from server import Controller, group_media, handler, media_route

TEST_ROOT = Path(__file__).resolve().parent.parent / "artifacts/management-tests"
TEST_ROOT.mkdir(parents=True, exist_ok=True)
tempfile.tempdir = str(TEST_ROOT)


class FakeGateway:
    def __init__(self):
        self.calls = []

    def call(self, method, **params):
        self.calls.append((method, params))
        if method == "getMediaList":
            return []
        if method == "addStreamProxy":
            return {"key": "__defaultVhost__/mgui/" + params["stream"]}
        return {"flag": True}


class ConsoleTests(unittest.TestCase):
    def test_media_route_boundaries(self):
        identifier = "a" * 32
        session = "b" * 32
        prefix = f"/media/{identifier}/{session}/"
        tasks = {identifier: {"app": "mgui", "stream": "ui_" + identifier}}
        self.assertEqual(media_route(prefix + "2026-11-14/17-30-00_0.ts", tasks)[0],
                         "/mgui/ui_" + identifier + "/2026-11-14/17-30-00_0.ts")
        for suffix in ("../config.ini", "%2e%2e/x.ts", "//other/x.ts", "hls.m3u8?url=http://evil", "secret.ini"):
            with self.assertRaises(ValueError):
                media_route(prefix + suffix, tasks)
        with self.assertRaises(ValueError):
            media_route(prefix + "hls.m3u8", {})

    def test_no_double_count_and_missing_value(self):
        base = dict(vhost="v", app="a", stream="s", totalReaderCount=3)
        rows = group_media([dict(base, schema="rtsp"), dict(base, schema="rtmp")])
        self.assertEqual(rows[0]["totalReaders"], 3)
        self.assertIsNone(group_media([dict(app="a", stream="s")])[0]["totalReaders"])

    def test_ownership_persistence_and_url_not_stored(self):
        with tempfile.TemporaryDirectory() as path:
            gateway = FakeGateway()
            controller = Controller(gateway, Path(path))
            task = controller.add("demo", "rtsp://user:private-password@127.0.0.1/live/test")
            self.assertNotIn("private-password", controller.path.read_text())
            restored = Controller(gateway, Path(path))
            with self.assertRaises(ValueError):
                restored.delete("not-owned")
            restored.delete(task["id"])
            self.assertEqual(restored.tasks, {})

    def test_failed_add_keeps_cleanup_ownership(self):
        class Failing(FakeGateway):
            def call(self, method, **params):
                if method == "addStreamProxy":
                    raise RuntimeError("timeout")
                return super().call(method, **params)
        with tempfile.TemporaryDirectory() as path:
            controller = Controller(Failing(), Path(path))
            task = controller.add("demo", "rtsp://127.0.0.1/live/test")
            self.assertEqual(task["state"], "timeout")
            controller.delete(task["id"])

    def test_http_origin_and_token(self):
        with tempfile.TemporaryDirectory() as path:
            controller = Controller(FakeGateway(), Path(path))
            with ThreadingHTTPServer(("127.0.0.1", 0), handler(controller, 0)) as http:
                port = http.server_port
                http.RequestHandlerClass = handler(controller, port)
                thread = threading.Thread(target=http.serve_forever, daemon=True)
                thread.start()
                try:
                    base = f"http://127.0.0.1:{port}"
                    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
                    with opener.open(base + "/api/state") as response:
                        state = json.load(response)
                    body = json.dumps(dict(name="demo", url="rtsp://127.0.0.1/test")).encode()
                    bad = urllib.request.Request(base + "/api/tasks", data=body)
                    with self.assertRaises(urllib.error.HTTPError) as caught:
                        opener.open(bad)
                    self.assertEqual(caught.exception.code, 403)
                    good = urllib.request.Request(base + "/api/tasks", data=body,
                               headers={"Origin": base, "X-MG-Token": state["token"]})
                    with opener.open(good) as response:
                        self.assertEqual(json.load(response)["task"]["state"], "拉流请求成功")
                    with opener.open(base + "/") as response:
                        self.assertIn(b"MediaGateway", response.read())
                finally:
                    http.shutdown()
                    thread.join(timeout=3)


if __name__ == "__main__":
    unittest.main(verbosity=2)
