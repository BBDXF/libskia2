# GUI 框架配置档

> 回答一个问题：**做一个支持常见功能的自绘 GUI 框架，Skia 的 gn args 怎么配。**
> 通用定制面见 [customization-analysis.md](customization-analysis.md)，本文只给结论和 GUI 特有的取舍。
> 证据基准同前：`google/skia@chrome/m153`。

---

## 1. 从功能倒推：GUI 框架要 Skia 提供什么

| GUI 常见功能 | 需要 Skia 的 | 对应 gn arg | m153 默认 |
|---|---|---|---|
| 矩形 / 圆角 / 边框 / 任意路径 | core（`SkPath` `SkPaint` `SkRRect`） | — | 内建，关不掉 |
| 渐变 / 阴影 / 模糊（毛玻璃） | core（`SkGradientShader` `SkImageFilters::Blur` `SkMaskFilter`） | — | 内建 |
| 裁剪 / 图层 / 节点 opacity | core（`saveLayer`） | — | 内建 |
| 变换 / 动画插值 | core（`SkMatrix` `SkM44`） | — | 内建 |
| 绘制命令录制与重放 | core（`SkPicture`） | — | 内建 |
| GPU 加速 | Ganesh + GL | `skia_enable_ganesh` `skia_use_gl` | ✅ 默认开 |
| CPU 光栅（黄金图测试 / 无 GPU 回退） | core（`SkSurfaces::Raster`） | — | 内建 |
| 色彩管理 | skcms | — | 内建 |
| **文字显示** | `SkFont` / `SkTextBlob`（core） | — | 内建 |
| **文字 shaping**（连字 / 阿拉伯语塑形） | skshaper + HarfBuzz | `skia_use_harfbuzz` | ✅ 默认开 |
| **段落布局**（换行 / 对齐 / 多样式 span） | skparagraph | `skia_enable_skparagraph` | ✅ |
| **光标移动 / 退格 / 双击选词** | skunicode（grapheme + word） | `skia_use_libgrapheme` 或 `skia_use_icu` | ⚠️ 默认走完整 ICU |
| **CJK 断行**（中日韩无空格分词） | skunicode（UAX#14） | 同上 | 同上 |
| **RTL / 阿拉伯语 / 希伯来语** | skunicode（BiDi） | 同上 | 同上 |
| Emoji 彩色字体（CBDT/sbix/COLR） | core 的 typeface 层 | — | 内建；**回退链要自己建** |
| 系统字体发现 | fontmgr | Linux `skia_use_fontconfig`；Win `skia_enable_fontmgr_win` | ✅ 各自默认开 |
| 图标（矢量） | svg 模块 | `skia_enable_svg` + `skia_use_expat` | ✅ |
| 图片显示 PNG/JPEG/WebP | codec | `skia_use_lib{png,jpeg_turbo,webp}_decode` | ✅ 全默认开 |
| 动图 GIF | wuffs | `skia_use_wuffs` | ✅ |
| 截图 / 位图缓存落盘 | encoder | `skia_use_libpng_encode` | ✅ |
| Lottie 动画 | skottie + sksg + jsonreader | `skia_enable_skottie` | ✅ 默认开，**本轮决定关掉**，见 §4.1 |

**结论**：GUI 框架需要的东西，Skia 默认几乎全开着。真正的定制工作是**减法** ——
关掉 PDF/RAW/XPS/Perfetto 那一堆，以及**在文本栈上做一次关键选择**。

---

## 2. 三个 GUI 框架特有的坑

### 2.1 `skia_enable_optimize_size=true` 对 GUI 框架是个陷阱

它给的是 `-Oz`（MSVC `/Os`）。GUI 框架的第一指标是**帧时间**，不是体积——
光栅化和 text shaping 都在每帧的关键路径上，`-Oz` 会直接吃掉这部分性能。

**建议：先不开。** 顺序应该是：
1. P0 用 `-O3` 建立**帧时间基线**和**体积基线**
2. P2 再单独开一次 `-Oz`，同时测两个数
3. 拿到"省了多少 KB / 慢了多少 ms"再决定

