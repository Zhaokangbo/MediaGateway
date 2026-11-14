# 管理工作台 v0.1

## 选择与范围

固定版本 pymkui README 确认其依赖 ENABLE_PYTHON=ON、mk_plugin、FastAPI 和数据库。
当前已验收构建关闭 Python。为保持媒体基线，本次新增独立 Python 标准库管理服务，
通过上游 HTTP API 管理网关，不复制协议转换、拉流重连或媒体统计实现。
参考：https://github.com/ZLMediaKit/pymkui/blob/aaba4f0fbd183ea964d74a1f64549fb2208fdbdc/README.md
该选择只适用于本地实验工作台；未来扩展前再次评估 pymkui，避免重建完整平台。

文件：management/server.py、management/web/index.html、app.js、style.css、test_server.py。
调用链：浏览器同源请求 → 管理服务 → 网关 getMediaList/addStreamProxy/delStreamProxy。
没有修改 ZLMediaKit 源码，没有浏览器播放器或模拟指标。

## 指标到界面证据

| 能力 | 数据与界面 | 验证动作 |
| --- | --- | --- |
| 网关连接 | getMediaList 成功/失败；失败显示未知而非 0 | 停止 gateway 后观察 |
| 在线流 | 按 vhost/app/stream 分组，协议以标签显示 | 输入一路流，检查多协议不会成为多路 |
| 总读者数 | totalReaderCount 跨 schema 取最大观测值，不累加 | ffplay 接入前后对比；不是独立用户统计 |
| 轨道 | 白名单字段：编码、宽高、音频采样率等 | 点击查看 |
| 创建任务 | 随机 mgui/ui_UUID，API 结果与媒体注册分别展示 | 输入真实 RTSP 源 |
| 删除任务 | 仅删除持久化归属记录中的代理 key | 删除任务，确认媒体下线 |
| 无流与异常 | 空列表提示新增任务；断连提示状态未知 | 无输入/停止网关分别检查 |
| RTP 指标、浏览器播放 | 明确显示尚未接入 | 不以 0 或绿色成功占位 |

界面：顶部状态、三张概览卡、在线流列表与任务列表、右侧创建表单和轨道详情。
每 3 秒轮询，不使用 Webhook，不宣称已经有事件历史或性能监控。

## 部署与访问

Windows PowerShell 同步：

```powershell
cd 'D:\智能多协议流媒体网关'
scp -r management zkb@192.168.96.128:~/MediaGateway/
```

Ubuntu 终端 A：

```bash
cd ~/MediaGateway
bash scripts/start.sh
mkdir -p artifacts/management
set -o pipefail
python3 management/test_server.py 2>&1 | tee artifacts/management/tests.log
# 测试必须显示 4 项 OK；失败先查看日志。
python3 -u management/server.py 2>&1 | tee artifacts/management/server.log
```

管理服务只监听 127.0.0.1:19090，无额外 pip/npm 依赖。终端保持运行，Ctrl+C 停止管理服务，
不会停止 MediaServer 或已有拉流。任务记录保存在 runtime/management/tasks.json，
不保存来源 URL/密码；网关重启后不自动恢复任务，需要删除旧记录后重新创建。
失败或超时仍保留任务归属，便于用户执行删除清理；不批量关闭其他流。

Windows 新开 PowerShell：

```powershell
ssh -N -o ExitOnForwardFailure=yes -L 127.0.0.1:19090:127.0.0.1:19090 zkb@192.168.96.128
```

该窗口无输出并持续占用是正常状态。浏览器访问 http://127.0.0.1:19090/ 。
必须使用这个地址和相同端口，避免 localhost 与严格 Host/Origin 校验不一致。
如 Windows 的 19090 已被其他项目占用，可在 Ubuntu 用 --port 19091，隧道两端与浏览器都改成 19091。

## 创建真实测试流

Ubuntu 终端 B（持续运行，Ctrl+C 停止）：

```bash
ffmpeg -hide_banner -re -f lavfi -i testsrc2=size=640x360:rate=25 \
  -re -f lavfi -i sine=frequency=1000:sample_rate=48000 \
  -map 0:v:0 -map 1:a:0 -c:v libx264 -preset ultrafast -tune zerolatency \
  -pix_fmt yuv420p -threads 2 -g 50 -c:a aac -b:a 64k \
  -f rtsp -rtsp_transport tcp rtsp://127.0.0.1:18554/live/ui_demo
```

页面输入名称“本机测试视频”和 RTSP 地址 `rtsp://127.0.0.1:18554/live/ui_demo`。
预期：拉流请求成功 → 媒体已注册 → 在线列表出现 mgui/ui_UUID，可查看轨道。
看不到画面是当前范围限制：本版本没有播放器。播放验收沿用 T4 脚本。
总读者数仅显示 API 原值，观看人数实验需在 Ubuntu 使用实际流 ID 接入播放器后单独验收。
最后删除页面任务，应只移除本任务；停止测试源。任务名称必须不包含密码等敏感信息。

## 边界与测试状态

只面向可信本机用户，通过 SSH 隧道访问；没有多用户登录与公网部署能力。
后端保管 api.secret，前端不接收密钥或原始上游错误（可能包含密码）。
Host、Origin 和随机请求令牌阻止其他网页直接创建/删除任务；令牌不替代多用户认证。
RTSP 输入允许访问网关能到达的地址，用于本机/局域网实验。

2026-11-14 Windows 本地：控制器的失败清理归属、计数不重复、持久化和 URL 不存盘测试通过。
HTTP 集成测试因沙箱 WinError 10013 禁止网络连接而失败，未宣称通过。
因此真实页面渲染、HTTP 操作、Ubuntu 网关联调、SSH 隧道与观看人数仍待用户验收。
单元测试 FakeGateway 只存在于 test_server.py；生产页面没有模拟数据模式。
