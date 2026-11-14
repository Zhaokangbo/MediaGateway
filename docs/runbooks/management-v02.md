# 管理工作台 v0.2：HLS 浏览器播放

## 本轮变更与风险

沿用 v0.1 页面结构和任务记录，新增任务播放按钮、播放器、停止与记录导出。
修改 management/server.py、web/index.html、web/app.js、web/style.css、test_server.py。
浏览器 → 同源 /media/<任务>/<播放会话>/ → 管理服务 → gateway HLS。
仅转发本界面拥有的随机任务 ID 下的 m3u8 和 ts，不接受任意转发 URL、路径穿越或查询参数。
每个资源最多 16 MiB；该预览转发不是生产分发节点，不用于容量压测。
上游 API secret 不出后端，浏览器不接触 RTSP 来源密码。

复用 hls.js 固定版本 1.6.13，按需从 jsDelivr 加载。Windows 浏览器首次播放需要互联网；
媒体与 API 始终走本机 SSH 隧道。CDN 不可用时显示明确错误，不影响管理操作。
原生 HLS 可用的浏览器优先原生播放。当前验收编码为测试源 H.264/AAC，不保证 H.265 支持。
官方接口参考：https://github.com/video-dev/hls.js 与 https://hlsjs.video-dev.org/api-docs/hls.js.hls

## 启动

Windows 同步 management 目录，Ubuntu 管理终端 Ctrl+C 后执行：

```bash
cd ~/MediaGateway
python3 management/test_server.py
python3 -u management/server.py --port 29090 2>&1 | tee artifacts/management/server-v02.log
```

现有 MediaServer、持续 FFmpeg 测试源、29090 SSH 隧道无需重启。
浏览器 http://127.0.0.1:29090/ 按 Ctrl+F5，确认 v0.2 与任务旁播放按钮出现。
任务记录保留；只重启管理服务不会删除上游代理。

## 验收与证据

| 动作 | 可见证据 | 验收范围 |
| --- | --- | --- |
| 点击在线任务“播放” | 加载/缓冲后出现真实动态画面，状态显示首个视频帧或浏览器 playing | 单浏览器播放；不是端到端延迟 |
| 手动取消静音 | 听见测试音 | 音频实际可播放，状态标签不替代听音 |
| 观察总读者数 | 播放前后 API 数值及导出采样记录 | 应在无其他客户端时上升，不伪造固定值 |
| 停止播放 | 播放器释放、请求停止，保留网关拉流 | 读者数可延迟下降 |
| 删除播放中的任务 | 自动停止本页播放器，任务下线 | 不影响其他任务 |
| 导出播放记录 | JSON 内包含 UTC 事件、错误与读者数采样 | 最近最多 600 条，页面刷新会清空 |

播放器基于 requestVideoFrameCallback 标记首个显示帧；不支持此 API 时只标记 playing 事件，
要求人工确认画面。45 秒未见首帧停止并报告超时，不自动声称成功。
若 HLS 资源 404、超时或 CDN 失败，导出记录并保留 server-v02.log。

HLS 会话通过 ZLM_HTTP_COOKIE 识别，上游固定版本 HttpFileManager.cpp 默认 cookie 生命周期 60 秒，
访问切片会刷新。转发时重写 Cookie Path 为独立播放会话路径，并保留 HttpOnly/SameSite。
停止后先等待约 60～90 秒观察；不保证精确某一秒归零。暂停不等于释放，验收用“停止播放”。
多标签页分别点击播放会创建不同播放会话，不能把 totalReaderCount 宣称为独立用户数。

## 实测边界

用户截图已确认 v0.1 的创建拉流、真实一路流注册、三协议标签、一个管理任务与读者数 0。
截图不证明删除操作、HTTP 测试全部通过或浏览器出画面。
v0.2 本地：媒体路径正常/非法/非归属任务测试、Python 与 JavaScript 语法通过。
沙箱限制网络连接，HTTP 转发与浏览器渲染未在本地验收，待用户 Ubuntu 执行。
当前不会把页面播放结果写成全局“已验收”，播放记录只代表本浏览器本次观测。
