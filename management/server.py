#!/usr/bin/env python3
"""Local development control plane; access remotely through an SSH tunnel."""
import argparse
import configparser
import json
import os
import re
from pathlib import Path
import secrets
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from http.cookies import SimpleCookie
import urllib.error
import urllib.parse
import urllib.request
import uuid

ROOT = Path(__file__).resolve().parent.parent
STATIC = Path(__file__).resolve().parent / "web"


def media_route(path, tasks):
    parts = urllib.parse.urlsplit(path)
    chunks = parts.path.split("/")
    if parts.query or len(chunks) < 5 or chunks[1] != "media":
        raise ValueError("Invalid media path")
    identifier, session = chunks[2:4]
    if not re.fullmatch(r"[0-9a-f]{32}", identifier) or not re.fullmatch(r"[0-9a-f]{32}", session):
        raise ValueError("Invalid session")
    task = tasks.get(identifier)
    if not task:
        raise ValueError("Not an owned task")
    files = chunks[4:]
    if any(not re.fullmatch(r"[A-Za-z0-9_.-]+", part) or part in (".", "..") for part in files):
        raise ValueError("Invalid segment")
    if not files[-1].endswith((".m3u8", ".ts")):
        raise ValueError("Only HLS TS is supported")
    # Derive path from the generated ID, never from a caller-supplied URL.
    upstream = "/mgui/ui_" + identifier + "/" + "/".join(files)
    return upstream, f"/media/{identifier}/{session}/"


def group_media(rows):
    groups = {}
    for row in rows:
        key = (row.get("vhost", ""), row.get("app", ""), row.get("stream", ""))
        item = groups.setdefault(key, dict(vhost=key[0], app=key[1], stream=key[2],
                                          protocols=[], totalReaders=None, tracks=[]))
        protocol = row.get("schema")
        if protocol and protocol not in item["protocols"]:
            item["protocols"].append(protocol)
        # Same stream's cross-protocol total is repeated: never sum it.
        readers = row.get("totalReaderCount")
        if isinstance(readers, int) and not isinstance(readers, bool) and readers >= 0:
            item["totalReaders"] = max(item["totalReaders"] or 0, readers)
        if row.get("tracks"):
            item["tracks"] = [{k: t[k] for k in
                               ("codec_id_name", "codec_type", "ready", "width", "height", "fps", "sample_rate", "channels")
                               if k in t} for t in row["tracks"]]
    return list(groups.values())


class Gateway:
    def __init__(self):
        cfg = configparser.ConfigParser(interpolation=None)
        if not cfg.read(ROOT / "runtime/gateway/config.ini", encoding="utf-8"):
            raise RuntimeError("Run scripts/start.sh first; gateway config is missing")
        if cfg.get("general", "listen_ip") != "127.0.0.1":
            raise RuntimeError("This version requires the loopback gateway configuration")
        self.secret = cfg.get("api", "secret")
        self.port = cfg.getint("http", "port")

    def call(self, method, **params):
        params["secret"] = self.secret
        req = urllib.request.Request(f"http://127.0.0.1:{self.port}/index/api/{method}",
                                     data=urllib.parse.urlencode(params).encode())
        try:
            opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
            with opener.open(req, timeout=15) as response:
                result = json.load(response)
        except Exception:
            raise RuntimeError("网关 API 无法连接或响应超时，请检查服务端日志") from None
        if result.get("code") != 0:
            # Upstream messages may contain source credentials; do not forward them.
            raise RuntimeError(f"网关 API 返回错误，code={result.get('code')}")
        return result.get("data")


