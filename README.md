# MediaGateway

基于 ZLMediaKit 的多协议流媒体网关学习与工程实践项目。

当前阶段：用户在 Ubuntu 24.04.4 已编译出 MediaServer，二进制哈希及证据见 T1 验证记录。T2 双实例启停脚本已准备，实际启动、API、播放与重连待验证。

- [架构、源码证据与任务计划](docs/phase-01-architecture.md)
- [固定上游版本](upstream.lock.json)
- [VMware Ubuntu 接入与构建](docs/runbooks/vmware-ubuntu-setup.md)
- [T1 实际验证记录](docs/experiments/t1-environment.md)
- [T2 双实例生命周期验证](docs/runbooks/t2-instances.md)

在 Ubuntu 项目目录执行 `bash scripts/bootstrap-ubuntu.sh --check` 检查依赖；安装依赖后执行 `JOBS=2 bash scripts/build-zlm.sh`。详细说明见接入文档。

首轮目标：Ubuntu 24.04 上，一路 RTSP 主动拉流，输出 RTSP、RTMP、HTTP-FLV、HLS，并提供生命周期脚本及自动化验收。

原则：复用上游、分阶段迭代、先声明变更文件和调用链、每项有测试与日志、每次改动提交 Git、不虚构性能结果。

公开仓库：https://github.com/Zhaokangbo/MediaGateway 。各阶段使用独立 Git Commit 保留改动和真实验证记录，不提交运行凭据或原始日志。用户侧已按固定版本完成源码获取及构建；当前 lock 尚不是完整可复现依赖清单，递归依赖和操作系统包版本以构建产物中的清单为准。

项目自有代码采用 MIT 许可证，见 LICENSE。ZLMediaKit、ZLToolKit、PyMKUI 及其依赖保留各自的许可证和版权声明，本仓库不重新授权第三方代码。

