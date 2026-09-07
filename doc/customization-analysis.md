# libskia2 定制面分析

> 证据基准：`google/skia` 分支 `chrome/m153`（commit `4f574af`），本文所有"默认值"均直接读自该分支源码，非二手资料。
> 参考对象：`Shopify/react-native-skia`（commit `5dd9b50`，pin `chrome/m152`）。

## 0. 前提

| 项 | 决定 |
|---|---|
| 消费方 | C++ 项目，直接调用 Skia C++ API（不做 C ABI 封装层） |
| 目标平台（首批） | `linux-x64`、`windows-x64-msvc` |
| 首要定制目标 | **裁剪体积** |
| 产物 | 版本化的预编译静态库 + 对齐的头文件包 |

---

## 1. react-native-skia：能抄什么，不能抄什么

**最重要的一条事实：react-native-skia 根本不支持 Linux 和 Windows。**
它的 `skia-configuration.ts` 里只有 `android` / `apple-ios` / `apple-tvos` / `apple-macos` 四个平台。
你要做的两个 target，正好是它完全没有的部分——GN args、字体后端、CRT/ABI 处理全都要自己写。

| 维度 | 能不能抄 | 说明 |
|---|---|---|
| **版本 pin 方式** | ✅ 直接抄 | git submodule 指向 `chromium.googlesource.com/skia`，`branch = chrome/m152`。**用上游而非 fork**，patch 在构建时打 |
| **依赖同步** | ✅ 直接抄 | `PATH=depot_tools:$PATH python3 tools/git-sync-deps`，比 gclient 轻得多 |
| **GN args 三层合并** | ✅ 直接抄 | `commonArgs` + 平台 args + target args，最后拼成一条 `gn gen --args='...'` |
| **产物清单显式声明** | ✅ 直接抄 | `outputNames: ["libskia.a", "libskshaper.a", ...]`，构建后按名字捞文件，缺一个就报错 |
| **CI 形态** | ✅ 直接抄 | 每个 target 一个 matrix job，各出一个 `.tar.gz`，传 GitHub Release；tag 形如 `skia-m152` |
| **`ZERO_AR_DATE=1`** | ✅ 直接抄 | 归档时间戳归零，构建可复现的前提 |
| **头文件复制清单** | ⚠️ 抄思路 | 它把 `include/**` + 各 module 的 `include/` + **一小撮 `src/` 私有头**复制出去（见 §8.2） |
| **平台矩阵 / 工具链** | ❌ 无可抄 | 它没有 Linux/Windows |
| Metal / Dawn / Graphite | ❌ 不需要 | |
| XCFramework / `lipo` 打包 | ❌ 不需要 | |
| npm / gradle / podspec 分发 | ❌ 不需要 | 你要的是 CMake package |
| 它的 GN args 取值 | ⚠️ 别照抄 | 多数是移动端取向（如 Apple 上强开 `-frtti -fexceptions` 是 React Native 的要求，不是你的） |

**唯一值得原样照抄的一条 GN args 经验**：

```ts
["skia_use_partition_alloc", false],  // Prevents raw_ptr link errors
```

这条在 m153 上对你是**必须**的——见 §3 第 1 行。

---

## 2. 定制面全清单（九个轴）

每个轴都必须做出显式决定，"用默认值"也是一个决定，但要知道默认值是什么。

### A. 版本与来源

| 选项 | 取舍 |
|---|---|
| upstream `google/skia` + 自己的 patch 目录 | **推荐**。react-native-skia 就是这么做的。patch 可审计、可复现、可随 milestone 重打 |
| 维护一个 Skia fork | rust-skia 的做法（27 个 commit）。省事但 rebase 成本随时间累积 |
| pin 到 `chrome/mXXX` 分支 | **推荐**。milestone 分支是 Chrome 实际发版用的，稳定性远高于 main |
| pin 到具体 commit SHA | 必须。分支会动，submodule 记录 SHA 才可复现 |

当前可选：`chrome/m152`（RN-Skia 在用）、`chrome/m153`、`chrome/m154`（已存在）。
建议 **m153**：比 m152 新，比 m154 成熟。

### B. 构建形态

