# T1 环境验证记录

日期：2026-11-14。证据来自用户提供的 Ubuntu 终端输出，不是代理远程实测。

## 已确认

- Ubuntu 24.04.4 LTS，x86_64，4 个逻辑 CPU，约 7.7 GiB 内存。
- 两个脚本的 bash -n 联合检查成功返回，未显示语法错误。
- apt-get update 成功；安装阶段退出 100，dpkg 前端锁被 unattended-upgrades 持有。
- 构建入口在环境检查处停止，报告缺少 cmake、ninja-build、git、libssl-dev、curl；没有进入 CMake。

## 本次修复

bootstrap-ubuntu.sh 的 apt-get install 增加 -o DPkg::Lock::Timeout=300，最多等待 300 秒。保留退出码，并给出明确重试提示。不删除锁、不停止自动更新。

该参数针对 dpkg 安装锁；不承诺处理 apt-get update 使用的软件包索引锁。若 update 阶段被锁阻止，等待现有更新完成后重试。

参考： https://github.com/Debian/apt/blob/main/apt-pkg/deb/debsystem.cc

## 回归方法与验收

在 Ubuntu 运行 bash -n scripts/bootstrap-ubuntu.sh，再运行 bash scripts/bootstrap-ubuntu.sh --install。若锁在等待期限内释放，应继续安装并输出环境 PASS；若仍被占用，应非零退出且保留日志，不进入编译。

环境 PASS 后才运行 JOBS=2 bash scripts/build-zlm.sh。构建成功须提供编译日志、子模块清单、二进制哈希；当前没有这些结果。

状态：原脚本语法检查 PASS（用户证据）；锁等待修复运行验证 PENDING；依赖安装 BLOCKED；构建 NOT RUN；媒体运行测试 NOT RUN。

## 后续用户验证（北京时间 2026-11-14 11:48）

- 修改后的脚本通过 bash -n；依赖安装成功，环境检查连续两次 PASS。
- Git 2.43.0、CMake 3.28.3、GCC 13.3.0；FFmpeg 编码器检查通过。
- 日志未显示实际等待锁的过程，因此仅确认正常安装路径成功；锁持续占用直到超时的分支未实测。
- build-zlm.sh 在 git clone 处退出 128：Recv failure，连接被对方重置。尚未执行 checkout、子模块初始化和 CMake。
- 最新状态：环境 PASS；源码获取 BLOCKED（网络）；构建 NOT RUN；播放测试 NOT RUN。

## 编译成功（用户终端证据）

使用命令级 Git 代理后，构建脚本已输出 PASS: MediaServer target compiled。此结果来自用户提供的终端末尾输出。

- 二进制：upstream/ZLMediaKit/release/linux/RelWithDebInfo/MediaServer。
- SHA-256：14a6548d2fa1ddaf33afed40876f7927cf055ed60cec9decbe38b77236343c2f。
- 用户侧构建证据目录：artifacts/build/20261114T091230Z-3765。
- 最新状态：编译 PASS；服务启动/API/RTSP 输入/播放/重连 NOT TESTED。完整编译日志、递归子模块清单尚未由代理逐项复核。

