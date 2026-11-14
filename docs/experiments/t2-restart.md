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

本次本地仅验证 Python 语法。Windows 不具备 Linux socket 语义，
Linux 回归与真实 MediaServer 连续重启结果待用户执行，不能记为通过。