| GN arg | m153 默认 | 建议 | 影响 |
|---|---|---|---|
| `is_official_build` | `false` | **`true`** | 关 tools/tracing/断言，开 `/OPT:ICF,REF`，体积大头 |
| `is_debug` | — | `false`（release）/ `true`（debug 变体） | 建议两个变体都发 |
| `is_component_build` | `false` | **保持 `false`** | 一旦 `true`，`skia_enable_skottie` / `skia_enable_svg` 会被强制关掉 |
| `skia_enable_optimize_size` | `false` | **`true`** | `-Oz`（MSVC `/Os`）+ 定义 `SK_ENABLE_OPTIMIZE_SIZE` |
| `skia_enable_tools` | `is_skia_dev_build` | `false` | official build 下已自动 false |
| `skia_disable_tracing` | `is_official_build` | 随 official | |

> `skia_enable_optimize_size=true` 有硬断言：必须 `is_debug=false`，否则 GN 直接 assert 失败。

### C. 渲染后端

| GN arg | m153 默认 | Linux 建议 | Windows 建议 |
|---|---|---|---|
| `skia_enable_ganesh` | `true` | `true` | `true` |
| `skia_use_gl` | `true` | `true` | `true` |
| `skia_use_egl` | `false` | 看是否要 EGL | `false` |
| `skia_use_vulkan` | `false` | 可选 | 可选 |
| `skia_use_direct3d` | `false` | — | `false`（除非要 D3D12） |
| `skia_enable_graphite` | `false` | `false` | `false` |
| `skia_use_dawn` | `false` | `false` | `false`（有 `assert(!skia_use_dawn \|\| skia_enable_graphite)`） |
| `skia_use_angle` | `false` | `false` | `false` |
| `skia_enable_discrete_gpu` | `true` | 可关 | 可关 |
| `skia_use_x11` | `is_linux` → **`true`** | **`false`** | — |

> `skia_use_gl` 不引入对 `libGL` 的链接依赖——Skia 提供 `GrGLMakeNativeInterface_none` 变体，
> 入口由调用方在运行时通过 proc loader 提供。这点对做"可嵌入库"很关键。

### D. 模块（独立 `.a`）

`group("modules")` 在 m153 里只含 5 个：`bentleyottmann` / `skottie` / `skparagraph` / `skshaper` / `svg`。
其余是它们的传递依赖。

| 模块 | 产物 | 门控 | 体积 | 建议 |
|---|---|---|---|---|
| skshaper | `libskshaper.a` | `skia_use_harfbuzz` | 中 | 要文本排版就得有 |
| skparagraph | `libskparagraph.a` | `skia_enable_skparagraph` | 中 | 富文本/换行/BiDi |
| skunicode | `libskunicode_core.a` + 后端变体 | `skia_enable_skunicode`（派生） | **见 §5** | 体积决策核心 |
| svg | `libsvg.a` | `skia_enable_svg` | 中 | 依赖 `:xml` → `skia_use_expat` |
| skottie | `libskottie.a` | `skia_enable_skottie` | 大 | 不做 Lottie 就关 |
| sksg / skresources / jsonreader | 各自 `.a` | skottie 的依赖 | 中 | 随 skottie 一起关 |
| pathops | 并入 `libskia.a` | 常开 | 小 | |
| skcms | 并入 `libskia.a` | 必需 | 小 | 色彩管理，关不掉 |
| bentleyottmann | `libbentleyottmann.a` | — | 小 | 多半用不到 |

> `skia_enable_skottie` 和 `skia_enable_svg` 在 m153 的默认值是 `!is_component_build`，
> 也就是**你不显式关就是开着的**。

### E. 图像编解码（m153 实测默认值）

这张表是 §4 裁剪清单的依据。**注意多条与常见二手资料不同**。