这与"首要目标是裁剪体积"直觉相反，但 GUI 框架里体积不该用帧时间去换。
真正无痛的体积收益在 §3 的减法清单里，不在 `-Oz`。

### 2.2 GL 后端的链接依赖在两个平台上不对称（实测 `BUILD.gn` L985–L1022）

| 配置 | 编进去的 interface | 链接依赖 |
|---|---|---|
| Linux + `skia_use_x11=true` | `GrGLMakeNativeInterface_glx.cpp` | **链 `libGL`** |
| Linux + `skia_use_egl=true` | `GrGLMakeNativeInterface_egl.cpp` | **链 `libEGL`** |
| Linux，两者都 `false` | **`GrGLMakeNativeInterface_none.cpp`** | **不链任何 GL** |
| Windows（`skia_use_gl=true`） | `GrGLMakeNativeInterface_win.cpp` | **总是链 `OpenGL32.lib`** |

**对一个要被别人嵌入的 GUI 框架，Linux 上必须选第三种**：`skia_use_x11=false` + `skia_use_egl=false`。

理由：这样出来的一套二进制**同时能跑 X11 和 Wayland**——GL 函数指针由你的窗口层
（SDL / GLFW / 原生）在运行时通过 proc loader 提供，Skia 侧不做任何假设。
一旦编进 GLX，产物就被钉死在 X11 上，且多一个 `libGL` 的运行时依赖。

代价：你必须自己调 `GrGLInterfaces::MakeAssembled(...)` 之类的组装接口，不能用 `MakeNative`。
这对 GUI 框架是应该做的事，不是负担。

Windows 侧没有这个选择——`OpenGL32.lib` 是系统库，一直在，可以接受。

### 2.3 `icudtl.dat` 的分发问题，可以直接消失

完整 ICU 方案（`skia_use_icu=true`）在 Windows 上默认要求 `icudtl.dat` 与可执行文件同目录。
对一个**要被别人嵌入**的 GUI 框架，这是很糟糕的契约：你的库要求宿主应用在特定位置放一个数据文件。

`skia_use_libgrapheme=true` 让这个问题整体消失——所有 Unicode 数据表编译进静态库。

而且（见 customization-analysis §5 实测）**libgrapheme 后端在 m153 里自带 icu_bidi 子集**，
grapheme / 断词 / UAX#14 断行 / BiDi 四项全有。GUI 框架真正会用到的能力一项不缺。

失去的是：分句迭代、locale 敏感大小写、UTF-16 代码路径、泰语/老挝语/高棉语的词典分词。
**对绝大多数 GUI 框架，这四项都不构成阻塞。**

---

## 3. 推荐配置

### 3.1 公共

```
# ---- 构建形态 ----
is_official_build=true
is_debug=false
is_component_build=false
skia_enable_tools=false
skia_enable_optimize_size=false       # §2.1：GUI 框架先别开，P2 再评估

# ---- 暗雷，必关 ----
skia_use_partition_alloc=false        # Linux+clang 默认 true，会导致 raw_ptr 链接错误

# ---- 渲染后端 ----
skia_enable_ganesh=true
skia_use_gl=true
skia_enable_graphite=false
skia_use_dawn=false
skia_use_vulkan=false                 # 一期不开，需要时单独出 variant
skia_enable_precompile=false
skia_enable_discrete_gpu=false

# ---- 文本栈（GUI 框架的核心）----
skia_use_harfbuzz=true
skia_use_system_harfbuzz=false
skia_enable_skparagraph=true
skia_use_libgrapheme=true             # ← 关键选择，见 §2.3
skia_use_icu=false
skia_use_bidi=false                   # 不需要：libgrapheme 已自带 bidi
skia_use_icu4x=false
skia_use_client_icu=false

# ---- 图标与矢量 ----
skia_enable_svg=true
skia_use_expat=true                   # svg → :xml → expat，必须一起开

# ---- 图像 ----
skia_use_libpng_decode=true
skia_use_libpng_encode=true
skia_use_libjpeg_turbo_decode=true
skia_use_libjpeg_turbo_encode=true
skia_use_libwebp_decode=true
skia_use_libwebp_encode=true
skia_use_wuffs=true                   # GIF

# ---- 减法：默认开着但 GUI 框架不需要的 ----
skia_enable_skottie=false             # Lottie，不做；见 §4.1
skia_enable_pdf=false
skia_use_xps=false
skia_use_dng_sdk=false                # RAW，体积大户
skia_use_piex=false
skia_use_perfetto=false
skia_use_libavif=false
skia_use_crabbyavif=false
skia_use_libjxl_decode=false
skia_use_fontations=false
skia_use_lua=false
skia_use_ffmpeg=false                 # skresources 会引用 ffmpeg video_decoder，保持关闭使其成为空目标

# ---- 第三方一律用 Skia 自带，不用系统库 ----
skia_use_system_libjpeg_turbo=false
skia_use_system_libpng=false
skia_use_system_libwebp=false
skia_use_system_zlib=false
skia_use_system_expat=false
skia_use_system_icu=false
```

