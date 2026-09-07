cmake_minimum_required(VERSION 3.24)
project(libskia2_smoke LANGUAGES CXX)

# 这个测试同时是消费方用法的示例：找到 package，链一个 target，完事。
# 7 个静态库、链接顺序、系统库、ABI 约束全部来自 skia2::skia2。
find_package(skia2 REQUIRED)

add_executable(libskia2_smoke smoke.cpp)
target_link_libraries(libskia2_smoke PRIVATE skia2::skia2)

# 只在冒烟测试里开，用来证明产物在 --gc-sections 下依然自洽。
if(NOT MSVC)
  target_link_options(libskia2_smoke PRIVATE -Wl,--gc-sections)
endif()

message(STATUS "skia2 version: ${SKIA2_VERSION} (${SKIA2_TARGET})")
message(STATUS "skia2 include: ${SKIA2_INCLUDE_DIR}")