| 能力 | GN arg | m153 默认 | 备注 |
|---|---|---|---|
| BMP / WBMP 解码 | 无 arg | **常开** | 直接编进 `libskia.a`，关不掉 |
| PNG 解码 | `skia_use_libpng_decode` | `true` | |
| PNG 编码 | `skia_use_libpng_encode` | `true` | |
| JPEG 解码 | `skia_use_libjpeg_turbo_decode` | `true` | |
| JPEG 编码 | `skia_use_libjpeg_turbo_encode` | `true` | |
| **WebP 解码** | `skia_use_libwebp_decode` | **`true`** | 默认就有，不需要额外开 |
| **WebP 编码** | `skia_use_libwebp_encode` | **`true`**（`!is_canvaskit`） | |
| GIF 解码 | `skia_use_wuffs` | **`true`** | 走 wuffs |
| **RAW/DNG 解码** | `skia_use_dng_sdk` | **`true`**（派生自 jpeg_decode && zlib） | **体积大户，多半该关** |
| RAW 元数据 | `skia_use_piex` | **`true`**（`!is_win`） | Linux 上默认开 |
| AVIF | `skia_use_libavif` / `skia_use_crabbyavif` | `false` | 要就显式开 |
| JPEG XL | `skia_use_libjxl_decode` | `false` | |
| HEIF | — | 无独立 arg | |
| JPEG gainmap | `skia_use_jpeg_gainmaps` | `is_skia_dev_build` | official 下自动关 |
| Rust codec 全家 | `skia_use_rust_*` | 全 `false` | m153 新增，实验性 |
| 禁用编码器快捷开关 | `skia_use_no_png_encode` / `no_jpeg_encode` / `no_webp_encode` | `false` | 只关编码保留解码时用 |

### F. 字体与文本栈

平台差异最大的一轴。

| GN arg | Linux 默认 | Windows 默认 | 说明 |
|---|---|---|---|
| `skia_use_freetype` | **`true`** | **`false`** | Linux 字体光栅化 |
| `skia_use_fontconfig` | **`true`** | `false` | 引入 fontconfig 运行时依赖 |
| `skia_enable_fontmgr_fontconfig` | `true` | `false` | |
| `skia_enable_fontmgr_win` | `false` | **`true`** | DirectWrite |
| `skia_enable_fontmgr_win_gdi` | `false` | **`true`** | 老 GDI 路径，可关 |
| `skia_enable_fontmgr_custom_embedded` | `true` | `false` | 内嵌字体 |
| `skia_enable_fontmgr_custom_directory` | `true` | `false` | 目录扫描 |
| `skia_enable_fontmgr_empty` | `false` | `false` | 完全由调用方提供 |
| `skia_use_fontations` | `false` | `false` | Rust 字体后端，实验性 |
| `skia_use_harfbuzz` | `true` | `true` | shaping |
| `skia_use_system_harfbuzz` | `false` | `false` | **保持 false**，用 Skia 自带的 |

**决策点**：是否要 fontconfig。
- 要 → Linux 产物带运行时 `libfontconfig` 依赖，但系统字体自动发现能用
- 不要 → 用 `fontmgr_custom_directory` + `fontmgr_custom_embedded`，字体由你自己管，产物更独立

Unicode 后端见 §5，单独展开。

### G. 工具链 / ABI（消费方必须逐条匹配）

**这一轴不产生体积收益，但错一条就是链接失败或运行时崩溃。** 全部实测自 `gn/skia/BUILD.gn`。

| 项 | Skia m153 实际行为 | 消费方后果 |
|---|---|---|
| **C++ 标准** | **C++20**（`/std:c++20`、`-std=c++20`） | 消费方 <C++20 编译头文件会失败。注意：不是很多资料说的 C++17 |
| **RTTI** | **关**（`-fno-rtti` / `/GR-`） | 你的代码对 Skia 类型用 `dynamic_cast` 会挂。要 RTTI 得 `extra_cflags_cc=["-frtti"]` 重编 |
| **异常** | 非 Windows：`-fno-exceptions`；Windows：`_HAS_EXCEPTIONS=0` | **`_HAS_EXCEPTIONS=0` 会改变 MSVC STL 的 ABI**，消费方必须同样定义，否则 ODR 违规 |
| **符号可见性** | `-fvisibility=hidden` + `-fvisibility-inlines-hidden` | 静态库消费无碍；将来若转 DLL 需显式导出 |
| **Windows CRT** | **Skia GN 全程不传 `/MD` 或 `/MT`** → cl.exe 落到默认 **`/MT`（静态 CRT）** | 消费方用 `/MD` 会 CRT 冲突。**要么消费方统一 `/MT`，要么构建时 `extra_cflags=["/MD"]`** |
| **Linux 标准库** | clang 默认，即 Ubuntu 上的 **libstdc++**（`-stdlib=libc++` 只在 sanitizer 配置里出现） | `_GLIBCXX_USE_CXX11_ABI` 必须与消费方一致；换 libc++ 需显式加 flag |
| **partition_alloc** | `skia_use_partition_alloc = is_clang` → **Linux+clang 下默认 `true`** | 见 §3 第 1 行，**必须关** |
| 其他 MSVC 定义 | `_CRT_SECURE_NO_WARNINGS`、`WIN32_LEAN_AND_MEAN`、`NOMINMAX` | 需在头文件包的 CMake INTERFACE 里透传 |

