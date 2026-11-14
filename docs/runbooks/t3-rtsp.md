# T3：RTSP 输入、主动拉流与解码验收

## 范围与调用链

新增 scripts/verify-t3.py，复用 instances.py 的配置和 PID 身份检查。
FFmpeg testsrc2 + sine → H.264/AAC → RTSP/TCP 推送 source:18554；
gateway 通过 addStreamProxy 主动拉取，再从 gateway:8554 解码五秒。
不修改上游、不开放外部端口、不做转码服务。FFmpeg 编码仅用于生成测试源。
API 依据 upstream.lock.json 固定版本 server/WebApi.cpp；检查 HTTP 与 JSON code。

## 执行

```bash
cd ~/MediaGateway
bash scripts/start.sh && python3 scripts/verify-t3.py
```

终端打印 Evidence 目录；全部结果在 artifacts/t3/<UTC时间-随机后缀>/。
每次使用独立 mgtest/t3_<UUID>，避免覆盖其他流。
测试结束或异常会删除自己的拉流代理、终止自己的 FFmpeg 子进程，保留两个服务器运行。
若 API 请求超时，按此独占流的确定性代理 key 尝试清理；清理失败标记 FAIL。
SIGKILL、虚拟机断电等无法触发 finally；此时查看记录中的 stream/key 并人工恢复，
不要批量关闭其他流。普通失败可查看 publisher.log、decoder.log、summary.json，
以及 bash scripts/logs.sh 的服务端日志。不要分享 runtime 配置内的 API secret。

## 验收标准

- source 与 gateway 的 getMediaList 都注册指定 RTSP 流。
- gateway FFmpeg 解码正常退出，必选视频和音频两个轨道，-xerror 遇解码错误失败。
- 五秒输出至少 100 个视频帧、100 个非空音频输出块；音频块数不等于采样数。
- decoded.framemd5 为实际解码后的原始视频及 PCM 的逐块摘要，不使用 -c copy。
- 清理后两个实例不再注册本次测试流，summary.json 为 PASS。
- 保存命令、FFmpeg 版本、API 响应、编码/解码日志、帧摘要和汇总。

rtp_type=0 指定 TCP；retry_count=0 仅用于本次有界接入验证，不测试自动重连。
注册了 RTMP/HLS 不代表播放通过；本轮不验收观看人数、其他播放协议或首帧/端到端延迟。
自动化脚本的本地语法检查不等于 Ubuntu 验收；运行结果待实际执行。

2026-11-14 本地检查：Python 语法通过；帧摘要计数器对含视频/音频记录的样本
以及只有注释的空输出检查通过。未在本地执行 FFmpeg 或 Ubuntu 媒体链路。