### 3.2 linux-x64 追加

```
target_os="linux"
target_cpu="x64"
cc="clang"
cxx="clang++"

skia_use_x11=false                    # §2.2：不链 libGL，X11/Wayland 通吃
skia_use_egl=false
skia_use_freetype=true
skia_use_fontconfig=true              # 见 §5 的取舍
skia_enable_fontmgr_fontconfig=true
skia_enable_fontmgr_custom_directory=true
skia_enable_fontmgr_custom_embedded=true

extra_cflags=["-ffunction-sections","-fdata-sections"]
```

### 3.3 windows-x64-msvc 追加

```
target_os="win"
target_cpu="x64"

skia_use_freetype=false               # 用 DirectWrite
skia_enable_fontmgr_win=true
skia_enable_fontmgr_win_gdi=false     # 有 DirectWrite 就不要 GDI 路径
skia_enable_winuwp=false

extra_cflags=["/MD"]                  # 不加则落到 /MT，消费方用 /MD 会 CRT 冲突
```

> `/MD` vs `/MT` 是一次性决策，定了就不能改（见 customization-analysis §2.G）。
> 一个"给别人嵌入"的 GUI 框架建议 `/MD`——大多数 Windows 应用是 `/MD`，强制宿主改 `/MT` 不现实。

> Windows 上**不用 fontconfig**。系统字体发现由 DirectWrite（`skia_enable_fontmgr_win`）承担，
> 这是 Windows 上的正确做法；fontconfig 在 Windows 上既不常见也无必要。
> 框架层需要把 fontconfig 与 DirectWrite 抽象成同一个字体来源接口。

---

### 3.4 产物清单

上述配置应当产出以下静态库。**构建脚本必须按名字逐个校验，缺一个即 fail**
（见 customization-analysis §8.1）——否则某个 arg 改动导致 module 静默消失，
要到消费方链接失败时才会发现。

| 产物 | 来源 | 由什么开关带来 |
|---|---|---|
| `libskia.a` | `skia_component("skia")` | 核心，恒有 |
| `libskshaper.a` | `modules/skshaper` | `skia_use_harfbuzz` |
| `libskparagraph.a` | `modules/skparagraph` | `skia_enable_skparagraph` |
| `libskunicode_core.a` | `modules/skunicode` | 派生 `skia_enable_skunicode` |
| `libskunicode_libgrapheme.a` | 同上 | `skia_use_libgrapheme` |
| `libsvg.a` | `modules/svg` | `skia_enable_svg` |
| `libskresources.a` | `modules/skresources` | **svg 的依赖**（不是 skottie 专属） |

共 7 个。链接顺序（静态库有顺序要求）：
```
skparagraph → skshaper → skunicode_libgrapheme → skunicode_core
svg → skresources
skia
```

### `SkPathOps` 的归属（关掉 Lottie 后依然成立）

实测 `BUILD.gn` L1243：`pathops` 是 `skia_source_set` 而非 `skia_component`，
`skia_component("skia")` 的 deps 里**没有它**。依赖 `:pathops` 的只有四个目标：
`pdf`、`xps`、`modules/skottie`、**`modules/svg`**。

