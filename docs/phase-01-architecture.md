# MediaGateway：源码调研与第一阶段架构设计

- 日期：2026-11-14（北京时间）
- 本轮范围：源码调研、架构决策、迭代计划；不实现功能，不宣称已部署或通过测试。
- 当前环境：Windows PowerShell，项目工作目录 D:\智能多协议流媒体网关，开始时没有项目文件或 Git 仓库。
- 证据方式：通过 GitHub 接口按 commit 读取源码。Git clone 因本机代理 127.0.0.1:9567 不可达而失败；单次禁用 Git 代理的尝试亦因 DNS 线程失败而未完成。没有修改系统或 Git 全局代理。
- Ubuntu 状态：尚未取得可执行的 Ubuntu 24.04 会话；WSL 枚举返回 E_ACCESSDENIED。这不能证明用户没有 Ubuntu VM。下一轮需要可用的 VM/SSH 执行入口。
- 所有下文数值门槛都是拟定验收标准，不是实测结果。

## 1. 调研基线与证据

| 仓库 | 固定 revision | 使用方式 |
| --- | --- | --- |
| ZLMediaKit | fb3265725f0880da1f52a3cc6e6eb04bbc327fa3 | MediaServer 数据面和现有 API |
| ZLToolKit | d7d601200f65f3111dbf9d20ed7f14d2654bbd6e | 上述 ZLM 的 3rdpart/ZLToolKit gitlink，构建必须跟随此版本 |
| ZLToolKit 独立仓库 HEAD | 39d4a647e441278c533258d0caeb152ef739127b | 仅作版本差异记录，不用它替换 ZLM 锁定的子模块 |
| pymkui | aaba4f0fbd183ea964d74a1f64549fb2208fdbdc | 后续管理界面与插件复用候选；须验证和上述 ZLM 配套 |

完整源码尚未 clone。下列是已读取的主要文件；链接固定到 commit，行号用于定位，不依赖移动中的 master。