**libskia2 应该做的**：把上表变成 `skia2Config.cmake` 里的 `INTERFACE_COMPILE_OPTIONS` /
`INTERFACE_COMPILE_DEFINITIONS`，消费方 `target_link_libraries(app PRIVATE skia2::skia)` 就自动对齐。
这正是现有第三方预编译库（rust-skia 等）**没有**做、因而 ABI 全靠人肉对齐的地方。

### H. 打包与分发

| 决策 | 选项 | 建议 |
|---|---|---|
| 多个 `.a` vs 合并成一个 | 保持分开 / `ar` MRI 脚本合并 / `llvm-ar` | **保持分开**。合并的唯一实质收益是免去链接顺序管理，而这件事 CMake package 本来就替你做了。见 gui-framework-profile §8 |
| 头文件来源 | 从同一个 checkout 复制 | 必须。头文件与二进制必须同 commit，否则链接过、运行崩 |
| 版本号 | `<skia-milestone>-<libskia2-revision>` | 如 `m153-0.1.0` |
| 完整性校验 | SHA256 + **gn args 指纹** | 光校验二进制不够。把完整 gn args 写进 `key.txt`，消费方能验"这个库到底开了什么" |
| 分发通道 | GitHub Release assets | 与 RN-Skia、rust-skia 一致 |
| 资产命名 | `libskia2-<version>-<triple>-<feature-hash>.tar.gz` | |

### I. Patch 层

**原则：能用 gn args 解决的，绝不打 patch。** patch 是随 milestone 升级的持续成本。

下游 repackager 常见的 patch 类别，供预判：

| 类别 | 例子 | 你大概率需要吗 |
|---|---|---|
| 构建系统修复 | macOS libtool 报错、Yocto SDK clang flag | ❌（不做 macOS） |
| 符号可见性 | `HB_NO_VISIBILITY` 防 harfbuzz 符号重复 | ⚠️ 若消费方也链 harfbuzz 则需要 |
| 第三方符号前缀 | ICU 符号 `u_*` 改名防冲突 | ⚠️ 若消费方也用 ICU 则需要 |
| 依赖裁剪 | 删掉不用的 module 以绕过链接错误 | ⚠️ 优先用 gn args |
| 平台可用性 shim | iOS `arm64e`、macOS deployment target | ❌ |
| 行为修改 | 改渲染逻辑、加 API | 看你的实际需求 |

规矩：`patches/` 目录 + 编号顺序 + 每个 patch 头部写清"为什么"和"能否用 gn args 替代"。

---

## 3. m153 默认值里的"暗雷"

这些在 Linux/Windows 上**默认是开的**，不显式关掉就白白进产物。按危害排序：

| # | GN arg | 默认 | 危害 | 动作 |
|---|---|---|---|---|
| 1 | `skia_use_partition_alloc` | **Linux+clang = `true`** | 引入 Chrome 的 PartitionAlloc，`raw_ptr` 被注入到**所有** Skia target，消费方极易出现链接错误。RN-Skia 显式关它就是为这个 | **`false`** |
| 1b | **`skia_use_system_*` 全家** | **`is_official_build` 一开就全变 `true`** | 见下方专条。产物会变成"薄 libskia.a + 一堆系统库依赖"，对可分发的预编译库是灾难 | **全部显式 `false`** |
| 2 | `skia_use_dng_sdk` | `true` | RAW/DNG 解码，体积大户 | `false` |
| 3 | `skia_enable_pdf` | `true` | PDF 后端 | `false` |
| 4 | `skia_use_icu` | `true` | 完整 ICU，最大单项 | 见 §5 |
| 5 | `skia_use_perfetto` | **Linux = `true`** | Perfetto tracing SDK | `false` |
| 6 | `skia_use_piex` | **Linux = `true`** | RAW 预览提取 | `false` |
| 7 | `skia_use_wuffs` | `true` | GIF 解码 | 不要 GIF 就 `false` |
| 8 | `skia_enable_skottie` | `true` | Lottie | `false` |
| 9 | `skia_enable_svg` | `true` | SVG（连带 `skia_use_expat`） | 按需 |
| 10 | `skia_use_xps` | `true` | Windows XPS 文档后端 | `false` |
| 11 | `skia_use_x11` | **Linux = `true`** | X11 | `false` |
| 12 | `skia_use_expat` | `true` | XML 解析（SVG/Android fontmgr 需要） | 不要 SVG 就 `false` |
| 13 | `skia_enable_fontmgr_win_gdi` | Windows = `true` | 老 GDI 字体路径 | 有 DirectWrite 就 `false` |
| 14 | `skia_enable_precompile` | `true` | Graphite 预编译支持 | `false` |
| 15 | `skia_use_lua` / `skia_enable_tools` / `skia_enable_android_utils` | `is_skia_dev_build` | — | `is_official_build=true` 时已自动关 |

