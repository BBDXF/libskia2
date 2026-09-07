# libskia2

预编译的**定制 Skia 静态库**，面向自绘 GUI 框架。用自己掌控的 GN 配置构建，
替代对 rust-skia/skia-binaries 等第三方产物的依赖。

构建管线参考 `Shopify/react-native-skia`，但它只覆盖 Android/Apple——
本项目做的 Linux 与 Windows 正是它没有的部分。

## 范围

| 项 | 决定 |
|---|---|
| 消费方 | C++ 项目，直接调用 Skia C++ API |
| 用途 | 自绘 GUI 框架 |
| 平台 | `linux-x64`、`windows-x64-msvc` |
| Skia 版本 | `chrome/m153`，pin 到具体 commit（`config/skia.pin`） |
| 产物 | 7 个静态库 + 头文件包 + CMake package |

## 功能面

| 能力 | 决定 |
|---|---|
| 渲染 | Ganesh + GL + CPU 光栅；Linux 不链 `libGL`，X11 与 Wayland 通吃 |
| 文本 | skparagraph + skshaper + **libgrapheme**（grapheme / 断词 / UAX#14 断行 / BiDi 全有，**无 `icudtl.dat` 依赖**） |
| 系统字体 | Linux fontconfig，Windows DirectWrite |
| 矢量图标 | SVG（`SkSVGDOM`），同时带入 `SkPathOps` 与 `skresources` |
| 图片 | PNG / JPEG / WebP 编解码 + GIF 解码 |
| 已关闭 | PDF、XPS、RAW/DNG、Skottie、Graphite/Dawn、Vulkan、AVIF、JPEG XL、Perfetto、PartitionAlloc |

理由与实测依据见 [GUI 框架配置档](doc/gui-framework-profile.md)。

## 实测基线（v0.1.0）

冒烟测试在两个平台各 11 项断言全通过。**关键的三条验证了 libgrapheme 能替掉完整 ICU**：

```
unicode.grapheme.zwj    PASS   期望 1 簇，实得 1      ZWJ 家族 emoji
unicode.lineBreak.cjk   PASS   软断点数 18            UAX#14 中文断行
unicode.bidi            PASS   区段数 3，含 RTL: 是   自带 icu_bidi 子集
```

| | linux-x64 | windows-x64-msvc |
|---|---|---|
| `libskia` | 23 M | 40 M |
| `libskshaper` | 8.4 M | 17 M |
| `libsvg` | 8.4 M | 13 M |
| `libskunicode_libgrapheme` | 938 K | 1.1 M |
| `libskparagraph` | 581 K | 1.7 M |
| `libskresources` | 46 K | 116 K |
| `libskunicode_core` | 23 K | 29 K |
| **发布包 tar.gz** | **15.1 MiB** | **21.5 MiB** |
| **链接后可执行文件** | **6.4 M** | **5.0 M** |

最后一行才是有意义的体积指标。注意 Windows 的静态库明显更大，链接后的二进制反而更小——
`.a` / `.lib` 里含大量未被引用的 section 与元数据，拿它衡量体积没有意义。

## 消费方怎么用

解压 release 里的 tarball，把包目录传给 `CMAKE_PREFIX_PATH`：

```cmake
find_package(skia2 REQUIRED)
target_link_libraries(my_gui PRIVATE skia2::skia2)
```

一行。7 个静态库的链接顺序、include 路径、系统库、C++20 与 ABI 约束
全部由 `skia2::skia2` 声明好，不需要手写。

Skia 的头文件之间用根相对路径互相引用，所以包含时也带上根前缀：

```cpp
#include "include/core/SkCanvas.h"
#include "modules/skparagraph/include/ParagraphBuilder.h"
```

外部依赖只有 Linux 上的 `libfontconfig1-dev`——Skia 从不 vendor fontconfig。
其余（zlib / expat / libpng / libwebp / libjpeg-turbo / harfbuzz / freetype /
libgrapheme / icu_bidi / wuffs / skcms）全部编译进 `libskia.a`。

## 发版

GitHub Actions → `build` → Run workflow，填版本号（如 `0.1.0`）。
或者打 tag：`git tag v0.1.0 && git push --tags`。