本配置关了 pdf / xps / skottie，但**开了 svg**（`modules/svg/BUILD.gn` L22 明确
`deps = ["../..:pathops", ...]`），因此 pathops 的目标文件被折叠进 `libsvg.a`，
`SkPathOps::Op()` / `Simplify()` 等符号可以正常解析。

**但这仍是一个隐式依赖，要记在案**：若将来把 SVG 也关掉，`SkPathOps` 会连带消失，
报错形式是链接期 undefined symbol 而非编译错误。届时应当加一个把 `:pathops`
包成独立 `static_library` 的小 patch，而不是靠别的模块顺带带进来。

---

## 4. 按需加开的档位

| 需求 | 追加 args | 代价 |
|---|---|---|
| Lottie 动画 | `skia_enable_skottie=true` | +3 个 `.a`；见 §4.1 |
| Vulkan 后端 | `skia_use_vulkan=true` | 明显体积增长；建议出独立 variant 而非默认开 |
| AVIF 图片 | `skia_use_libavif=true` 或 `skia_use_crabbyavif=true` | 中等 |
| 导出 PDF | `skia_enable_pdf=true` | 大 |
| 完整 Unicode（分句 / 泰语词典分词 / locale 大小写） | `skia_use_icu=true` + `skia_use_libgrapheme=false` | **最大单项**，且带回 `icudtl.dat` 分发问题 |

---

## 4.1 关于 Lottie 的决定

**已决定：不做。** 但把判断依据记下来，避免将来重新辩论。

需要澄清一点：**Lottie 的构建复杂度其实很低**——`skia_enable_skottie` 在 m153 里
默认就是 `true`，开启它是零配置工作，只是链接行上多 3 个 `.a`
（`libskottie.a` / `libsksg.a` / `libjsonreader.a`；`libskresources.a` 因为 SVG 也要，本来就有）。

真正的复杂度不在构建，在**框架集成**：

| 事项 | 说明 |
|---|---|
| 动画时钟 | Lottie 需要被逐帧驱动，要接进框架的 vsync 帧循环和失效机制 |
| 内嵌资源加载 | `.json` 里可引用图片和字体，需要实现 `skresources::ResourceProvider` |
| 生命周期与缓存 | 动画实例的创建/暂停/销毁、多实例共享解析结果 |
| 与布局的交互 | 动画尺寸、缩放模式、是否参与内在尺寸计算 |

这几项加起来是实打实的一个子系统，而不是"链上库就能用"。既然当前不需要，就不做。

**关掉的连带影响已核实为零风险**：`SkPathOps` 由 `modules/svg` 带入（见 §3.4），
不依赖 skottie；`libskresources.a` 也由 svg 需要，仍然会产出。

将来要加回来时，改一个 arg + 补 3 个产物名 + 实现 `ResourceProvider`，
不涉及任何已有配置的返工。

---

## 4.2 这份配置到底还在裁什么

需求确定为 fontconfig + PNG/JPEG/WebP/GIF + SVG（不含 Lottie）之后，剩下的减法：

| 仍然在裁的 | 性质 |
|---|---|
| PDF + XPS 后端 | **大**，纯粹用不到 |
| RAW/DNG（`dng_sdk` + `piex`） | **大**，纯粹用不到 |
| Skottie + sksg + jsonreader | **中**，本轮决定不做 |
| Graphite / Dawn / Vulkan / ANGLE | 大，一期不需要 |
| Perfetto tracing SDK | 中，Linux 上默认开着 |
| PartitionAlloc | 中，且不关会有链接错误 |
| AVIF / JPEG XL | 中 |
| 完整 ICU → libgrapheme | **最大单项**，且解决 `icudtl.dat` 分发问题 |
| Fontations（Rust 字体后端） | 中 |
| X11/EGL 绑定 | 小，但换来 X11+Wayland 通吃 |
| GDI 字体路径、discrete_gpu、precompile | 小 |