### 专条：`is_official_build=true` 会把第三方依赖翻成系统库

这是最反直觉的一条——**你为了体积开 `is_official_build`，副作用是 Skia 不再 vendor 第三方库**。
实测各 `declare_args` 默认值：

| GN arg | 默认表达式 | 桌面 Linux/Windows 实际值 | 定义位置 |
|---|---|---|---|
| `skia_use_system_zlib` | `is_official_build` | **`true`** | `third_party/zlib/zlib.gni` |
| `skia_use_system_expat` | `is_official_build` | **`true`** | `third_party/expat/BUILD.gn` |
| `skia_use_system_icu` | `is_official_build && !is_canvaskit` | **`true`** | `third_party/icu/icu.gni` |
| `skia_use_system_libpng` | `is_official_build && !is_canvaskit` | **`true`** | `third_party/libpng/BUILD.gn` |
| `skia_use_system_libwebp` | `is_official_build && !is_canvaskit` | **`true`** | `third_party/libwebp/BUILD.gn` |
| `skia_use_system_libjpeg_turbo` | `is_official_build && !is_canvaskit` | **`true`** | `third_party/libjpeg-turbo/BUILD.gn` |
| `skia_use_system_harfbuzz` | `is_official_build && !is_canvaskit` | **`true`** | `third_party/harfbuzz/BUILD.gn` |
| `skia_use_system_freetype2` | `(is_official_build \|\| !(is_android \|\| MSAN)) && !is_canvaskit` | **`true`**（**即使不开 official build**） | `third_party/freetype2/BUILD.gn` |

`system()` 模板（`third_party/third_party.gni` L104）做的事就是把目标换成一个只带 `libs = [...]`
的空 group——源码根本不参与编译。

**后果**：产物变成"薄 `libskia.a` + 8 个系统库依赖"，且版本必须与构建机一致。
对一个要分发给别人的预编译库，这是灾难。

**这就是 react-native-skia 把它们逐条显式设为 `false` 的原因**
（`skia-configuration.ts` 的 `commonArgs` 里 5 条 `skia_use_system_* = false` 排在最前面）。

全部设 `false` 后，zlib / expat / libpng / libwebp / libjpeg-turbo / harfbuzz / freetype
**全部编译进 `libskia.a`**，消费方一个都不用链。

**唯一的例外是 fontconfig**——Skia 从不 vendor 它：
```gn
# third_party/BUILD.gn L9
config("system_fontconfig") { libs = [ "fontconfig" ] }
group("fontconfig") { public_configs = [ ":system_fontconfig" ] }
```
开 `skia_use_fontconfig=true` 就必然带一个 `libfontconfig` 的运行时依赖，没有第二条路。

---

## 4. 裁剪体积：按收益排序的动作清单

> **先说度量口径**：静态库 `.a` 的大小几乎没有意义——它含大量未被引用的 section。
> 真正的指标是**链接一个最小可用程序后的二进制体积**。libskia2 的 CI 应该产出这个数字作为回归门槛，
> 而不是报告 `libskia.a` 有多大。

