# C++ RTP 质量统计：第一轮

## 基线与范围

进入核心扩展阶段。本轮新增独立库 mg_rtp_quality 和确定性测试；当前使用 C++11 与上游一致，
不是新的媒体服务器，也不改变上游丢包/Jitter 算法。
产物：include/mediagateway/quality/RtpSequenceStats.h、src/quality/RtpSequenceStats.cpp、
tests/rtp_sequence_tests.cpp、根 CMakeLists.txt、scripts/test-quality.sh。
本轮库尚未接入真实 RTP、HTTP API 或页面；页面继续显示质量指标尚未接入。

## 上游证据与后续接入点

基于固定提交 fb3265725f0880da1f52a3cc6e6eb04bbc327fa3：

- src/Rtsp/RtpReceiver.cpp：RtpTrack::inputRtp 在头部、PT、SSRC 校验后创建包；
  然后 onBeforeRtpSorted(rtp) → sortPacket(seq, rtp) → onRtpSorted。
- RtpTrackImp 已提供 setBeforeSorted 回调；下一轮检查具体 RTSP 拉流实例对该回调的使用，
  必须保留已有 RTCP 调用，不直接覆盖回调。实际接入方式尚未验收。
- src/Rtcp/RtcpContext.cpp：RtcpContextForRecv 已实现接收序号、丢包和 Jitter 相关统计。
  Jitter 使用 RTP 时钟单位，展示毫秒时需结合轨道时钟频率；暂不重写。

源码链接：
https://github.com/ZLMediaKit/ZLMediaKit/blob/fb3265725f0880da1f52a3cc6e6eb04bbc327fa3/src/Rtsp/RtpReceiver.cpp
https://github.com/ZLMediaKit/ZLMediaKit/blob/fb3265725f0880da1f52a3cc6e6eb04bbc327fa3/src/Rtcp/RtcpContext.cpp

## 序号统计口径

每个接收轨道、每个 epoch 一个对象。只读合法 RTP 包的 uint16_t 序号，不解析或保留媒体负载。
回调采样表示应用观察到的到达顺序；尤其 TCP 模式下，不等于网卡层的网络乱序。

| 字段 | 定义 |
| --- | --- |
| received | observe 调用总数，包含所有分类 |
| unique | 在可判定范围内首次观察到的包 |
| reordered | unique 的子集；首次观察到且扩展序号小于当前最大值 |
| duplicates | 最近 1024 个序号范围内能够证明已经观察到的包 |
| too_old | 早于首个采样序号，或落后最大序号至少 1024；无法区分首次迟到与重复 |
| discontinuities | 正向跨越超过 3000，或恰好半个序号空间 32768；不更改历史 |
| highest_extended | 本 epoch 内最高已接受扩展序号 |
| epoch | 显式 reset 的次数，构造时为 0 |

恒等式：received = unique + duplicates + too_old + discontinuities。
不能将缺口立即作为丢包，也不能把 too_old 当重复。
unique/reordered 都只对观察起点以后的保留窗口有效，不推断开始采样前的数据。
序号环绕用模 65536 差值展开；超过半个序号空间的延迟无法仅靠序号区分，属于明确限制。
3000 是本模块初版异常步长阈值，不宣称完整实现 RFC 序号有效性/probation 算法。
连续大跳变可能一直被拒绝，必须由连接生命周期/SSRC 变化触发 reset，不擅自推断源重启。

## 实现与线程边界

固定 std::array 保存 1024 个扩展序号标签（约 8 KiB/轨道），扩展标签避免回绕后槽位假重复。
observe 无动态内存分配、无锁，常数次访问；这是实现结构描述，不是性能测试结论。
不是线程安全容器：observe、reset、snapshot 都必须在同一 owner EventPoller 调用，
将 Snapshot 按值复制后交给其他线程。不允许 HTTP 工作线程直接读取正在更新的对象。
重连、已确认 SSRC 切换时 reset；不能继承上一 epoch 的去重历史。

## 运行与验收

```bash
cd ~/MediaGateway
bash scripts/test-quality.sh
```

与 upstream/ZLMediaKit 和 build/zlm-* 隔离，生成 build/quality。
CTest 包含一个测试可执行文件，内部逐项输出 11 个命名用例。
覆盖 seq=0、顺序包、重复与乱序分离、迟到后重复、回绕前后乱序、140000 包多次回绕、
窗口边界、采样前包、异常大跳变、3000 边界、重启清零、双轨独立。
不用 assert，因此 RelWithDebInfo/Release 下仍执行检查。

验收：11 个用例均 PASS、failures: 0、CTest 100% tests passed。
日志保存 artifacts/quality/<UTC时间-PID>/test.log，包括编译器、CMake 和完整测试输出。
本地 Windows 未发现可用 C++ 编译器，尚未编译或执行这 11 个测试，不能记为通过。
本轮未提交任何真实媒体统计结果或性能收益。

## 下一轮接入条件

先完成以上 C++ 验收，再实现最小上游适配补丁、轨道 epoch 生命周期和只读 API 快照。
然后以可控 RTP 序列验证接收回调与 API 一致，再运行四协议回归，最后接页面。
不通过管理页面发送假统计，也不以 UDP 网卡抓包旁路替代 RTSP/TCP 接收链路验证。
