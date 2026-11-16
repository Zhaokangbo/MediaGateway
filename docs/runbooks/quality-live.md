# RTP 统计第二轮：接收回调与只读 API

## 文件与调用链

- integrations/zlm/quality-edits.json：针对固定上游版本的精确替换清单。
- integrations/zlm/quality.patch：同一改动的可读 diff，供审核，不手动叠加应用。
- scripts/build-quality-zlm.py：检查原版 HEAD、工作区、子模块，复制到独立目录后应用清单。
- scripts/instances.py、select-gateway.py：仅 gateway 可切换独立构建；source 保持原版。
- scripts/verify-quality-live.py：受控本地 RTSP/TCP 测试源与 API 断言。

上游只修改 RtspPlayer.h、RtspPlayer.cpp、server/WebApi.cpp，另在派生源码的 src/CMakeLists.txt
追加模块包含路径和 C++17 编译要求。模块 cpp 位于 src/MediaGateway，由已有 GLOB 加入 zlmediakit。
原版 upstream/ZLMediaKit 不应用任何补丁，原版二进制不覆盖。

真实链路：PlayerProxy → MediaPlayer 创建 RtspPlayerImp → RtpTrack 校验 RTP/SSRC →
RtspPlayer::onBeforeRtpSorted 追加序号统计 → 原有 RTCP 统计/保活 → 原有排序和分发。
未覆盖 setBeforeSorted，未改丢包或 Jitter，也未按统计结果丢弃任何包。

查询链路：getProxyRtpQuality → 按 key 查 API 拉流代理 → owner poller async →
取得当前 RtspPlayer delegate → 复制轨道计数 → JSON。
跨线程不直接读取正在更新的统计对象，也不使用每包全局互斥锁。

## 生命周期与接口语义

新增 POST /index/api/getProxyRtpQuality，参数 secret、key；鉴权沿用 CHECK_SECRET。
只支持 API 创建的 RTSP 拉流代理；不包含 RTSP 推流源，也不包含 RTMP 输入。
不支持的输入返回 supported=false，不伪造零计数。没有代理的 key 返回上游 NotFound。
新 RtspPlayer 使用不同 instance_id（仅在本次 MediaServer 进程生命周期内唯一）。
teardown 重置轨道，已经被上游接受的 SSRC 变化也重置 epoch。首次 play 的 epoch 通常为 1。
API 轨道返回 received、unique、reordered、duplicates、too_old、discontinuities、
highest_extended、epoch、ssrc、track_type、sample_rate、sample_age_ms、window。
scope=application_pre_sort，含义是应用接收回调观察到的顺序，不是网卡抓包统计。
sample_age_ms 是距最后接收包的时间，不是端到端延迟；没有新包时历史快照不代表流仍健康。
proxy_status 保留上游原值，不作为独立的可播放判据。

## 构建（无需先停止现有服务）

Windows 同步：

```powershell
cd 'D:\智能多协议流媒体网关'
scp -r integrations include src scripts docs README.md zkb@192.168.96.128:~/MediaGateway/
```

Ubuntu：

```bash
cd ~/MediaGateway
JOBS=2 python3 scripts/build-quality-zlm.py
```

不下载依赖，不改变代理。依赖上一次已完整初始化的原版源码与子模块。
每次新建 build/zlm-quality/<UTC-PID>/source 和 cmake，可能占用数 GB，保留失败构建方便诊断。
输入哈希、二进制 SHA256、递归子模块和可读补丁保存在 artifacts/quality-build/<UTC-PID>/。
成功写入 runtime/builds/latest-quality.json，但不自动启动、不替换运行中的 gateway。

## 切换与验收

切换会中断 gateway 的现有播放/拉流，source 不停止。管理页面任务记录保留，
但上游代理不跨进程恢复；页面旧任务需删除后重建。先结束浏览器播放。

```bash
bash scripts/stop.sh gateway &&
python3 scripts/select-gateway.py quality &&
bash scripts/start.sh gateway &&
python3 scripts/verify-quality-live.py &&
python3 scripts/verify-t3.py --stage t4
```

验收固定序列 65534,0,65535,65535,1：received=5、unique=4、reordered=1、duplicates=1，
highest_extended=65537，too_old/discontinuities=0。
测试源等待上游 SSRC 切换保护窗口后发送新 SSRC 的 10,11,10：epoch 加一，received=3、
unique=2、duplicates=1、reordered=0。删除并重新创建代理后应获得新 instance_id 和新计数。
测试源只实现本地无鉴权 PCMA RTP-over-TCP 的必要 RTSP 方法，不能用作产品 RTSP 服务。
此阶段使用 PCMA 是为了让固定 RTP 包可确定注入，不替代 H264/AAC 四协议播放回归。

预期输出 PASS: live RTSP quality API，然后四协议回归 PASS: T4。
quality-live 保存每次 API JSON 与 summary.json；T4 另存独立解码证据。
单元测试已由用户验证；本轮补丁锚点与 Python 语法在本地通过，
扩展版 C++ 编译、真实回调/API 以及协议回归待 Ubuntu 执行，不能提前记录为通过。
还未验收 UDP、自动重连、性能开销、Jitter/丢包对外展示；管理页面质量卡暂不改变。

## 回退

```bash
bash scripts/stop.sh gateway &&
python3 scripts/select-gateway.py original &&
bash scripts/start.sh gateway
```

不会删除派生源码、日志或任务文件。再次构建原版仍使用 scripts/build-zlm.sh。
不要在 gateway 运行时手动改 binary-path.txt；选择脚本会检查存活进程并拒绝切换。