| 主题 | 源码入口与观察 |
| --- | --- |
| 依赖和能力开关 | [CMakeLists.txt](https://github.com/ZLMediaKit/ZLMediaKit/blob/fb3265725f0880da1f52a3cc6e6eb04bbc327fa3/CMakeLists.txt)、[.gitmodules](https://github.com/ZLMediaKit/ZLMediaKit/blob/fb3265725f0880da1f52a3cc6e6eb04bbc327fa3/.gitmodules)、[README](https://github.com/ZLMediaKit/ZLMediaKit/blob/fb3265725f0880da1f52a3cc6e6eb04bbc327fa3/README.md) |
| HTTP API | [server/WebApi.cpp](https://github.com/ZLMediaKit/ZLMediaKit/blob/fb3265725f0880da1f52a3cc6e6eb04bbc327fa3/server/WebApi.cpp)：ToJson 478、makeMediaSourceJson 494、addStreamProxy 661、API 注册 1338、getProxyInfo 1984、addProbe 2726 |
| Webhook | [server/WebHook.cpp](https://github.com/ZLMediaKit/ZLMediaKit/blob/fb3265725f0880da1f52a3cc6e6eb04bbc327fa3/server/WebHook.cpp)：异步请求与重试 178、流变化 548 |
| 流目录 | [src/Common/MediaSource.cpp](https://github.com/ZLMediaKit/ZLMediaKit/blob/fb3265725f0880da1f52a3cc6e6eb04bbc327fa3/src/Common/MediaSource.cpp)：find 470、regist 511、unregist 557 |
| 转封装分发 | [src/Common/MultiMediaSourceMuxer.cpp](https://github.com/ZLMediaKit/ZLMediaKit/blob/fb3265725f0880da1f52a3cc6e6eb04bbc327fa3/src/Common/MultiMediaSourceMuxer.cpp)：totalReaderCount 307、onAllTrackReady 741、onTrackFrame_l 880 附近 |
| 拉流与重连 | [src/Player/PlayerProxy.cpp](https://github.com/ZLMediaKit/ZLMediaKit/blob/fb3265725f0880da1f52a3cc6e6eb04bbc327fa3/src/Player/PlayerProxy.cpp)：play、rePlay、setDirectProxy、onPlaySuccess、attachPlayerTracks |
| RTSP 输入 | [src/Rtsp/RtspPlayer.cpp](https://github.com/ZLMediaKit/ZLMediaKit/blob/fb3265725f0880da1f52a3cc6e6eb04bbc327fa3/src/Rtsp/RtspPlayer.cpp)：onRtpPacket 624、onRtpSorted 665、getPacketLossRate 674、onBeforeRtpSorted 789、RtspPlayerImp::onRecvRTP 999 |
| RTP 排序 | [src/Rtsp/RtpReceiver.h](https://github.com/ZLMediaKit/ZLMediaKit/blob/fb3265725f0880da1f52a3cc6e6eb04bbc327fa3/src/Rtsp/RtpReceiver.h) 和 [RtpReceiver.cpp](https://github.com/ZLMediaKit/ZLMediaKit/blob/fb3265725f0880da1f52a3cc6e6eb04bbc327fa3/src/Rtsp/RtpReceiver.cpp)：排序前回调先于 sortPacket |
| RTCP 统计 | [src/Rtcp/RtcpContext.cpp](https://github.com/ZLMediaKit/ZLMediaKit/blob/fb3265725f0880da1f52a3cc6e6eb04bbc327fa3/src/Rtcp/RtcpContext.cpp)：RtcpContextForRecv::onRtp 161、getLost 244、createRtcpRR 255 |
| RTSP 输出 | [src/Rtsp/RtspMediaSource.h](https://github.com/ZLMediaKit/ZLMediaKit/blob/fb3265725f0880da1f52a3cc6e6eb04bbc327fa3/src/Rtsp/RtspMediaSource.h)、[RtspSession.cpp](https://github.com/ZLMediaKit/ZLMediaKit/blob/fb3265725f0880da1f52a3cc6e6eb04bbc327fa3/src/Rtsp/RtspSession.cpp)：attach 941、setReadCB2 954、sendRtpPacket 1326 |
| 网络事件循环 | [ZLToolKit/src/Poller/EventPoller.cpp](https://github.com/ZLMediaKit/ZLToolKit/blob/d7d601200f65f3111dbf9d20ed7f14d2654bbd6e/src/Poller/EventPoller.cpp)：async_l 278、runLoop 372 |
| 缓存分发 | [ZLToolKit/src/Util/RingBuffer.h](https://github.com/ZLMediaKit/ZLToolKit/blob/d7d601200f65f3111dbf9d20ed7f14d2654bbd6e/src/Util/RingBuffer.h)：write 390、attach 418 |
| 默认行为 | [conf/config.ini](https://github.com/ZLMediaKit/ZLMediaKit/blob/fb3265725f0880da1f52a3cc6e6eb04bbc327fa3/conf/config.ini)：protocol、general、rtsp、hook |
| PyMKUI 集成 | [README](https://github.com/ZLMediaKit/pymkui/blob/aaba4f0fbd183ea964d74a1f64549fb2208fdbdc/README.md)、[mk_plugin.py](https://github.com/ZLMediaKit/pymkui/blob/aaba4f0fbd183ea964d74a1f64549fb2208fdbdc/backend/mk_plugin.py)、[py_http_api.py](https://github.com/ZLMediaKit/pymkui/blob/aaba4f0fbd183ea964d74a1f64549fb2208fdbdc/backend/py_http_api.py) |
| PyMKUI 恢复和切源 | [plugins/pull_proxy.py](https://github.com/ZLMediaKit/pymkui/blob/aaba4f0fbd183ea964d74a1f64549fb2208fdbdc/backend/plugins/pull_proxy.py)、[database.py](https://github.com/ZLMediaKit/pymkui/blob/aaba4f0fbd183ea964d74a1f64549fb2208fdbdc/backend/database.py) |

## 2. 架构结论

采用“原版 MediaServer 数据面 + API 驱动的轻量运维/验收层 + 后续小范围 C++ 观测扩展”。

第一轮不新写 C++ 服务器，不接管 Socket、RTSP 状态机、RTP 重排序或转封装。先建立可重复的基线，再学习和扩展真实热点。ZLToolKit 已由 ZLM 引入，不再给管理层引入另一份网络框架。

PyMKUI 不是一个只需启动 uvicorn 的独立 HTTP 面板：当前 backend 使用 mk_loader，FastAPI 接口嵌入 ZLM Python 插件环境。接入需要 ENABLE_PYTHON=ON、Python 开发依赖、PYTHONPATH、[python] plugin 及前端路径。第一轮先关闭 Python 插件，以减少部署变量；下一轮接入它已有的页面、代理持久化、恢复和切源，不重复造管理平台。

多协议转换首先是“压缩帧的解包、转封装和重打包”，不代表自动解决所有编码兼容性。第一轮固定 H.264 + AAC；WebRTC 的音频兼容性、ICE/NAT 和浏览器能力另列任务。README 的“闭源专业版”转码、JT1078、专用 IPTV 等能力不能列为本项目免费开源现成功能。

## 3. 核心对象和调用链

### EventPoller

Linux 下事件循环通过 epoll_wait 监听非阻塞 I/O，并处理定时任务。EventPollerPool 提供多个事件线程；不是每个观看者一个线程。async_l 在允许且当前已是目标线程时可直接执行，否则加锁入队并写管道唤醒目标线程。

线程约束：网络回调不能做同步数据库、大块日志落盘、阻塞 HTTP 或耗时解码。流状态在 owner poller 上更新；跨线程读取通过异步快照。对象释放、定时器取消、weak_ptr 生命周期均纳入后续 C++ 扩展评审。

### MediaSource

MediaSource 是“某种输出协议的一路媒体源”的注册与发现抽象。注册表按 schema/vhost/app/stream 组织，提供查找、注册/注销事件、观看数、来源和轨道信息。它不是统一原始像素缓冲，也不是每个播放器单独建一个源。

业务流标识使用 vhost/app/stream；输出实例另带 schema。同一业务流可能同时存在 rtsp、rtmp、hls 等条目。HTTP-FLV 通常消费 RTMP 源，不应预期出现名为 http-flv 的 MediaSource schema。

### RTSP 拉流、转封装和分发

1. WebApi::addStreamProxy 把工作提交到 poller，构造并保存 PlayerProxy。
2. PlayerProxy::play -> MediaPlayer 的 RTSP delegate -> RtspPlayer：进行 RTSP 握手、SDP/轨道建立和 RTP/RTCP 收取。
3. TCP interleaved 拆包，或 UDP socket 收包 -> RtpTrack::inputRtp。
4. onBeforeRtpSorted -> RTCP 接收统计；然后 PacketSortor::sortPacket 重排序。
5. RtspPlayer::onRtpSorted -> RtspPlayerImp::onRecvRTP -> RtspDemuxer::inputRtp，恢复压缩音视频 Frame。
6. Track delegate -> MultiMediaSourceMuxer；根据 ProtocolOption 分发到 RTSP、RTMP、TS、fMP4、HLS/MP4 等封装器。
7. 对应 MediaSource 缓存和注册；播放器 Session 查找源、附着 RingReader、在自己的 poller 回调发送数据。

“RTP 解包器中的 decode”是还原压缩帧，不能笼统描述成视频解码为 YUV 再编码。

存在重要分支：rtsp.directProxy=1 时，RtspPlayerImp 同时把排序后的原始 RTP 写入 RtspMediaSource；PlayerProxy 为 muxer 关闭重复的 RTSP 输出，其他协议仍走 Frame 转封装链。这条直通路径需要单独观测，不能假设所有 RTSP 输出都重打包。第一轮保留默认直通，后续做 directProxy=0 对照实验。

RTSP 推流入口是 RtspSession，和主动拉流 RtspPlayer 不同。测试源推送给源站，网关再主动拉取，避免用“FFmpeg 直接推到网关”冒充拉流验证。

### RingBuffer 与 MultiMediaSourceMuxer

MultiMediaSourceMuxer 管理轨道就绪、输出协议、缓存/录制及观看数汇总；按需开关影响是否持续生成某输出。

RingBuffer 按关键帧/GOP 缓存数据，并按 EventPoller 维护 dispatcher；一次写入向各 dispatcher 提交任务，在目标线程通知 readers。RTSP 缓存元素是 RTP 包列表的 shared_ptr，不是裸字节循环数组。

因此不能把它称为“完全无锁”或“全链路零拷贝”：write/attach 使用 _mtx_map，跨线程有任务分配与引用计数，协议封装和内核发送仍有成本。慢客户端风险要结合 Socket 发送队列、超时和 RSS 一起测试。

## 4. 已有能力及复用边界

| 能力 | 源码/文档证据 | 决策 |
| --- | --- | --- |
| RTSP 推拉、RTP TCP/UDP、RTCP、SDP | RtspPlayer、RtspSession、RtpReceiver | 直接复用；TCP 先跑通，UDP 用于质量实验 |
| RTMP、HTTP/WS-FLV | README、Muxer 的 RTMP 分支 | 首轮验证 RTMP/HTTP-FLV |
| HLS、HTTP/WS-TS、HTTP/WS-fMP4、MP4 | README、Muxer、构建/配置选项 | 首轮 HLS；其余后续兼容性用例 |
| WebRTC、WHIP/WHEP、SRT | README、对应编译开关 | 已有但延后启用；依赖和端口另验 |
| GB28181 RTP 媒体接入/发送 | README、RTP proxy API | 可复用媒体部分；不等于完整 SIP 国标业务平台 |
| 多路复用、GOP 缓存、按需转协议 | MediaSource、Muxer、RingBuffer | 直接复用；首轮显式关闭按需输出以稳定验收 |
| 代理重连 | PlayerProxy | 直接复用；不创建第二个常驻重连定时器 |
| 流列表、轨道、观看数、流量 | WebApi | API 封装与口径统一 |
| 丢包、RTCP jitter 内部计算 | RtspPlayer、RtcpContext | 先验证统计正确性；补齐安全导出和乱序等字段 |
| 帧级探针 | WebApi::addProbe | 已有 dts/pts/recv_stamp/frame_size/key_frame 等，优先复用 |
| Web 管理、SQLite 代理持久化 | PyMKUI | 下一轮配套接入 |
| 多备用源及重启恢复 | PullProxyFailover、PullProxyRestore | 复用并测试，不重复写数据库和切源调度 |
| 自动转码、全编码浏览器播放 | 存在专业版边界及客户端限制 | 不作为开源基线承诺；必要时外接 FFmpeg 单独测算 |

## 5. HTTP API、事件和状态口径

统一前缀 /index/api/。客户端必须同时校验 HTTP 状态和 JSON code；HTTP 200 不等于操作成功。secret 使用运行时私密配置，报告脱敏。

| API | 作用和注意事项 |
| --- | --- |
| addStreamProxy | 输入 vhost/app/stream/url 和输出选项；保留返回的 key，不自行猜 key；默认 retry_count=-1 |
| delStreamProxy | 用返回 key 删除；检查 data.flag，停止后验证不会重新拉流 |
| getMediaList | 查在线协议源和轨道/流量；不能把条目数当输入路数 |
| getMediaInfo | 查询具体 schema/vhost/app/stream；在 owner poller 上提供 tracks[].loss |
| getMediaPlayerList | 读取对应媒体源 reader 信息；不是“所有网络连接” |
| getProxyInfo | 按 key 获取 status、status_str、liveSecs、rePullCount、bytesSpeed、tracks |
| getThreadsLoad | poller 负载与延时；不能替代 OS CPU 使用率 |
| getStatistic | 框架对象等内部统计；不是完整主机资源监控 |
| getAllSession | 网络会话辅助排查；不能直接当观看人数 |
| addProbe | 短时帧级采样，按 probe_ms 返回 FrameInfo；不等同逐包 RTP 质量统计或端到端延迟 |

重要限制：
- WebApi 源码明确说明 getMediaList 忽略丢包统计，不能在列表中臆造 loss=0。
- 对 RTSP 拉流，getPacketLossRate 返回 lost/expected 的 0～1 比率，基于当前接收上下文；UI 才乘 100 展示百分数。其他来源路径的区间语义应另验。-1/缺字段显示“不可用”，不是零丢包。
- readerCount 是此协议源的 readers；totalReaderCount 是关联输出的汇总。同一业务流多行上的 totalReaderCount 不累加。它们是消费者连接语义，不是去重自然人；HLS 会话释放还有超时因素。
- getProxyInfo 的 status/status_str/rePullCount 仅作证据之一。当前代码中 _live_status 在构造、成功时更新，不能仅凭 status 判断断线；rePullCount 也不等于每一次连接尝试。
- 最终健康判定组合：代理是否存在、媒体注册、输入字节增量、轨道帧推进和实际解码探针。定义 desired_state 与 observed_state，区分 CONNECTING/ONLINE/DEGRADED/RECONNECTING/OFFLINE/STOPPED。

已有 Webhook：on_publish、on_play、on_stream_changed、on_stream_none_reader、on_stream_not_found、on_flow_report、on_server_started、on_server_keepalive 等。HTTP hook 有超时和有限重试，不能假定可靠消息队列或 exactly-once。后续接收端做幂等，周期 API 对账；鉴权 hook 和仅观测事件分离。

PyMKUI 的 on_player_proxy_failed 属于 Python 插件事件；不要把它凭空配置成已有 HTTP 同名 hook。Python 插件和 Webhook 的拦截顺序必须集成测试。

## 6. 重连能力及需验证的边界

PlayerProxy 在播放失败和 shutdown 时安排 rePlay，成功后清连续失败计数。默认最小 2 秒、最大 60 秒、步长 3 秒；公式是有界递增等待，不是指数退避，也没有据此确认随机抖动。

HTTP addStreamProxy 当前调用使用默认构造重连参数；不能把 C++ 构造参数名直接当成已支持的 HTTP 配置字段。retry_count、timeout_sec、force 已在 API 中确认。

初次拉流失败：force=false 会移除代理，不能假定它会常驻重试；force=true 可保留任务，但成功响应仅代表代理建立，不代表已有可播放视频。测试分别覆盖“源先启动”和“网关先建任务”。

general.resetWhenRePlay 默认为 1；设为 0 时有复用输出 muxer/轨道兼容判断路径，但直通 RTSP 源还会注销。不能保证所有输出、所有播放器无感恢复。源重连、MediaServer 进程重启、备用 URL 切换是三类独立恢复，分别验收；进程重启后的代理恢复优先用 PyMKUI 持久化能力。

## 7. 第一阶段部署拓扑与技术路线

测试拓扑：FFmpeg 测试图与音频 -> ZLM source 实例 -> RTSP 拉流 -> ZLM gateway 实例 -> 多协议客户端。

两个实例使用同一固定版本二进制，但独立配置、日志、PID、HTTP 根目录和 HLS 输出目录。
- source：RTSP 18554、HTTP 18081、RTMP 11935；只承接 testsrc。
- gateway：RTSP 8554、HTTP 18080、RTMP 1935；业务流 live/cam01。
- 首轮关 HTTPS、WebRTC、SRT、RTP proxy 监听和 shell；只在测试网络开放必要端口。UDP RTP 动态端口在下一轮明确规划。
- FFmpeg 生成 1280x720、25fps、H.264/yuv420p、GOP=25、无 B 帧，加 AAC 48 kHz 测试音。编码器能力须通过 ffmpeg -encoders 确认。
- FFmpeg 是向 source 推送 RTSP，不假设 ffmpeg -f rtsp 输出就是 RTSP 服务端。
- gateway 经 addStreamProxy 拉 rtsp://127.0.0.1:18554/test/source01，业务标识 __defaultVhost__/live/cam01。
- 基线 enable_rtsp/enable_rtmp/enable_hls=1，enable_mp4/enable_ts/enable_fmp4=0；按需输出关闭，auto_close 关闭；音频测试源真实存在，不靠静音注入掩盖问题。
- 预期播放地址：rtsp://HOST:8554/live/cam01、rtmp://HOST:1935/live/cam01、http://HOST:18080/live/cam01.live.flv、http://HOST:18080/live/cam01/hls.m3u8。以运行时返回和实际解码复核。
- 浏览器播放后续复用 PyMKUI；第一轮 FFmpeg/ffprobe/VLC 验收足够。网页不原生支持 RTSP。

Ubuntu 24.04 构建计划：
1. 核验 /etc/os-release、CPU/内存、磁盘、端口占用和联网；固定 VM vCPU/内存。
2. 安装 build-essential、cmake、ninja-build、git、pkg-config、libssl-dev，以及 ffmpeg、curl、jq、sysstat 等验证工具。
3. checkout 固定 ZLM SHA，递归拉取并记录所有子模块 SHA。其 .gitmodules 使用 Gitee，不直接替换成任意最新 GitHub HEAD。
4. 独立 build 目录，RelWithDebInfo；ENABLE_SERVER/PLAYER/HLS/MP4=ON，ENABLE_WEBRTC/SRT/SCTP/PYTHON=OFF，DISABLE_REPORT=ON。使用外部 FFmpeg，不必为测试源启用内部 FFmpeg 集成。
5. 保存 CMakeCache、依赖版本、编译命令和构建日志；检查实际功能摘要，防止依赖缺失后静默关闭能力。
6. 两实例前台运行并受脚本管理；稳定后再加 systemd。服务端采样隔离 FFmpeg 编码器和压测客户端的 CPU。
7. 在 Linux 本地文件系统编译，不把 Windows 共享目录 I/O 延迟混入性能基线。

## 8. 项目目录设计

以下为计划目录，不表示对应代码已创建。

| 路径 | 职责 |
| --- | --- |
| README.md | 项目范围、阶段状态与运行入口 |
| docs/phase-01-architecture.md | 本文：调研、架构和验收 |
| docs/adr/ | 依赖锁定、直通模式、统计口径等决策 |
| docs/runbooks/ | Ubuntu 部署、排障和复现实验 |
| docs/experiments/ | 每轮测试方法、结果和原始证据索引 |
| upstream.lock.json | 上游固定 revision，后续补全部子模块 |
| upstream/ZLMediaKit/ | 后续完整 checkout；不把不完整下载当完整仓库 |
| upstream/pymkui/ | 后续固定版本 checkout |
| config/source.ini.example | 源站实例模板 |
| config/gateway.ini.example | 网关配置模板；无真实 secret |
| scripts/bootstrap-ubuntu.sh、build-zlm.sh | 环境核验和可重复构建 |
| scripts/start.sh、stop.sh、status.sh、logs.sh | 生命周期操作 |
| scripts/start-test-source.sh、stop-test-source.sh | FFmpeg 测试源 |
| scripts/stream-add.sh、stream-remove.sh、stream-status.sh | 复用 HTTP API |
| tests/smoke/verify-multiplay.py | 多协议解码、观看数和状态验证 |
| tests/fault/ | 断源、网络故障、进程重启、恢复验证 |
| tests/quality/ | 可重复 RTP 包序列与 PCAP 对照 |
| tests/perf/ | 并发阶梯、资源采样、延迟和优化 A/B |
| modules/rtp-observer/ | 后续独立 C++ 统计模型与快照，非首轮 |
| patches/zlmediakit/ | 必要的最小接入补丁及上游 base SHA |
| runtime/、artifacts/ | 运行日志与测试产物，不提交凭据和大文件 |

Git 策略：MediaGateway 自己的仓库管理文档/配置/脚本/模块；上游 checkout 以 lock 固定，后续必要修改放独立分支并导出补丁，不直接改移动中的 master。每个小任务独立 commit，提交正文记录影响文件、调用链、风险、验证证据。未经用户指定不创建远程仓库或推送。

## 9. 第一轮开发任务：只完成最小可运行系统

本轮调研完成后，下一轮按下表顺序实施。每次修改前先报告实际拟改文件和风险，完成即提交。

| 任务 | 拟修改文件 | 调用链/主要风险 | 方法和验收标准 | 必须保存 |
| --- | --- | --- | --- | --- |
| T1 固定源码与构建 | lock、bootstrap/build 脚本 | 依赖/CMake -> MediaServer；子模块缺失、自动降级 | Ubuntu 24.04 干净构建成功，SHA/子模块匹配，二进制可启动并返回 API | 环境、依赖、CMakeCache、build.log |
| T2 两实例生命周期 | 两份配置、start/stop/status/logs | 脚本 -> 指定实例进程；端口冲突、误杀 | 启停连续 3 轮；重复 start 不增加实例，stop 不杀其他进程，端口释放 | PID/命令身份核验、实例日志、exit code |
| T3 测试源与 RTSP 拉流 | source 脚本、stream-add/remove | FFmpeg -> source -> PlayerProxy；推拉混淆、key 丢失 | 15 秒内媒体就绪，getMediaInfo 确认 H.264/AAC；输入字节持续增长 | FFmpeg 日志、API 脱敏 JSON、source/gateway 日志 |
| T4 多协议解码 | verify-multiplay.py | 4 个播放器 -> 源缓存/转封装；容器可读但不能解码 | RTSP/RTMP/HTTP-FLV/HLS 四路并行，每路解码 60 秒并产生视频帧；HLS 启动放宽至 20 秒；退出/错误明示 | 每协议解码日志、帧数、时长、退出状态 |
| T5 在线状态/观看数 | stream-status、smoke 用例 | API -> MediaSource/PlayerProxy；重复计数 | 独立 RTSP 计数用例，无其他客户端时做 0->1->3->0，10 秒内收敛；多协议另测，不把 HLS 超时混入 | 每秒 API 快照与客户端 PID 时间线 |
| T6 最小断源恢复 | tests/fault/basic-reconnect、runbook | 停 FFmpeg -> shutdown/rePlay -> 恢复；源保留状态 | 先观察 OFFLINE/RECONNECTING 证据；源恢复后 90 秒内重新解码，做 3 轮；允许客户端重连并记录 | 断源/恢复时间、代理快照、服务器与客户端日志 |
| T7 验证报告 | docs/experiments/首轮报告 | 汇总真实证据；日志凭据泄露 | 一键验证返回 0 仅当所有必需项 PASS；缺依赖为 SKIP/BLOCKED 且不能算总验收成功 | result.json、版本、配置摘要、日志哈希 |

测试脚本必须设超时和清理 trap；只能停止自己创建且已校验命令身份的进程。日志不记录 api.secret 或 RTSP 用户密码。无声、黑屏、ffprobe 返回成功但解码零帧均不能通过。

首轮不包含自研监控页面、Prometheus 集群部署、RTP 算法改造和性能优化。T6 只验证已有基本重连，完整故障矩阵留给第二阶段。

## 10. 后续工程模块与验收路线

### M1：RTP 质量观测

复用 onBeforeRtpSorted 和 RtcpContext，补齐按 stream/track/SSRC/session_generation 的只读快照。计数分为 received、unique、duplicate、reordered、late_dropped、expected、confirmed_lost；明确累计窗口和区间窗口，重连与 SSRC 切换重置基线。

乱序必须在排序前观测，不能在已排序的输出上估算。序号扩展要覆盖 65535->0、重复包、极迟到、发送端重启；不能简单将 seq 差当丢包。先确定 reorder window，再确认缺包；接收乱序与最终未恢复缺包分别报告。

Jitter 复用接收侧计算定义，内部单位为 RTP 时钟 tick，显示毫秒为 jitter_ticks*1000/clock_rate。不是网络 RTT，也不是播放端缓冲时长。TCP 有队头阻塞，不能用 TCP 模式声称验证了 UDP 丢包恢复。

新增 API 只从 owner poller 拷贝快照到 JSON，禁止逐包发 Webhook。FrameInfo 探针负责帧率/GOP/码率，不能替代逐包计数。

方法：可控序列先做确定性单测（0 丢包、固定缺 100/10000 包、重复、乱序、回绕、重启），再在隔离 network namespace/veth 用 tc netem 注入；使用抓包和已知发包日志对照，记录采集自身丢包。验收：确定性包计数精确匹配；jitter 与独立参考计算在声明的时钟分辨率误差内一致。netem 随机丢包配置不是实际丢包率真值。

源码风险：当前 RtcpContext 中 getLost() 直接以 expected-packets 相减，需要验证重复包/乱序对 size_t 统计的影响；createRtcpRR 的 fraction 表达式存在运算符优先级疑点，应以小型确定性回归用例验证后单独修复，不能把正确性修复当性能优化。现阶段未运行用例、未提交修复。

### M2：故障诊断与恢复

优先复用 PlayerProxy 重连和 PyMKUI 的 PullProxyRestore/PullProxyFailover。新增状态对账、健康判据、故障分类及时间线；同一路流只能有一个重连/切源控制者。

用例：连接拒绝、无媒体但 RTSP 连接存活、停源恢复、网络黑洞、鉴权失败、主动删除、MediaServer 重启、两备用 URL 轮转、重连后参数变化。验收目标：错误类型有证据；源恢复 90 秒内可再次解码；进程恢复后持久化任务可重建；主动删除不被后台复活；10 轮故障后无僵尸客户端/代理持续增长。参数和是否保连接分别记录。

### M3：首帧和端到端延迟

至少区分 API 请求完成、流注册、首个可解码帧、客户端首帧渲染四个时刻。API 成功和 probe recv_stamp 均不能当首帧渲染时间。

冷拉流/热流新观众分开，各协议至少 30 次，报告 P50/P95/最大值及 GOP、缓存配置。拟定无故障本机 RTSP/HTTP-FLV 热启动首帧 P95<=2 秒，HLS P95<=10 秒，需实测确认或有证据调整。

端到端使用同机公共时钟的可见时间戳/帧编号测试，或经校时的发送与显示时间戳，报告同步误差；记录真正渲染/屏幕采样而不是收到包时间。HLS 与低延迟协议分别报告，不预先承诺统一毫秒门槛。20% 变化小于测量误差时不得宣布优化。

### M4：多客户端与资源压测

阶梯 1/10/25/50/100 客户端；每档预热 30 秒、稳定 5 分钟，基线可用后增加 30 分钟稳态。按 RTSP TCP、RTSP UDP、HTTP-FLV 分开测，再测混合协议。

pidstat/sar/ss 与框架 API 同步记录 CPU（核数归一方式）、RSS/峰值、fd、网络吞吐、上下文切换、poller 负载、首帧失败、断连。明确播放器只拉包还是实际解码，两类场景不混用。FFmpeg 生成端、客户端尽量分机，至少进程独立计量。

验收：每档可复现并报告成功率/断连；无崩溃、无持续无界 RSS/fd 增长；找到瓶颈时记录容量上限而非承诺任意并发。容量还受输出码率*观看数及 VM NAT 限制。低于 100 路失败也必须报告真实结果。

### M5：一项经证据确认的 C++ 优化

先用 perf record/report 和火焰图找热点，再选择一个小改动。候选观察点为 RTP 缓存分配、跨 poller 分发任务、重复序列化；当前不认定任何一个已经是瓶颈。

要求记录“热点占比 -> 假设 -> 最小补丁 -> 相同负载 A/B -> 正确性/延迟回归”。每组至少 5 次交替运行，同机、同编译器/配置/GOP，客户端无瓶颈；报告中位数和波动。拟定目标：相同成功率/吞吐下 CPU 中位数降低 >=5%，或固定资源下有效吞吐提升 >=10%；P95 延迟不恶化超过 5%、无数据完整性/生命周期回归。若差异未超出波动，结论必须是“未证明收益”，保留实验记录但不合入优化。

涉及上游文件时预先列调用链及对象所有权/线程风险；必要单测和 ASan 回归另跑，不能把 ASan 版用于 release 性能对比。

## 11. 主要风险及应对

| 风险 | 应对 |
| --- | --- |
| 仓库版本漂移、子模块混搭 | 锁定 ZLM 与 gitlink；PyMKUI 兼容性单测后才能成为默认安装项 |
| 只有 Windows 会话，无法 Ubuntu 执行 | 先取得可用 VM/SSH 会话，不虚构 Linux 编译或播放结果 |
| H.265/AAC 与浏览器能力不匹配 | H.264/AAC 基线，WebRTC 音频独立兼容矩阵 |
| 只看注册/回调就认为恢复 | 输入增长 + 解码探针 + 状态快照联合判断 |
| 默认按需、无人关流、重连重建导致误判 | 模板显式固定关键配置，测试冷/热路径 |
| 重复统计 viewers/不同协议源 | 按业务流去重，schema 维度单独展示，不求和重复 total |
| 统计本身有边界问题 | 逐包确定性测试，缺字段不填 0，保存原始抓包 |
| 插件阻塞事件循环或重复控制重连 | 小型异步观测；切源控制权单一；重任务外移 |
| 慢客户端堆积/VM 资源影响压测 | 发送队列、RSS、fd 和 poller 同测；隔离编码端和客户端 |
| PyMKUI 数据结构快速变化 | 固定版本、升级前备份和迁移评估，不照 README 删除用户数据库 |
| secret 和输入 URL 泄露 | 不提交真实配置；日志脱敏；管理接口只开放可信网络 |
| 提前优化或重复实现 | 每项先查现有接口，优化以 profile 和 A/B 证据准入 |

## 12. 本轮交付与未完成事项

已完成：固定版本的关键源码调研、复用清单、线程/媒体调用链、最小部署拓扑、项目目录、首轮任务及后续测试设计。

未完成：完整仓库 clone、Ubuntu 安装/编译、测试视频推拉、多协议播放、重连实测、压测、性能优化。此文不包含任何实际性能结论。

下一轮从 T1 开始，先解决 Ubuntu 执行入口和完整源码获取；按 T1～T7 分小提交推进，不一次性加入 M1～M5。

