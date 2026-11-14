# T2 连续重启故障与修复

## 用户提供的 Ubuntu 结果

2026-11-14：首次单轮启动、API、重复启动、停止通过。
连续三轮验证中，第 1 轮 source PID 6036、gateway PID 6044，API OK，
重复启动没有新建实例，两个实例均报告 STOPPED。
第 2 轮两者报 OSError errno 98 Address already in use；第 3 轮未执行。
因此 T2 单轮通过，但连续重启验收未通过。

## 修复

scripts/instances.py 原端口预检使用没有 SO_REUSEADDR 的 socket.bind。
Linux 上此前连接留下的 TIME_WAIT 可导致该预检失败，即使监听进程已退出。
该机制与现场症状吻合；现场未提供 ss 状态，尚不能排除真实端口占用。
新增 check_ports，设置 SO_REUSEADDR 并在失败消息中包含具体端口。
不设置 SO_REUSEPORT，不结束其他进程，不改变 sysctl。
预检只是建议性检查；实际启动及 API 就绪检查继续保留。

## 回归方法与验收

在 Ubuntu 执行 python3 scripts/test_port_preflight.py：必须显示 OK，不能是 skipped。
测试使用系统分配的临时端口，不占用业务端口；先确认活跃监听拒绝绑定，
然后构造服务端主动关闭，验证旧式 bind 返回 EADDRINUSE，而新预检通过。
随后连续三轮执行 start/status/start/stop，均须成功，停止后检查业务端口无 LISTEN。
保存测试与生命周期日志至 artifacts/t2；原始运行产物不上传公开仓库。

修复提交时本地仅验证 Python 语法。Windows 不具备 Linux socket 语义。

## 修复后的实际结果（2026-11-14）

证据来源：用户在 Ubuntu 执行修复版后贴回的终端输出，并非代理本地执行。
test_listener_and_time_wait 显示 ok，Ran 1 test in 0.001s，最终 OK，无跳过。

| 轮次 | source PID | gateway PID | 结果 |
| --- | --- | --- | --- |
| 1 | 6137 | 6146 | 启动、API、状态、重复启动抑制、停止均成功 |
| 2 | 6166 | 6174 | 启动、API、状态、重复启动抑制、停止均成功 |
| 3 | 6194 | 6202 | 启动、API、状态、重复启动抑制、停止均成功 |

最终 ss -ltnp 输出无 8554、18554、18080、18081、1935、11935 监听。
T2 连续重启验收通过。所有 API 返回 media_sources=0，符合尚未接入媒体的状态。
日志由用户命令保存到 artifacts/t2/retest-<UTC时间>.log，具体文件名未提供。
该结果不代表 RTSP 输入、多协议播放、观看人数或故障重连已通过。
