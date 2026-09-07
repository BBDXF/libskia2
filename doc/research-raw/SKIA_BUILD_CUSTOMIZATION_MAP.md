# SKIA BUILD CUSTOMIZATION MAP v1.0
## Complete Decision Surface for Custom Static Library Builds
Source: google/skia chrome/m120 branch | Methodology: Direct source audit (gn/skia.gni, BUILD.gn, modules/*/BUILD.gn)

---

## 1. AUTHORITATIVE GN ARGUMENTS REGISTRY

### 1.1 External Dependency Control (skia_use_*)
All defaults from /gn/skia.gni lines 11-103.

CORE CODECS & IMAGE:
- skia_use_libjpeg_turbo_decode = true (JPEG decoders, +1MB)
- skia_use_libjpeg_turbo_encode = true (JPEG encoding, +200KB)
- skia_use_no_jpeg_encode = false (set true to disable JPEG encoding)
- skia_use_libpng_decode = true (PNG codec, +800KB)
- skia_use_libpng_encode = true (PNG encoding, +300KB)
- skia_use_no_png_encode = false (blocks PNG encoding if true)
- skia_use_libwebp_decode = true (WebP decoder, +600KB)
- skia_use_libwebp_encode = !is_wasm (WebP encoding, +400KB; OFF on WASM)
- skia_use_no_webp_encode = false (blocks WebP encoding if true)
- skia_use_libavif = false (AVIF support via libavif, +500KB)
- skia_use_libjxl_decode = false (JPEG XL decoder, +700KB)
- skia_use_libheif = is_skia_dev_build (HEIF/H.265, +400KB; dev-only)
- skia_use_wuffs = true (GIF via wuffs, +200KB)
- skia_use_piex = !is_win && !is_wasm (RAW metadata, +100KB)
- skia_use_dng_sdk = derived (RAW codec; requires JPEG turbo + zlib, +300KB)

TEXT SHAPING:
- skia_use_harfbuzz = true (text shaping, +2MB, HIGH IMPACT)
- skia_use_fontconfig = is_linux (Linux font enum)
- skia_use_freetype = platform (TrueType/OT, +600KB)
- skia_use_fonthost_mac = is_mac || is_ios (macOS/iOS native)

UNICODE & BIDI:
- skia_use_icu = !is_fuchsia (full ICU, +8-15MB, CRITICAL)
- skia_use_icu4x = false (ICU4X Rust subset, +2-4MB)
- skia_use_client_icu = false (client provides ICU symbols)
- skia_use_libgrapheme = false (grapheme clusters, +300KB)

GPU BACKENDS:
- skia_use_gl = !is_fuchsia (OpenGL, +2-5MB)
- skia_use_egl = false (EGL for embedded)
- skia_use_angle = false (ANGLE D3D11→GLES, +3MB)
- skia_use_direct3d = false (Direct3D 12, +4MB)
- skia_use_metal = false (Metal/Apple, platform-var)
- skia_use_vulkan = platform (Android ndk_api>=24, Fuchsia true; +3-6MB)
- skia_use_dawn = false (WebGPU, +5MB; requires graphite)
- skia_use_webgl = is_wasm (WebGL only)
- skia_use_webgpu = is_wasm (WebGPU only)

MISC LIBS:
- skia_use_zlib = true (compression, +500KB)
- skia_use_expat = !is_wasm (XML fonts, +200KB)
- skia_use_lua = is_skia_dev_build && !is_ios (Lua, +300KB)
- skia_use_ffmpeg = false (video decoding, +10MB)
- skia_use_sfml = false (windowing)
- skia_use_x11 = is_linux (X11)
- skia_use_perfetto = platform (tracing, +500KB)
- skia_use_safe_libcxx = false (libc++ assertions)

DERIVED:
- skia_use_dng_sdk = !is_fuchsia && !is_wasm && skia_use_libjpeg_turbo_decode && skia_use_zlib

### 1.2 Feature Control (skia_enable_*)

RENDERING BACKENDS:
- skia_enable_ganesh = skia_enable_gpu (Ganesh rasterizer, +5-10MB, CRITICAL; requires static link)
- skia_enable_gpu = true (DEPRECATED; alias)
- skia_enable_graphite = false (new experimental backend, +3-8MB)

FEATURES:
- skia_enable_pdf = !is_wasm (PDF rendering, +2MB)
- skia_enable_svg = !is_component_build (SVG, +500KB; blocked by DLL)
- skia_enable_skottie = !(is_win && is_component_build) (Lottie animation, +1.5MB)
- skia_enable_precompile = true (shader caching)
- skia_enable_optimize_size = false (size optimization; requires is_debug=false)

SHAPING & UNICODE:
- skia_enable_skunicode = DERIVED (ON if: ICU OR client-ICU OR libgrapheme OR ICU4X)

FONT MANAGERS (select ONE primary):
- skia_enable_fontmgr_empty = false (null manager; app provides fonts; -1.5MB)
- skia_enable_fontmgr_android = skia_use_expat && skia_use_freetype (Android system fonts)
- skia_enable_fontmgr_custom_directory = skia_use_freetype && !is_fuchsia && !is_wasm
- skia_enable_fontmgr_custom_embedded = skia_use_freetype && !is_fuchsia
- skia_enable_fontmgr_custom_empty = skia_use_freetype && !is_wasm
- skia_enable_fontmgr_fontconfig = skia_use_freetype && skia_use_fontconfig (fontconfig+FT)
- skia_enable_fontmgr_win = is_win (Windows GDI)
- skia_enable_fontmgr_win_gdi = is_win && !skia_enable_winuwp (legacy GDI)
- skia_enable_fontmgr_fuchsia = is_fuchsia
- skia_enable_fontmgr_FontConfigInterface = skia_use_freetype && skia_use_fontconfig

PLATFORMS:
- skia_enable_android_utils = is_skia_dev_build (+50KB)
- skia_enable_winuwp = false (Windows UWP)
- skia_enable_api_available_macro = true (SK_API_AVAILABLE on macOS/iOS)

DEBUG & TOOLS:
- skia_enable_tools = is_skia_dev_build (+20MB; requires static+ganesh; test/benchmark apps)
- skia_enable_gpu_debug_layers = is_skia_dev_build && is_debug (+500KB)
- skia_enable_discrete_gpu = true (prefer discrete GPU)

SPIRV & SHADERS:
- skia_enable_spirv_validation = is_skia_dev_build && is_debug && !skia_use_dawn (+200KB)
- skia_enable_vello_shaders = false (experimental)
- skia_enable_sksl_tracing = is_skia_dev_build && !skia_enable_optimize_size (DEPRECATED)
- skia_disable_tracing = is_official_build (disable SK_TRACE)

GL Standard (mutually exclusive, auto-set):
  skia_gl_standard in { "gl", "gles", "webgl", "" }
  Default: is_mac → "gl"; is_ios → "gles"; is_wasm && ganesh → "webgl"; else ""

### 1.3 Build & Toolchain Arguments
From /gn/toolchain/BUILD.gn and /gn/skia/BUILD.gn.

COMPILER SELECTION:
- target_cc = "cc" (C compiler)
- target_cxx = "cxx" (C++ compiler)
- target_ar = "ar" (archiver)
- cc_wrapper = "" (ccache/sccache/goma)

COMPILER FLAGS:
- extra_asmflags = []
- extra_cflags = []
- extra_cflags_c = []
- extra_cflags_cc = []
- extra_ldflags = []

MEMORY:
- malloc = "" (jemalloc/tcmalloc/mimalloc)

ERROR HANDLING:
- werror = false (warnings as errors)

XCODE (macOS/iOS):
- xcode_sysroot = auto-detected

PARALLELISM:
- dlsymutil_pool_depth = CPU count (macOS)
- link_pool_depth = -1 (no limit)

HARDCODED SETTINGS:
- C++ Standard: C++17
  Windows MSVC: /std:c++17 (line 108)
  Unix/Clang: -std=c++17 (line 147)
  
- Visibility & ABI:
  Unix: -fvisibility=hidden -fvisibility-inlines-hidden
  RTTI: -fno-rtti (except ASAN)
  Exceptions: -fno-exceptions (Unix); /EHsc implicit (MSVC); _HAS_EXCEPTIONS=0 (Windows)

### 1.4 Unicode/ICU Strategy Matrix

Decision tree (gn/skia.gni:133-138):
  skia_enable_skunicode = skia_use_icu || skia_use_client_icu || 
                          skia_use_libgrapheme || skia_use_icu4x

STRATEGIES:
1. Full ICU (embedded):
   - Args: skia_use_icu=true (default)
   - Binary: +8-15MB
   - Capabilities: Bidi (yes), Line break UAX#14 (yes), Grapheme (yes), Word break (yes)
   - External data: No (icudtl.dat embedded in libicu.a)
   - File: modules/skunicode/src/SkUnicode_icu_builtin.cpp

2. Full ICU (runtime):
   - Args: skia_use_icu=true + skia_use_runtime_icu=true (Android/Linux only)
   - Binary: +3-5MB
   - Capabilities: Same as embedded
   - External data: Yes (icudtl.dat separate file)
   - File: modules/skunicode/src/SkUnicode_icu_runtime.cpp

3. Client-provided ICU:
   - Args: skia_use_client_icu=true
   - Binary: 0 bytes (Skia side)
   - Capabilities: Caller defines via SkUnicode::Make(icu_provider)
   - External: Yes (app provides)
   - File: modules/skunicode/src/SkUnicode_client.cpp

4. ICU4X (Rust subset):
   - Args: skia_use_icu4x=true
   - Binary: +2-4MB
   - Capabilities: Bidi (yes), Line break (partial), Grapheme (limited), Word break (limited)
   - External: No
   - File: (not yet integrated; placeholder)

5. libgrapheme only:
   - Args: skia_use_libgrapheme=true
   - Binary: +300KB
   - Capabilities: Bidi (no), Line break (no), Grapheme (yes), Word break (no)
   - External: No (pure Rust)
   - File: modules/skunicode/src/SkUnicode_libgrapheme.cpp

### 1.5 Codec Availability Matrix

DECODERS (default enabled):
- BMP/WBMP: Always (hardcoded; SK_CODEC_DECODES_BMP, SK_CODEC_DECODES_WBMP)
- GIF: skia_use_wuffs=true (default; wuffs library)
- JPEG: skia_use_libjpeg_turbo_decode=true (libjpeg-turbo; +1.2MB total with encode)
- JPEG Gainmaps: skia_use_jpeg_gainmaps=is_skia_dev_build (extension; +50KB)
- JPEG XL: skia_use_libjxl_decode=false (libjxl; +700KB)
- PNG: skia_use_libpng_decode=true (libpng; +1.1MB total with encode)
- WebP: skia_use_libwebp_decode=true (libwebp; +1.0MB total with encode)
- AVIF: skia_use_libavif=false (libavif AV1; +500KB)
- HEIF/H.265: skia_use_libheif=is_skia_dev_build (libheif; +400KB; dev-only)
- RAW/DNG: skia_use_dng_sdk=derived (requires JPEG+zlib; +300KB)

ENCODERS (overridable):
- JPEG: skia_use_libjpeg_turbo_encode=true; block with skia_use_no_jpeg_encode=true
- PNG: skia_use_libpng_encode=true; block with skia_use_no_png_encode=true
- WebP: skia_use_libwebp_encode=!is_wasm; block with skia_use_no_webp_encode=true

---

## 2. MODULE TARGETS & STATIC LIBRARY ARTIFACTS

All modules gate on skia_enable_* arg. From modules/*/BUILD.gn and modules/*/MODULE.gni.

Ninja targets and output .a files:

MODULE          GATED_BY                    TYPE        LINK_TARGET    BINARY        DEPS
skshaper        skia_enable_skshaper        component   ":skshaper"    +2MB          skia, harfbuzz, skunicode*
                (default true)

skparagraph     skia_enable_skparagraph     component   ":skparagraph" +800KB        skia, skshaper, skunicode
                (default true)

skunicode       skia_enable_skunicode       component   ":skunicode"   0-15MB        skia, ICU/libgrapheme/icu4x
                (derived)

skottie         skia_enable_skottie         component   ":skottie"     +1.5MB        skia, skunicode, sksg, 
                                                                                      skresources, lottie (external)

svg             skia_enable_svg             component   ":svg"         +500KB        skia, expat
                (!is_component_build)

sksg            implicit (skottie dep)      static_lib  ":sksg"        +300KB        skia

skresources     implicit (skottie dep)      static_lib  ":skresources" +100KB        skia

skcms           always                      static_lib  ":skcms"       +150KB        (none)

pathops         always                      static_lib  ":pathops"     +200KB        skia

bentleyottmann  always                      static_lib  ":bentleyottmann" +50KB     (none)

json            always                      static_lib  ":json"        +100KB        (none)

particles       implicit (skottie)          static_lib  ":particles"   +100KB        skia, sksg, skresources

Dependency tree:
  skottie → sksg, skresources, skunicode, lottie
  skparagraph → skshaper → skunicode, harfbuzz, freetype*
  Core (always): skcms, pathops, bentleyottmann, json, particles

GNI source files (auto-generated from Bazel):
  modules/skshaper/skshaper.gni: skia_shaper_*_sources
  modules/skparagraph/skparagraph.gni: skia_paragraph_*_sources
  modules/skunicode/skunicode.gni: skia_unicode_*_sources
  modules/skottie/skottie.gni: skia_skottie_*_sources
  modules/svg/svg.gni: skia_svg_*_sources

---

## 3. FONT MANAGER SELECTION

Automatic selection via skia_fontmgr_factory derived arg (gn/skia.gni:175-198):

if (skia_enable_fontmgr_empty)
  → ":fontmgr_empty_factory" (null; app provides fonts)

else if (is_android && skia_enable_fontmgr_android)
  → ":fontmgr_android_factory" (/system/fonts via expat+freetype)

else if (is_win && skia_enable_fontmgr_win)
  → ":fontmgr_win_factory" (Windows Registry GDI)

else if ((is_mac || is_ios) && skia_use_fonthost_mac)
  → ":fontmgr_mac_ct_factory" (CoreText/CoreFoundation)

else if (skia_enable_fontmgr_fontconfig)
  → ":fontmgr_fontconfig_factory" (fontconfig+FreeType on Linux)

else if (skia_enable_fontmgr_custom_directory)
  → ":fontmgr_custom_directory_factory" (app directory)

else if (skia_enable_fontmgr_custom_embedded)
  → ":fontmgr_custom_embedded_factory" (embedded directory)

else if (skia_enable_fontmgr_custom_empty)
  → ":fontmgr_custom_empty_factory" (stub)

else
  → ":fontmgr_empty_factory" (FALLBACK)

Recommendations:
- Mobile (Android): skia_enable_fontmgr_android=true
- macOS/iOS: skia_use_fonthost_mac=true
- Linux: skia_enable_fontmgr_fontconfig=true
- Windows: skia_enable_fontmgr_win=true
- Embedded: skia_enable_fontmgr_custom_directory or empty

---

## 4. SINGLE FAT STATIC LIB

Skia does NOT produce a single fat .a by default.

Default outputs (per-module):
  libskia.a, libskshaper.a, libskparagraph.a, libskunicode.a,
  libskottie.a, libsvg.a, libsksg.a, libskresources.a, libskcms.a,
  libpathops.a, libbentleyottmann.a, libjson.a, libparticles.a

MERGING METHOD 1: ar MRI Script (portable POSIX)
  Create merge_script.mri:
    create out/Release/libskia_fat.a
    addlib out/Release/libskia.a
    addlib out/Release/libskshaper.a
    addlib out/Release/libskparagraph.a
    addlib out/Release/libskunicode.a
    addlib out/Release/libskottie.a
    addlib out/Release/libsvg.a
    ...
    save
    end

  ar -M < merge_script.mri

MERGING METHOD 2: Python (official Skia tool)
  python3 tools/merge_static_libs.py out/Release/libskia_fat.a \
    out/Release/libskia.a out/Release/libskshaper.a ...

  (Source: tools/merge_static_libs.py; uses ar -x + ar -crs on POSIX,
   lib /OUT: on Windows)

MERGING METHOD 3: libtool (macOS)
  libtool -static -o libskia_fat.a libskia.a libskshaper.a ...

MERGING METHOD 4: llvm-ar (LLVM)
  llvm-ar x libskia.a -o objs/
  llvm-ar x libskshaper.a -o objs/
  ...
  llvm-ar crs libskia_fat.a objs/*.o

---

## 5. DEPENDENCY FETCHING & BUILD INITIALIZATION

### 5.1 tools/git-sync-deps (lightweight, no gclient required)

Usage: ./tools/git-sync-deps

Behavior:
- Reads DEPS file in repo root
- Clones each dep at specified commit
- Allows per-repo disable: cd third_party/libpng && git config sync-deps.disable true

DEPS structure (root DEPS file):
  use_relative_paths = True
  
  vars = {
    'sk_tool_revision': 'git_revision:382c1d1c...',
    'ninja_version': 'version:2@1.8.2.chromium.3',
  }
  
  deps = {
    "buildtools": "https://chromium.googlesource.com/chromium/src/buildtools.git@<sha>",
    "third_party/externals/angle2": "https://chromium.googlesource.com/angle/angle.git@<sha>",
    "third_party/externals/brotli": "https://...",
    ...  # ~200+ entries
  }

Key deps fetched:
  buildtools/ (GN, Clang)
  third_party/externals/ (libjpeg-turbo, libpng, libwebp, harfbuzz, freetype,
                          fontconfig, ICU, vulkan, angle, etc.)
  third_party/icu/ (full ICU library)
  third_party/icu_bidi/ (minimal bidi-only ICU)

### 5.2 Minimal/Offline sync

Option A: Comment unwanted DEPS
  sed -i 's/^  "third_party\/externals\/angle2"/  # "third_party\/externals\/angle2"/' DEPS

Option B: Use GN args to disable optional deps
  gn gen out/Release --args='
    skia_use_angle=false
    skia_use_dawn=false
    skia_use_libjxl_decode=false
  '

Option C: Air-gapped build
  1. Clone + sync on connected machine
     git clone https://chromium.googlesource.com/skia.git
     ./tools/git-sync-deps
  2. Tar: tar czf skia-m120-complete.tar.gz skia/
  3. On air-gapped machine: tar xzf skia-m120-complete.tar.gz
  4. Build with pre-fetched deps

### 5.3 GN & Ninja

Modern Skia (m120):
  GN and Ninja are in buildtools/ (fetched by DEPS)
  buildtools/gn --version
  buildtools/ninja --version

---

## 6. MINIMAL vs MAXIMAL BUILD EXAMPLES

MINIMAL (embedded, size-optimized):
  gn gen out/minimal --args='
    is_official_build=true
    is_debug=false
    is_component_build=false
    
    skia_enable_ganesh=false
    skia_enable_graphite=false
    skia_use_gl=false
    skia_use_vulkan=false
    
    skia_enable_pdf=false
    skia_enable_svg=false
    skia_enable_skottie=false
    
    skia_use_libjpeg_turbo_decode=false
    skia_use_libpng_decode=false
    skia_use_libwebp_decode=false
    skia_use_harfbuzz=false
    skia_use_icu=false
    skia_use_freetype=false
    skia_enable_fontmgr_empty=true
    
    skia_enable_tools=false
    extra_cflags="-Os"
  '
  
  Result: ~2-3 MB (pure rasterization only)

MAXIMAL (all features):
  gn gen out/maximal --args='
    is_official_build=true
    is_debug=false
    is_component_build=false
    
    skia_enable_ganesh=true
    skia_enable_graphite=true
    skia_use_gl=true
    skia_use_vulkan=true
    skia_use_metal=true
    skia_use_direct3d=true
    
    skia_enable_pdf=true
    skia_enable_svg=true
    skia_enable_skottie=true
    skia_enable_skshaper=true
    skia_enable_skparagraph=true
    
    skia_use_libjpeg_turbo_decode=true
    skia_use_libjpeg_turbo_encode=true
    skia_use_libpng_decode=true
    skia_use_libpng_encode=true
    skia_use_libwebp_decode=true
    skia_use_libwebp_encode=true
    skia_use_libavif=true
    skia_use_libjxl_decode=true
    
    skia_use_harfbuzz=true
    skia_use_icu=true
    skia_use_freetype=true
    skia_use_fontconfig=true
  '
  
  Result: ~30-40 MB (all backends + codecs)

---

## 7. QUICK REFERENCE: KNOWN PATCH POINTS

Common downstream patches:
1. Symbol visibility: Define HB_NO_VISIBILITY for HarfBuzz
2. ICU symbol prefixing: Rename u_* to skia_icu_* to avoid collisions
3. Strip tools: skia_enable_tools=false (tests/benchmarks)
4. Force client ICU: skia_use_client_icu=true (match app's ICU)
5. Disable experimental: skia_enable_graphite=false
6. Linker flags: Add -Wl,--exclude-libs=ALL (hide vendored symbols)
7. C++ ABI: Force -stdlib=libc++ (match consumer)
8. Dependency trimming: Disable unused codecs (wuffs, piex, jxl, heif, avif)

---

## 8. VALIDATION CHECKLIST

Before building, verify:
✓ skia_use_dng_sdk → requires (skia_use_libjpeg_turbo_decode && skia_use_zlib)
✓ skia_use_angle → skia_gl_standard == "gles"
✓ skia_use_dawn → skia_enable_graphite == true
✓ skia_enable_tools → is_component_build == false && skia_enable_ganesh == true
✓ skia_enable_skparagraph → skia_enable_skshaper == true
✓ skia_enable_skottie → skia_enable_sksg == true
✓ Font manager: only ONE primary (auto-selected)

---

END OF DOCUMENT

Source files reference:
  gn/skia.gni - ALL GN args
  gn/toolchain/BUILD.gn - Toolchain args
  gn/skia/BUILD.gn - Compiler flags, visibility/ABI
  modules/*/BUILD.gn - Module gating
  modules/*/MODULE.gni - Source lists (auto-gen from Bazel)
  BUILD.gn - Codec matrix (lines 1100-1410)
  DEPS - Dependency list
  tools/merge_static_libs.py - FAT lib merging
  tools/git-sync-deps - Dependency syncing

Skia chrome/m120 branch audit: September 2026
