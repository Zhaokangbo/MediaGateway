# MediaGateway

基于 ZLMediaKit 的多协议流媒体网关学习与工程实践项目。

当前阶段：源码调研与架构设计完成；用户已在 Ubuntu 24.04.4 通过 Bash 语法检查、依赖安装和环境检查。固定版本源码下载因 GitHub 连接被重置而失败，尚未进入 CMake 编译或运行媒体服务。GitHub 写入授权已验证，阶段代码通过独立 Commit 保留。

- [架构、源码证据与任务计划](docs/phase-01-architecture.md)
- [固定上游版本](upstream.lock.json)
- [VMware Ubuntu 接入与构建](docs/runbooks/vmware-ubuntu-setup.md)

在 Ubuntu 项目目录执行 `bash scripts/bootstrap-ubuntu.sh --check` 检查依赖；安装依赖后执行 `JOBS=2 bash scripts/build-zlm.sh`。详细说明见接入文档。

首轮目标：Ubuntu 24.04 上，一路 RTSP 主动拉流，输出 RTSP、RTMP、HTTP-FLV、HLS，并提供生命周期脚本及自动化验收。

原则：复用上游、分阶段迭代、先声明变更文件和调用链、每项有测试与日志、每次改动提交 Git、不虚构性能结果。

公开仓库：https://github.com/Zhaokangbo/MediaGateway 。各阶段使用独立 Git Commit 保留改动和真实验证记录，不提交运行凭据或原始日志。上游完整源码尚未取得，后续按 lock 取回并递归核对子模块；当前 lock 不是完整可复现依赖清单，构建任务需补全。

项目自有代码采用 MIT 许可证，见 LICENSE。ZLMediaKit、ZLToolKit、PyMKUI 及其依赖保留各自的许可证和版权声明，本仓库不重新授权第三方代码。