**诚实的预期**：这不会是一个"极小"的 Skia。开了 SVG + 四种 codec + 完整文本栈之后，
产物规模主要由这些功能本身决定。真正省下的大头是 PDF/XPS/RAW/Perfetto/Graphite
这几块**纯粹的死重量**，加上用 libgrapheme 换掉完整 ICU。

如果最终体积仍超预算，下一步的杠杆按顺序是：
1. 砍掉 SVG，图标改为预栅格化位图（**注意**：会连带带走 `SkPathOps`，见 §3.4）
2. 砍掉 GIF（`skia_use_wuffs=false`）与各类编码器
3. 才轮到 `skia_enable_optimize_size=true`（会付出帧时间代价，见 §2.1）

---

## 5. fontconfig：已定为开启，但要知道代价

| | 现状（`skia_use_fontconfig=true`） |
|---|---|
| 系统字体自动发现 | ✅ 直接可用，符合"界面用系统默认字体"的用户预期 |
| Linux 运行时依赖 | 多一个 `libfontconfig`（几乎所有桌面发行版预装，可接受） |
| Windows 对应物 | DirectWrite（`skia_enable_fontmgr_win=true`），**不是** fontconfig |
| CJK / emoji 回退链 | fontconfig 只给候选字体列表，**回退顺序仍要框架自己定**（见 §6） |

同时保留 `skia_enable_fontmgr_custom_directory` 和 `custom_embedded`，
这样框架可以在系统字体之外再加载自带字体或用户指定目录——两套 fontmgr 并存不冲突。

**框架层要做的**：把 fontconfig（Linux）和 DirectWrite（Windows）包在同一个字体来源接口后面。
这两者的 API 和语义差别不小，抽象层从第一天就要有，事后补等于重写字体子系统。

---

## 6. gn args 解决不了、框架自己必须做的

配 Skia 参数只是拿到了能力。以下是 GUI 框架真正的工作量，别指望 gn args：

| 事项 | 说明 |
|---|---|
| **字体回退链** | fontmgr 只给字体枚举。CJK 字形选择（汉字统一表意——同一码点中日韩字形不同）和 emoji 回退顺序，要自己构建 `FontCollection` 并按 BCP 47 语言标签分别建链 |
| **三种文本索引空间** | 内部存储用 UTF-8，`SkParagraph` 的位置 API 是 **UTF-16 语义**，用户可见的"第几个字"是 **grapheme**。三者在纯 ASCII 下完全一致，一遇中文就静默错位。建议用互不隐式转换的强类型包装挡住 |
| **GPU 上下文丢失恢复** | Windows 驱动更新 / 休眠 / TDR 都会让 `GrDirectContext` 失效。需要：检测 → 丢弃 GPU 资源 → 重建 → 重传字形图集与纹理 → 重绘 |
| **纹理与字形图集预算** | Skia 不替你做 LRU 淘汰策略 |
| **脏区 / 部分重绘** | Skia 只管画，脏区计算和 `SwapBuffersWithDamage` 是你的事 |
| **`saveLayer` 成本控制** | 节点 opacity 会触发离屏合成，需要在框架层做"单叶子直接乘 alpha"之类的优化 |

---

## 7. P0 冒烟测试要覆盖的（验证配置是否真的够用）

配置对不对，靠这几个用例验，不靠读文档：

1. **CPU 光栅**：`SkSurfaces::Raster` 画圆角矩形 + 渐变 + 阴影，存 PNG
2. **GPU 路径**：用 proc loader 组装 GL interface，建 `GrDirectContext`，同样画一遍，像素比对
3. **中文断行**：一段无空格中文，`SkParagraph` 定宽换行，检查断点位置合理（验 §2.3 的 UAX#14）
4. **grapheme 边界**：`👨‍👩‍👧‍👦`（ZWJ 序列）+ `🇨🇳`（区域指示符对）+ 肤色修饰符，验证退格删除是整体删
5. **双击选词**：中英混排下 `getWords` 返回的边界是否合理
6. **RTL**：一段阿拉伯语 + 英文混排，验证 BiDi 生效（验 libgrapheme 自带的 icu_bidi 确实工作）
7. **SVG 图标**：加载一个 SVG 渲染成 `SkPicture`，按不同 DPI 栅格化
8. **图片**：PNG / JPEG / WebP 各解一张
9. **体积**：把上述全部链成一个可执行文件，记录 strip 后大小 —— **这是体积基线，不是 `libskia.a` 的大小**
10. **帧时间**：滚动一屏文本，记录 p99 帧时间 —— `-Oz` 决策的依据

