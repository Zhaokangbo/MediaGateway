# T3 RTSP 接入实测

证据来源：用户在 Ubuntu 24.04.4 执行后提供的终端输出。
2026-11-14，source PID 6303，gateway PID 6311，两者 API OK。
source RTSP 注册成功，gateway RTSP 注册成功。
gateway 实际解码视频 124 帧、音频 235 块，最终 PASS: T3（含脚本清理检查）。
尚未单独审阅原始 summary.json、帧摘要或全量日志。

用户侧证据目录：
`/home/zkb/MediaGateway/artifacts/t3/20261114T093500Z-1d5c8bf1fc36`。

此结果只证明测试源生成、RTSP 推流、主动拉流、RTSP 分发和音视频解码链路。
不代表其他播放协议、浏览器、观看人数、重连或延迟已验收。