两个平台并行构建（各约 40–60 分钟），各自跑完冒烟测试后打包，
最后由 `release` job 汇总上传到 Release。勾 `dry_run` 则只产出 workflow artifact，不建 Release。

## 本地构建

```sh
python3 scripts/libskia2.py all --target linux-x64
```

或分步执行 `sync` / `gen` / `build` / `package`。
Windows target 必须在 Windows 上跑，脚本会拦住跨平台调用。

## 改配置改哪里

| 想改什么 | 改哪个文件 |
|---|---|
| 开关某个 Skia 功能 | `config/common.gn.args` |
| 平台专属参数（工具链、字体后端、CRT） | `config/{linux-x64,windows-x64-msvc}.gn.args` |
| 换 Skia 版本 | `config/skia.pin`（CI 会校验 commit，漂移即失败） |
| 增删产出的静态库 | `scripts/libskia2.py` 的 `BUILD_TARGETS` 与 `EXPECTED_LIBS` |
| 消费方看到的链接顺序 / 系统库 / ABI | `cmake/skia2Config.cmake.in` |

**产物清单是硬校验**：某个 GN arg 让模块静默消失时，`build` 步骤立刻失败，
而不是留到消费方链接时才发现。

## 冒烟测试

CI 里是发版的闸门，验证的不是"能编过"，而是配置选择是否成立：

| 用例 | 验什么 |
|---|---|
| `unicode.grapheme.*` | ZWJ 家族 emoji / 肤色修饰符 / 区域指示符旗帜各算 1 个簇——光标与退格的正确性 |
| `unicode.lineBreak.cjk` | 中文无空格文本能给出 UAX#14 断点——**libgrapheme 方案的关键一条** |
| `unicode.words` | 词边界，双击选词依赖它 |
| `unicode.bidi` | libgrapheme 自带的 icu_bidi 子集确实工作，RTL 能力不缺 |
| `raster.*` | CPU 光栅 + 渐变 + 模糊阴影 + PNG 编解码 |
| `svg.render` | SkSVGDOM 解析并渲染出非透明像素 |
| `paragraph.layout` | SkParagraph 在窄宽度下真的换行 |

任何一条不过，说明 libgrapheme 文本方案不够用，需要回退到完整 ICU
（`skia_use_icu=true` + `skia_use_libgrapheme=false`，代价见配置档 §4）。

CI 会把 tarball 体积、各静态库体积、以及**冒烟测试二进制的体积**
写进 workflow summary。最后一项才是有意义的体积基线——`.a` 的大小含大量未引用 section。

## 已知的尖锐边缘

- **Windows 上传播 `_HAS_EXCEPTIONS=0`**。Skia 硬编码此宏（不是 GN arg），它改变 MSVC STL 头的行为，
  跨 TU 不一致即 ODR 违规。CMake package 会把它传播给消费方，也就是说**宿主应用在 Windows 上同样是无异常的**。
  要改必须重建 libskia2 并打 patch，消费方侧去掉定义只会把问题藏起来。
- **RTTI 关闭**（`-fno-rtti` / `/GR-`）。消费方自己的 `dynamic_cast` 不受影响，但不能对 Skia 类型用。
- **Windows CRT 定为 `/MD`**（`config/windows-x64-msvc.gn.args`）。一次性决策，改它等于要求所有消费方同步改。
- **Windows 侧系统库清单未经实测**。GN 只显式声明了 `opengl32`；DirectWrite/COM 那组是补的，
  以首次 CI 运行的链接结果为准。
- **`SkPathOps` 由 `modules/svg` 隐式带入**。若将来关掉 SVG，它会消失且只在链接期报错。

## 文档

- [GUI 框架配置档](doc/gui-framework-profile.md) —— 配置的依据：功能倒推、三个 GUI 特有的坑、
  产物清单、消费方要引用什么、冒烟测试清单
- [定制面分析](doc/customization-analysis.md) —— 通用参考：九个定制轴、m153 实测默认值、
  暗雷清单、ABI 契约
- `doc/research-raw/` —— 早期调研笔记，基于 m120，含已知错误，仅作线索
