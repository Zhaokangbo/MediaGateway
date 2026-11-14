# T2 双实例生命周期验证

状态：已实现并核对固定上游启动参数；尚未在 Ubuntu 运行本脚本，验收待执行。

入口：bash scripts/start.sh、stop.sh、status.sh、logs.sh；可传 source、gateway 或 all（默认）。

- source：RTSP 18554、HTTP 18081、RTMP 11935。
- gateway：RTSP 8554、HTTP 18080、RTMP 1935。
- 初始均绑定 127.0.0.1，仅从虚拟机内部访问。
- 自动从上游 conf/config.ini 生成 runtime/<实例>/config.ini，随机 secret 只落在忽略目录中，不输出到终端。
- 两实例独立配置、HTTP/HLS 根目录、日志和进程状态；已存在的配置不自动覆盖。
- 启动前检查端口；调用 MediaServer -c <配置> --log-dir <日志目录> -t 2，等待 getMediaList 返回 code=0。
- 生命周期操作加文件锁；停止前核对 PID、/proc 启动时间、可执行文件和完整参数，发送 SIGTERM，等待最多 10 秒，不强杀其他进程。
- 任一实例失败时保留现场；all 操作不自动回滚另一实例，修复前可 stop all。
- 命令直接使用进程管理而非 systemd；启动 API 成功不代表媒体播放成功。

在 Ubuntu 项目目录依次运行：

```bash
bash scripts/start.sh
bash scripts/status.sh
bash scripts/start.sh
bash scripts/stop.sh
bash scripts/status.sh
```

最后一次 status 在全部停止时预期非零退出，显示 STOPPED，这是状态查询约定。重复上述过程三轮，确认重复 start 不新增 PID，停止后端口释放：

```bash
ss -ltn | grep -E ':(8554|18554|18080|18081|1935|11935)\\b'
```

全部停止后 grep 无匹配预期返回 1。失败时查看：

```bash
bash scripts/logs.sh
```

验收证据：每轮命令输出、两个 PID、API code=0、停止后端口结果，以及 runtime/<实例>/console.log。只提供脱敏片段，不公开真实配置。下一步 T3 才添加 FFmpeg 测试源与 RTSP 代理。

当前检查：Python 语法与帮助入口在 Windows 验证；Linux /proc 所有权核对、端口绑定、MediaServer 启停、API 就绪均待 Ubuntu 实测。