| 档位 | 动作 | 预期收益 | 代价 |
|---|---|---|---|
| **巨额** | ICU 策略切换（§5） | 最大单项，完整 ICU 数据约 10 MB 量级 | 失去部分 Unicode 能力，须逐项确认 |
| **巨额** | `is_official_build=true` | 关断言/tracing/tools + `/OPT:ICF,REF` | 无（release 本就该开） |
| **大** | `skia_enable_optimize_size=true` | `-Oz` / `/Os`，全局代码收缩 | 有性能损失，需实测 |
| **大** | 关 `skia_use_dng_sdk` + `skia_use_piex` | RAW 解码栈整块移除 | 不能读 RAW/DNG |
| **大** | 关 `skia_enable_pdf`（+ `skia_use_xps`） | PDF/XPS 后端整块移除 | 不能导出 PDF |
| **大** | 关 `skia_enable_skottie`（连带 sksg/skresources/jsonreader） | 4 个 module 消失 | 不能播 Lottie |
| **中** | 关 `skia_use_partition_alloc` | 移除 PartitionAlloc | 无（本就该关） |
| **中** | 关 `skia_enable_svg` + `skia_use_expat` | SVG + XML 解析器 | 不能渲染 SVG |
| **中** | 关 `skia_use_perfetto` | tracing SDK | 无 |
| **中** | codec 精简（关 GIF/WebP 编码等） | 每项数百 KB | 对应格式不可用 |
| **中** | 消费侧 `-ffunction-sections -fdata-sections` + `--gc-sections` / `/OPT:REF` | 未引用代码被丢弃 | 需要构建期加 `extra_cflags` |
| **小** | 关 `skia_enable_discrete_gpu` / `precompile` / `fontmgr_win_gdi` | 各数十 KB | |
| **待测** | LTO（`extra_cflags=["-flto"]`） | 可观但不确定 | 链接变慢；静态库跨 TU LTO 要求消费方也开 |

---

## 5. Unicode 后端：裁剪的核心决策

`skia_enable_skunicode` 是派生值：
```
skia_enable_skunicode = skia_use_icu || skia_use_client_icu || skia_use_bidi
                        || skia_use_libgrapheme || skia_use_icu4x
```
五个后端**可以组合**（`modules/skunicode/BUILD.gn` 为每个开关生成一个独立 component，
注释写明"因为不同 ICU 构建需要不同 defines 才拆开"）。

| 后端 | GN arg | 产物 | grapheme | 断词 | 断行 UAX#14 | BiDi | 分句 | UTF-16 API | 体积 |
|---|---|---|---|---|---|---|---|---|---|
| 完整 ICU（内嵌数据） | `skia_use_icu=true` | `libskunicode_icu.a` | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | **最大**（含 icudtl 数据） |
| 运行时 ICU | `+ skia_use_runtime_icu=true` | 同上 | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | 小（dlopen 系统 ICU）；**仅 Android/Linux 生效**，Windows 无效 |
| 系统 ICU | `skia_use_system_icu=true` | 同上 | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | 最小，但强依赖系统 ICU 版本 |
| **libgrapheme** | `skia_use_libgrapheme=true` | `libskunicode_libgrapheme.a` | ✅ | ✅ | ✅ | **✅** | ❌ | ❌ | **很小** |
| icu_bidi | `skia_use_bidi=true` | `libskunicode_bidi.a` | ❌ | ❌ | ❌ | ✅ | ❌ | — | 小（只取 ICU 的 bidi 部分） |
| ICU4X | `skia_use_icu4x=true` | `libskunicode_icu4x.a` | ✅ | ？ | ？ | ✅ | ？ | ？ | 中；引入 Rust 工具链 |
| client 提供 | `skia_use_client_icu=true` | `libskunicode_client_icu.a` | 由你实现 | | | | | | 0 |

**关键事实（实测 m153，与多数二手资料不同）：`libgrapheme 后端自带 BiDi`。**

`modules/skunicode/BUILD.gn` 里 `skunicode_libgrapheme` 的 sources 是：
```
sources  = skia_unicode_icu_bidi_sources       # ← icu_bidi
sources += skia_unicode_bidi_subset_sources    # ← icu_bidi 子集
sources += skia_unicode_libgrapheme_sources
deps    += [ skia_icu_bidi_third_party_dir, skia_libgrapheme_third_party_dir ]
```
`SkUnicode_libgrapheme.cpp` 的 `getBidiRegions()` / `makeBidiIterator()` 直接转发给 `fBidiFact`。
所以**不需要**再叠加 `skia_use_bidi=true`，那是给"只要 BiDi 不要别的"的场景用的独立后端。

`SkUnicode_libgrapheme.cpp` 逐方法实测结论：