第 3、4、5、6 条是验证 libgrapheme 方案够不够用的关键。**任何一条不过，就得回退到完整 ICU。**

---

## 8. 消费方到底要引用什么

### 8.1 结论：一行

7 个 `.a` 是 GN 的产物形态，**不是消费方要面对的东西**。libskia2 出的是 CMake package：

```cmake
find_package(skia2 REQUIRED)
target_link_libraries(my_gui PRIVATE skia2::skia2)
```

`skia2::skia2` 是一个 INTERFACE target，里面声明好：
7 个 `IMPORTED STATIC` 库及其依赖关系（链接顺序由 CMake 拓扑排序，不用手写）、
头文件搜索路径、系统库、以及 customization-analysis §2.G 的全部 ABI 编译选项。

**这正是现有第三方预编译库没做的事**——rust-skia 之流只丢给你一堆 `.a`，
ABI 约束靠人肉对齐、链接顺序靠试错。libskia2 的价值有一半在这里。

### 8.2 第三方依赖：全部在 `libskia.a` 里，一个都不用链

前提是配置里那组 `skia_use_system_*=false` 一条都不能少。
**这不是可选的洁癖**——`is_official_build=true` 会把它们全部默认翻成 `true`
（详见 customization-analysis §3 专条），届时产物会退化成"薄 libskia.a + 8 个系统库依赖"。

设为 `false` 后被编译进 `libskia.a` 的：
`zlib` / `expat` / `libpng` / `libwebp` / `libjpeg-turbo` / `harfbuzz` / `freetype` /
`libgrapheme` / `icu_bidi` / `wuffs` / `skcms`。

> 注意 `skia_use_system_freetype2` 的默认表达式是
> `(is_official_build || !(is_android || MSAN)) && !is_canvaskit`——
> 在桌面 Linux 上**即使不开 official build 也是 `true`**。必须显式关。

### 8.3 真正逃不掉的系统库

**Linux**

| 库 | 为什么 | 能否避免 |
|---|---|---|
| `fontconfig` | Skia 从不 vendor 它（`third_party/BUILD.gn` L9 只有 `libs = ["fontconfig"]`） | 只能关掉 `skia_use_fontconfig`，改用 custom fontmgr |
| `dl` `pthread` `m` | libc 家族 | 否 |
| **GL 相关：无** | 因为选了 `skia_use_x11=false` + `skia_use_egl=false`（§2.2） | — |

**Windows**

GN 里显式声明的只有两条：`OpenGL32.lib`（`skia_use_gl=true` 必带）、
`Gdi32.lib`（仅 `fontmgr_win_gdi`，本配置已关）。

DirectWrite / COM 相关的那组（`ole32` `oleaut32` `user32` 等）GN 没有显式列出，
**实际需要哪些必须在 P4 首次链接时实测补齐**，然后固化进 CMake package。
这里不猜。

### 8.4 为什么不合并成一个 `.a`

合并（`ar` MRI 脚本 / `llvm-ar` / `lib.exe`）的**唯一实质收益是免去链接顺序管理**，
而 CMake package 本来就替你做了这件事。代价则是实打实的：

- 不同 module 可能有同名目标文件，`ar` 归档内会冲突
- 三个平台三套合并脚本
- 出问题时符号定位到哪个 module 变得麻烦

顺带纠正一个常见说法：合并**不会**影响 `--gc-sections` 的效果。
`ar` 只是把 `.o` 拼进一个归档，section 粒度不变，链接器依然按需逐个 `.o` 拉取。
体积上是中性的。
