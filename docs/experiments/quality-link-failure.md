# 扩展版 JsonCpp 链接失败

用户日志：2026-11-16，链接 MediaServer 时 WebHook.cpp 引用
Json::Value::operator[](std::basic_string_view<...>)，ld 报 undefined reference，构建失败。
证据目录：/home/zkb/MediaGateway/artifacts/quality-build/20261116T113124Z-4597。
尚未激活扩展版。

源码核对：固定版本根 CMakeLists.txt 设置 CMAKE_CXX_STANDARD 11，3rdpart 先生成 jsoncpp 静态库；
本项目在后续 src/CMakeLists.txt 向 zlmediakit 加入 PUBLIC cxx_std_17，向 MediaServer 传播，
但不会向已定义的 JsonCpp 依赖反向传播，造成调用方和库的条件接口不一致。
这与 string_view 符号缺失一致；未取得用户完整 compile_commands，不能声称已经逐条审阅其编译命令。

修复：不升级上游依赖标准；模块使用 C++11 兼容命名空间并移除 C++17 传播。
序号分类算法未改变。新增实际编译命令标准一致性检查，以及受限的 --resume 续建入口。
本地 Python 语法、--help 和三项编译标准检查测试通过。
修复后 C++11 单元测试、MediaServer 链接与运行结果待用户 Ubuntu 验证。