| 方法 | 实现 |
|---|---|
| `computeCodeUnitFlags(char utf8[])` | ✅ `grapheme_next_character_break_utf8` + `grapheme_next_line_break_utf8` |
| `getWords` / `getUtf8Words` | ✅ `grapheme_next_word_break_utf8` |
| `getBidiRegions` / `makeBidiIterator` | ✅ 转发 icu_bidi |
| `toUpper(str, locale)` | ⚠️ `grapheme_to_uppercase_utf8`，**locale 参数被忽略**（无土耳其语 i 处理） |
| `getSentences` | ❌ `SkDEBUGF("not implemented")` + `return false` |
| `computeCodeUnitFlags(char16_t utf16[])` | ❌ `SkASSERT(false)` |
| `SkBreakIterator::setText(char16_t[])` | ❌ `SkASSERT(false)` |

**相对完整 ICU 真正失去的**：分句迭代、locale 敏感大小写、**UTF-16 代码路径**、
以及泰语/老挝语/高棉语/缅甸语的**词典分词**（libgrapheme 只实现 UAX#14 规则，
这些语言的断行会退化）。CJK 断行不受影响——它由 UAX#14 规则表覆盖。

参照：react-native-skia 在 Apple 平台生产环境用的就是 `skia_use_libgrapheme=true` + `skia_use_icu=false`；
Android 端用 `skia_use_icu=true` + `skia_use_runtime_icu=true`（dlopen 系统 ICU）。

**必须实测验证的点**（不能靠推断）：
1. libgrapheme 的 UAX#14 断行对**中文避头尾**（行首不得为 `。，！？」`）覆盖到什么程度
2. `SkParagraph` 在 libgrapheme 后端下是否全程走 UTF-8 路径（UTF-16 路径是 `SkASSERT(false)`）
3. 泰语/老挝语/高棉语等需要词典分词的语言退化到什么程度
4. 两种方案（完整 ICU vs libgrapheme）链接后的**真实二进制体积差**

---

## 6. 建议的 gn args 草案

未经实测，作为第一次构建的起点。

**公共**
```
is_official_build=true
is_debug=false
is_component_build=false
skia_enable_optimize_size=true
skia_use_partition_alloc=false        # 暗雷 #1
skia_enable_tools=false
skia_enable_ganesh=true
skia_use_gl=true
skia_enable_graphite=false
skia_use_dawn=false
skia_enable_pdf=false
skia_use_xps=false
skia_enable_skottie=false
skia_enable_precompile=false
skia_enable_discrete_gpu=false
skia_use_dng_sdk=false
skia_use_piex=false
skia_use_perfetto=false
skia_use_wuffs=false                  # 不要 GIF
skia_use_harfbuzz=true
skia_use_system_harfbuzz=false
skia_use_system_libjpeg_turbo=false
skia_use_system_libpng=false
skia_use_system_libwebp=false
skia_use_system_zlib=false
skia_use_system_expat=false
skia_use_system_icu=false
# Unicode：先按 A 方案（完整 ICU）跑通，再切 B 方案（libgrapheme+bidi）对比体积
skia_use_icu=true
skia_use_libgrapheme=false
skia_use_bidi=false
skia_enable_skparagraph=true
# SVG：按需
skia_enable_svg=true
skia_use_expat=true
```

**linux-x64 追加**
```
target_os="linux"
target_cpu="x64"
cc="clang"
cxx="clang++"
skia_use_x11=false
skia_use_egl=false
skia_use_freetype=true
skia_use_fontconfig=true              # 或 false + custom fontmgr，见 §2.F
extra_cflags=["-ffunction-sections","-fdata-sections"]
```

**windows-x64-msvc 追加**
```
target_os="win"
target_cpu="x64"
skia_enable_fontmgr_win=true
skia_enable_fontmgr_win_gdi=false
skia_use_freetype=false
extra_cflags=["/MD"]                  # 见 §2.G：不加则落到 /MT
```

---

## 7. 建议的仓库结构

