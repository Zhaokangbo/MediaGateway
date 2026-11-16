# 独立 C++ 序号统计验收

用户于 2026-11-16 贴回 Ubuntu 24.04 的完整构建/测试输出。
GCC 13.3.0、CMake 3.28.3，成功生成 libmg_rtp_quality.a 与 rtp_sequence_tests。
11 个内部命名用例全部 PASS，failures: 0；CTest 一个测试程序通过。
测试总耗时显示 0.01 秒，仅是本次测试耗时，不是性能基准。

证据：`/home/zkb/MediaGateway/artifacts/quality/20261116T104314Z-3927/test.log`。
该结果不证明真实 RTP 接入、API 导出、协议回归或性能。
