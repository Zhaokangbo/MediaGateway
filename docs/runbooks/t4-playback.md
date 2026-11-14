# T4 同一路输入的多协议播放验收

复用 scripts/verify-t3.py，新增 --stage t4；默认 T3 入口保留。
不修改上游源码、不创建另一套测试源。网关拉取同一路 RTSP 后，
依次验证 RTSP、RTMP、HTTP-FLV、HLS 的实际解码；暂不做并发压测。

```bash
cd ~/MediaGateway
bash scripts/start.sh && python3 scripts/verify-t3.py --stage t4
```

各协议均要求：FFmpeg 正常退出且 -xerror 未报告致命解码错误；
五秒输出至少 100 个视频帧、100 个非空 PCM 音频块。
帧数不是跨协议完全相等的断言，不代表逐帧一致性或端到端延迟测量。
四项及清理全部通过才输出 PASS: T4；失败返回非零，仍尝试其他协议并保留结果。
HLS 先等待含 EXTINF 的媒体列表，最多约 45 秒加单次请求超时，
随后由 FFmpeg 实际请求切片和解码，不能仅凭 m3u8 返回 200 判定通过。
每项解码限制 40 秒。通常约一分钟结束，异常时可能需要数分钟。

证据在 artifacts/t4/<时间-随机后缀>/：summary.json、run.log、
playback-urls.json、各协议 decoder.log、decoder-command.json、decoded.framemd5，
以及 HLS 列表快照、API 响应与 publisher.log。
FFmpeg HTTP 读取忽略代理环境，只访问本机。原始产物保持 gitignore。
自动清理自己的拉流代理和 FFmpeg，保留两个 MediaServer；不改配置和 API secret。

本轮只验证 FFmpeg 客户端；浏览器播放兼容性和观看人数将在最小监控 Web 阶段验收。
后续顺序：最小监控 Web → RTP 质量 C++ 扩展 → 故障恢复 → 延迟与压测 → 热点优化。
Web 先评估 pymkui 复用范围，用真实 API 展示状态，未实现指标显示暂不可用。

本地 Python 语法与参数检查不等于 Ubuntu 多协议验收，实际结果待用户执行。
2026-11-14：本地语法、--help 参数入口、帧摘要计数样本检查通过。