```
libskia2/
├── README.md
├── doc/
│   ├── customization-analysis.md     # 本文
│   ├── abi-contract.md               # §2.G 的正式契约，消费方必读
│   └── provenance.md                 # 记录 skia commit + patch 列表 + gn args 指纹
├── externals/
│   ├── skia/                         # submodule → chromium.googlesource.com/skia @ chrome/m153
│   └── depot_tools/                  # submodule
├── config/
│   ├── common.gn.args
│   └── targets/{linux-x64,windows-x64-msvc}.gn.args
├── patches/                          # 编号 patch，每个带"为什么"
├── scripts/
│   ├── sync-deps.*                   # 包装 tools/git-sync-deps
│   ├── build.*                       # gn gen + ninja + 产物校验
│   ├── copy-headers.*                # 头文件包
│   └── measure-size.*                # 链接最小程序，输出体积（回归门槛）
├── cmake/
│   └── skia2Config.cmake.in          # 把 §2.G 的 ABI 约束固化成 INTERFACE 属性
├── tests/
│   └── smoke/                        # 最小 C++ 程序：建 surface、画图、存 PNG、量体积
└── .github/workflows/build.yml       # matrix: linux-x64 / windows-x64-msvc
```

---

## 8. 两个容易漏的实现细节

### 8.1 产物清单要显式声明并校验
RN-Skia 的 `outputNames` 数组是个好设计：构建完按名字捞文件，**少一个就 fail**。
否则某个 gn arg 关掉后 module 静默消失，直到消费方链接失败才发现。

### 8.2 头文件包不只有 `include/`
需要复制的至少有：
- `include/**`（公开 API）
- `modules/{svg,skparagraph,skshaper,skottie,sksg,skresources,skunicode,skcms,jsonreader}/include`
- **少量 `src/` 私有头**——RN-Skia 复制了 `src/core/`（`SkChecksum.h`、`SkTHash.h` 等）和
  `src/gpu/ganesh/gl/` 的一部分。这是因为某些公开头文件 `#include` 了它们。

必须实测：编译一个只 `#include <skia/core/SkCanvas.h>` 等公开头的 TU，
把所有缺失头文件补进清单，直到干净编过。**这一步不做，头文件包必然缺件。**

---

## 9. 建议实施顺序

| 阶段 | 目标 | 完成标准 |
|---|---|---|
| P0 | Linux x64 一次跑通 | 默认 args 能出 `libskia.a`，最小程序画个圆存 PNG |
| P1 | 加体积度量 | `measure-size` 脚本给出基线数字 |
| P2 | 逐项应用 §4 裁剪清单 | 每关一项记录一次体积，得到收益表（**这才是"定制"的实质**） |
| P3 | Unicode 三方案对比 | §5 的四个实测问题有答案 |
| P4 | Windows MSVC | CRT 决策落地，两平台产物对齐 |
| P5 | 头文件包 + CMake package | 消费方 `find_package(skia2)` 即用，ABI 自动对齐 |
| P6 | CI + Release | matrix 构建，tar.gz 上传，SHA256 + gn args 指纹 |

---

## 10. 未决问题

1. **是否要 fontconfig**（§2.F）——影响 Linux 产物的运行时依赖
2. **Windows 走 `/MT` 还是 `/MD`**（§2.G）——取决于消费方，定了就不能改
3. **RTTI 是否要开**——Skia 默认关；若你的代码对 Skia 类型用 `dynamic_cast` 则必须开
4. **Unicode 方案**（§5）——需 P3 实测数据
5. **是否要 SVG**——连带 expat + xml，中等体积
6. **milestone 升级节奏**——跟 Chrome 每 4 周，还是半年一次

---

## 附：本文的证据来源

| 结论 | 来源文件（`google/skia@chrome/m153`） |
|---|---|
| 全部 `declare_args` 默认值 | `gn/skia.gni` |
| C++20 / RTTI / 异常 / visibility / 无 `/MD` | `gn/skia/BUILD.gn` |
| `optimize_size` → `-Oz` / `/Os` | `gn/skia/BUILD.gn` |
| 模块列表 `group("modules")` | `BUILD.gn` |
| codec 目标与 `skia_component("skia")` 依赖 | `BUILD.gn` |
| SkUnicode 五后端与 defines | `modules/skunicode/BUILD.gn` |
| icudtl.dat 处理 | `third_party/icu/BUILD.gn` |
| RN-Skia 管线与 GN args | `Shopify/react-native-skia@5dd9b50` `packages/skia/scripts/{build-skia,skia-configuration}.ts`、`.github/workflows/build-skia.yml`、`.gitmodules` |

`doc/research-raw/` 下有两份早期调研笔记，**基于 m120，含已知错误**（如 C++ 标准写成 C++17），
仅作线索保留，结论以本文为准。
