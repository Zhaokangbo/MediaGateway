# VMware Ubuntu 接入与 T1 构建

当前状态：Ubuntu 24.04.4 的依赖安装和环境检查已通过（用户终端证据）。源码克隆因连接被重置而失败，尚未编译。公开仓库 https://github.com/Zhaokangbo/MediaGateway 的写入授权已通过实际创建 LICENSE 提交验证；Windows 副本的 .git 仍不可写。

2026-11-14 接入进展：用户已在 Windows 终端成功通过 SSH 登录 Ubuntu 24.04.4，ssh 服务 active。代理执行环境访问 VM 的 TCP 22 返回 Permission denied（认证前），因此本轮采用用户终端执行，不将此错误误判为 VM 密码或密钥问题。

此前接入记录：用户已授权公开各阶段代码；本机 gh 凭据校验失败，浏览器自动控制超时。后续用户重新授权后，GitHub 创建文件成功。初始化提交为 20cfd03f47c10bd72d279901519e168a9acaedc0。

公开提交只包含项目源码、模板和技术文档；不包含私钥、Token、真实配置、原始日志或测试抓包。每阶段提交说明实际验证范围，未运行的脚本明确标为待验证。先保留架构和 T1 脚本的独立提交，再按构建修复追加提交，不伪造先前 Commit。上游源码不重复上传，使用 lock 和后续最小补丁保留依赖边界。项目自有代码采用 MIT，许可证已补齐；上游版权声明不变。

## 用户协助：建立执行入口

在 VMware 中启动 Ubuntu，打开终端执行：

```bash
sudo apt update
sudo apt install -y openssh-server
sudo systemctl enable --now ssh
whoami
hostname -I
systemctl is-active ssh
```

提供用户名、Ubuntu IPv4 和 ssh 状态即可，不提供密码、私钥或 GitHub Token。若输出多个 IP，保留输出以便辨认；Windows 和 VM 使用现有可互通网络即可，不必先改桥接，也不做公网端口映射。

Windows PowerShell 试连接（替换实际值）：

```powershell
ssh 用户名@Ubuntu_IP
```

第一次连接前，在 Ubuntu 可运行以下命令获取主机密钥指纹，与 Windows 提示核对：

```bash
ssh-keygen -lf /etc/ssh/ssh_host_ed25519_key.pub
```

密码在你自己的终端输入。自动执行需要 SSH 密钥登录，连接确认后再创建项目专用密钥并安装公钥；不关闭主机密钥校验，不发送私钥。如果不希望开放自动 SSH，可在 VM 手动执行脚本并提供日志。

若 ssh 不通，先提供实际报错，再区分服务、地址、VMware NAT 和防火墙问题。不要直接关闭整个防火墙。

## GitHub 与项目传输

首轮仅访问公开仓库，无需登录 GitHub。可以先检查虚拟机联网：

```bash
git ls-remote https://github.com/ZLMediaKit/ZLMediaKit.git HEAD
```

这只是联网检查，构建仍 checkout lock 中固定版本。ZLM 子模块还访问 Gitee，GitHub 可达不代表子模块可达。不要将 Windows 的 127.0.0.1 代理地址直接复制给 VM。

项目应复制到 Ubuntu 本地文件系统，例如 ~/MediaGateway，不在 Windows 共享挂载上压测。传输范围为 README.md、.gitignore、.gitattributes、upstream.lock.json、scripts/、docs/；不复制当前受限的 .git 或 runtime/。项目传输与实际执行会在连接信息明确后进行。

## 构建命令

在 Ubuntu 项目根目录执行：

```bash
bash scripts/bootstrap-ubuntu.sh --check
# 缺依赖时执行；会安装软件包，需要本机 sudo
bash scripts/bootstrap-ubuntu.sh --install
JOBS=2 bash scripts/build-zlm.sh
```

默认只用两个编译任务降低 VM 内存压力。日志在 artifacts/environment/ 和 artifacts/build/，包含软件包版本、源码/递归子模块版本、CMakeCache、构建输出和二进制哈希。

构建脚本不会修改系统代理、覆盖脏源码、自动切换已有不同版本 checkout，也不会启动媒体服务。失败时保留现场；不要删除有改动的源码后盲目重试。

配置使用 RelWithDebInfo，启用 Server/Player/HLS/MP4，关闭 Python/WebRTC/SRT/SCTP/RTPPROXY 等本轮不需要的功能。外部 FFmpeg 用作测试源，不需要内部 FFmpeg 集成。

## 验证与提交边界

T1 完成需要实际 Ubuntu 构建证据；随后 T2 验证二进制启动、API 与两实例生命周期。脚本打印“编译通过”不等于最小系统验收通过。

源码读取与脚本审查不代替 Linux 执行。当前测试状态由实际报告说明。

如果 Windows 沙箱持续禁止写入 .git，可以在 Ubuntu 的项目副本初始化 Git 并提交；采用用户已有的 Git 作者配置，若没有则询问姓名与邮箱，不代填用户身份。不创建远程仓库或推送，除非用户指定。

后续顺序：T1 构建 -> T2 两实例启停 -> T3 测试源和代理 -> T4 多协议解码 -> T5 观看数 -> T6 重连 -> T7 报告。