class Controller:
    def __init__(self, gateway, folder):
        self.gateway = gateway
        self.folder = folder
        folder.mkdir(parents=True, exist_ok=True)
        self.path = folder / "tasks.json"
        self.lock = threading.Lock()
        self.tasks = json.loads(self.path.read_text(encoding="utf-8")) if self.path.exists() else {}
        for task in self.tasks.values():
            if task.get("state") == "提交中":
                task["state"] = "上次提交被中断，状态未知；可删除后重建"
        if self.tasks:
            self.save()

    def save(self):
        temp = self.path.with_suffix(".tmp")
        temp.write_text(json.dumps(self.tasks, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(temp, self.path)

    def snapshot(self):
        with self.lock:
            tasks = [dict(t) for t in self.tasks.values()]
        try:
            media = group_media(self.gateway.call("getMediaList") or [])
            return dict(connected=True, media=media, tasks=tasks)
        except RuntimeError as ex:
            return dict(connected=False, error=str(ex), media=None, tasks=tasks)

    def add(self, name, url):
        if not isinstance(name, str) or not name.strip() or len(name) > 64:
            raise ValueError("请输入 1～64 字的任务名称")
        if not isinstance(url, str) or len(url) > 2048 or any(ord(c) < 32 for c in url):
            raise ValueError("RTSP 地址格式错误")
        try:
            parsed = urllib.parse.urlsplit(url)
            valid = parsed.scheme in ("rtsp", "rtsps") and parsed.hostname and parsed.port != 0
        except ValueError:
            valid = False
        if not valid:
            raise ValueError("仅接受带主机地址的 rtsp:// 或 rtsps:// URL")
        with self.lock:
            if len(self.tasks) >= 32:
                raise ValueError("本实验版本最多保存 32 个任务，请删除不再需要的任务")
            identifier = uuid.uuid4().hex
            stream = "ui_" + identifier
            task = dict(id=identifier, name=name.strip(), app="mgui", stream=stream,
                        key="__defaultVhost__/mgui/" + stream, state="提交中")
            # Store ownership before making a request, even if the response is lost.
            self.tasks[identifier] = task
            self.save()
        try:
            result = self.gateway.call("addStreamProxy", vhost="__defaultVhost__", app="mgui",
                                       stream=stream, url=url, rtp_type=0, retry_count=-1,
                                       timeout_sec=10, enable_rtsp=1, enable_rtmp=1,
                                       enable_hls=1, enable_mp4=0, auto_close=0)
            if not result or result.get("key") != task["key"]:
                raise RuntimeError("拉流返回的任务标识不一致，请检查后删除该任务")
            state = "拉流请求成功"
        except RuntimeError as ex:
            state = str(ex)
        with self.lock:
            task["state"] = state
            self.save()
        return dict(task)

    def delete(self, identifier):
        with self.lock:
            task = self.tasks.get(identifier)
            if not task:
                raise ValueError("任务不存在；仅允许删除本界面创建的任务")
            if task["state"] == "提交中":
                raise ValueError("任务仍在提交，请等待请求结束后再删除")
            self.gateway.call("delStreamProxy", key=task["key"])
            del self.tasks[identifier]
            self.save()


def handler(controller, port):
    token = secrets.token_urlsafe(32)
    origin = f"http://127.0.0.1:{port}"

    class Handler(BaseHTTPRequestHandler):
        def setup(self):
            super().setup()
            self.connection.settimeout(20)

        def log_message(self, fmt, *args):
            # Never log URLs or bodies (may contain source credentials).
            print(f"management: {self.command} completed", flush=True)

        def send(self, code, value, content_type="application/json; charset=utf-8", cookie=None):
            payload = json.dumps(value, ensure_ascii=False).encode() if isinstance(value, dict) else value
            self.send_response(code)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(payload)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self' https://cdn.jsdelivr.net; media-src 'self' blob:; worker-src 'self' blob:; frame-ancestors 'none'; object-src 'none'; base-uri 'none'")
            if cookie:
                self.send_header("Set-Cookie", cookie)
            self.end_headers()
            self.wfile.write(payload)

        def allowed_host(self):
            return self.headers.get("Host") == f"127.0.0.1:{port}"

        def do_GET(self):
            if not self.allowed_host():
                return self.send(403, {"error": "请使用 127.0.0.1 地址访问"})
            if self.path == "/api/state":
                result = controller.snapshot()
                result["token"] = token
                return self.send(200, result)
            if self.path.startswith("/media/"):
                return self.media()
            files = {"/": ("index.html", "text/html; charset=utf-8"),
                     "/app.js": ("app.js", "text/javascript; charset=utf-8"),
                     "/style.css": ("style.css", "text/css; charset=utf-8")}
            if self.path not in files:
                return self.send(404, {"error": "Not found"})
            name, mime = files[self.path]
            self.send(200, (STATIC / name).read_bytes(), mime)

        def media(self):
            try:
                with controller.lock:
                    path, cookie_path = media_route(self.path, controller.tasks)
            except ValueError:
                return self.send(404, {"error": "媒体路径或任务无效"})
            try:
                headers = {}
                incoming = SimpleCookie(self.headers.get("Cookie", ""))
                if "ZLM_HTTP_COOKIE" in incoming:
                    headers["Cookie"] = "ZLM_HTTP_COOKIE=" + incoming["ZLM_HTTP_COOKIE"].coded_value
                req = urllib.request.Request(f"http://127.0.0.1:{controller.gateway.port}" + path, headers=headers)
                opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
                with opener.open(req, timeout=10) as response:
                    payload = response.read(16 * 1024 * 1024 + 1)
                    if len(payload) > 16 * 1024 * 1024:
                        raise RuntimeError("Segment exceeds preview limit")
                    cookie = SimpleCookie(response.headers.get("Set-Cookie", ""))
                    outgoing = None
                    if "ZLM_HTTP_COOKIE" in cookie:
                        item = cookie["ZLM_HTTP_COOKIE"]
                        item["path"] = cookie_path
                        item["httponly"] = True
                        item["samesite"] = "Strict"
                        if item["domain"]:
                            del item["domain"]
                        outgoing = item.OutputString()
                    mime = "application/vnd.apple.mpegurl" if path.endswith(".m3u8") else "video/mp2t"
                self.send(200, payload, mime, outgoing)
            except urllib.error.HTTPError as ex:
                self.send(ex.code if ex.code in (403, 404) else 502, {"error": "HLS 资源尚未就绪或不可用"})
            except (BrokenPipeError, ConnectionResetError):
                pass
            except Exception:
                self.send(502, {"error": "HLS 转发失败或超时"})

        def do_POST(self):
            if not self.allowed_host() or self.headers.get("Origin") != origin or not secrets.compare_digest(
                    self.headers.get("X-MG-Token", ""), token):
                return self.send(403, {"error": "请求来源无效，请刷新页面"})
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if length < 2 or length > 8192:
                    raise ValueError("请求体大小无效")
                body = json.loads(self.rfile.read(length))
                if not isinstance(body, dict):
                    raise ValueError("请求体必须是对象")
                if self.path == "/api/tasks":
                    result = controller.add(body.get("name"), body.get("url"))
                    return self.send(200, {"task": result})
                if self.path == "/api/tasks/delete":
                    identifier = body.get("id")
                    if not isinstance(identifier, str):
                        raise ValueError("任务标识无效")
                    controller.delete(identifier)
                    return self.send(200, {"ok": True})
                self.send(404, {"error": "Not found"})
            except (ValueError, TypeError):
                self.send(400, {"error": "参数无效，或任务不存在/仍在提交；请检查输入并刷新"})
            except RuntimeError as ex:
                self.send(502, {"error": str(ex)})
            except Exception:
                self.send(500, {"error": "管理服务内部错误，请检查磁盘与运行状态"})
    return Handler


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=19090)
    args = parser.parse_args()
    if not 1024 <= args.port <= 65535:
        parser.error("port must be in 1024..65535")
    os.umask(0o077)
    folder = ROOT / "runtime/management"
    folder.mkdir(parents=True, exist_ok=True)
    # Linux deployment: prevent two processes from overwriting ownership records.
    import fcntl
    with (folder / "server.lock").open("a") as guard:
        fcntl.flock(guard, fcntl.LOCK_EX | fcntl.LOCK_NB)
        controller = Controller(Gateway(), folder)
        with ThreadingHTTPServer(("127.0.0.1", args.port), handler(controller, args.port)) as server:
            print(f"MediaGateway console: http://127.0.0.1:{args.port}", flush=True)
            try:
                server.serve_forever()
            except KeyboardInterrupt:
                print("Management stopped; upstream streams are retained", flush=True)


if __name__ == "__main__":
    main()
