// libskia2 冒烟测试
//
// 验证目标不是"能编过"，而是 doc/gui-framework-profile.md §7 里那几条
// 决定 libgrapheme 文本方案够不够用的断言。任何一条不过，就说明该退回完整 ICU。
//
// 不测 GPU 路径 —— CI runner 无 GL 上下文。CPU 光栅走的是同一套绘制命令录制，
// 足以验证 libskia.a 的核心可用。

#include <cstdio>
#include <string>
#include <vector>

#include "include/codec/SkCodec.h"
#include "include/codec/SkPngDecoder.h"
#include "include/core/SkBlurTypes.h"
#include "include/core/SkCanvas.h"
#include "include/core/SkColor.h"
#include "include/core/SkData.h"
#include "include/core/SkFontMgr.h"
#include "include/core/SkImageInfo.h"
#include "include/core/SkMaskFilter.h"
#include "include/core/SkPaint.h"
#include "include/core/SkPoint.h"
#include "include/core/SkRRect.h"
#include "include/core/SkStream.h"
#include "include/core/SkSurface.h"
#include "include/effects/SkGradientShader.h"
#include "include/encode/SkPngEncoder.h"
#include "include/private/base/SkTArray.h"
#include "modules/skparagraph/include/FontCollection.h"
#include "modules/skparagraph/include/Paragraph.h"
#include "modules/skparagraph/include/ParagraphBuilder.h"
#include "modules/skparagraph/include/ParagraphStyle.h"
#include "modules/skparagraph/include/TextStyle.h"
#include "modules/skunicode/include/SkUnicode.h"
#include "modules/skunicode/include/SkUnicode_libgrapheme.h"
#include "modules/svg/include/SkSVGDOM.h"

#ifdef SK_BUILD_FOR_WIN
#include "include/ports/SkTypeface_win.h"
#else
#include "include/ports/SkFontMgr_fontconfig.h"
#include "include/ports/SkFontScanner_FreeType.h"
#endif

namespace {

int g_failures = 0;

void check(bool ok, const char* name, const std::string& detail) {
    std::printf("%-28s %s   %s\n", name, ok ? "PASS" : "FAIL", detail.c_str());
    if (!ok) {
        ++g_failures;
    }
}

sk_sp<SkFontMgr> makeFontMgr() {
#ifdef SK_BUILD_FOR_WIN
    return SkFontMgr_New_DirectWrite();
#else
    return SkFontMgr_New_FontConfig(nullptr, SkFontScanner_Make_FreeType());
#endif
}

size_t countFlag(const skia_private::TArray<SkUnicode::CodeUnitFlags, true>& flags,
                 SkUnicode::CodeUnitFlags wanted) {
    size_t n = 0;
    for (int i = 0; i < flags.size(); ++i) {
        if (flags[i] & wanted) {
            ++n;
        }
    }
    return n;
}

// 完整走一遍 CPU 光栅：渐变 + 圆角 + 模糊阴影 -> PNG 编码 -> 落盘 -> 再解码回来。
// 一次覆盖 core 绘制、SkPngEncoder、SkPngDecoder 三处。
void testRasterAndCodec(const char* outPath) {
    constexpr int kW = 320, kH = 200;
    auto surface = SkSurfaces::Raster(SkImageInfo::MakeN32Premul(kW, kH));
    if (!surface) {
        check(false, "raster.surface", "SkSurfaces::Raster 返回 nullptr");
        return;
    }
    SkCanvas* canvas = surface->getCanvas();
    canvas->clear(SK_ColorWHITE);

    SkPaint shadow;
    shadow.setColor(SkColorSetARGB(90, 0, 0, 0));
    shadow.setMaskFilter(SkMaskFilter::MakeBlur(kNormal_SkBlurStyle, 8.0f));
    canvas->drawRRect(SkRRect::MakeRectXY(SkRect::MakeXYWH(44, 40, 232, 120), 20, 20), shadow);

    const SkPoint pts[2] = {{40, 30}, {280, 150}};
    const SkColor colors[2] = {SK_ColorBLUE, SK_ColorMAGENTA};
    SkPaint fill;
    fill.setAntiAlias(true);
    fill.setShader(SkGradientShader::MakeLinear(pts, colors, nullptr, 2, SkTileMode::kClamp));
    canvas->drawRRect(SkRRect::MakeRectXY(SkRect::MakeXYWH(40, 30, 232, 120), 20, 20), fill);

    SkPixmap pixmap;
    if (!surface->peekPixels(&pixmap)) {
        check(false, "raster.peekPixels", "peekPixels 失败");
        return;
    }
    SkFILEWStream out(outPath);
    const bool encoded = out.isValid() && SkPngEncoder::Encode(&out, pixmap, {});
    out.fsync();
    check(encoded, "raster.pngEncode", outPath);

    sk_sp<SkData> png = SkData::MakeFromFileName(outPath);
    std::unique_ptr<SkCodec> codec =
            png ? SkPngDecoder::Decode(png, nullptr) : nullptr;
    const bool decoded = codec && codec->dimensions().width() == kW &&
                         codec->dimensions().height() == kH;
    check(decoded, "raster.pngDecode",
          decoded ? std::to_string(kW) + "x" + std::to_string(kH) : "解码失败或尺寸不符");
}

// grapheme cluster 是光标移动与退格删除的最小单位。
// computeCodeUnitFlags 在每个簇边界（含末尾）打 kGraphemeStart，
// 因此标记数 == 簇数 + 1。
void testGrapheme(sk_sp<SkUnicode> unicode) {
    struct Case {
        const char* name;
        std::string text;
        size_t clusters;
    };
    const Case cases[] = {
            {"unicode.grapheme.zwj", "\U0001F468\u200D\U0001F469\u200D\U0001F467\u200D\U0001F466", 1},
            {"unicode.grapheme.skin", "a\U0001F44D\U0001F3FDb", 3},
            {"unicode.grapheme.flag", "\U0001F1E8\U0001F1F3", 1},
    };
    for (const Case& c : cases) {
        std::string buf = c.text;
        skia_private::TArray<SkUnicode::CodeUnitFlags, true> flags;
        const bool ok = unicode->computeCodeUnitFlags(
                buf.data(), static_cast<int>(buf.size()), false, &flags);
        const size_t marks = ok ? countFlag(flags, SkUnicode::kGraphemeStart) : 0;
        check(ok && marks == c.clusters + 1, c.name,
              "期望 " + std::to_string(c.clusters) + " 簇，实得 " +
                      std::to_string(marks ? marks - 1 : 0));
    }
}

// CJK 不以空格分词，断行完全依赖 UAX#14 规则表。
// 这是 libgrapheme 方案最关键的一条：不过就必须退回完整 ICU。
void testLineBreakCJK(sk_sp<SkUnicode> unicode) {
    std::string text = "中文没有空格所以断行完全依赖规则表";
    skia_private::TArray<SkUnicode::CodeUnitFlags, true> flags;
    const bool ok = unicode->computeCodeUnitFlags(
            text.data(), static_cast<int>(text.size()), false, &flags);
    const size_t breaks = ok ? countFlag(flags, SkUnicode::kSoftLineBreakBefore) : 0;
    // 16 个汉字，UAX#14 应给出远多于 2 个断点；只有首尾说明规则表没生效。
    check(ok && breaks > 4, "unicode.lineBreak.cjk",
          "软断点数 " + std::to_string(breaks));
}

// 双击选词依赖词边界。
void testWords(sk_sp<SkUnicode> unicode) {
    std::string text = "hello world foo";
    std::vector<SkUnicode::Position> words;
    const bool ok = unicode->getUtf8Words(
            text.data(), static_cast<int>(text.size()), "en", &words);
    check(ok && words.size() >= 3, "unicode.words",
          "词边界数 " + std::to_string(words.size()));
}

// libgrapheme 后端自带 icu_bidi 子集，这条验证它确实工作 ——
// 如果不工作，RTL 文本能力就是缺失的。
void testBidi(sk_sp<SkUnicode> unicode) {
    std::string text = "hello \u0645\u0631\u062D\u0628\u0627 world";
    std::vector<SkUnicode::BidiRegion> regions;
    const bool ok = unicode->getBidiRegions(
            text.data(), static_cast<int>(text.size()),
            SkUnicode::TextDirection::kLTR, &regions);
    bool hasRtl = false;
    for (const auto& r : regions) {
        if (r.level % 2 == 1) {
            hasRtl = true;
        }
    }
    check(ok && regions.size() >= 2 && hasRtl, "unicode.bidi",
          "区段数 " + std::to_string(regions.size()) +
                  "，含 RTL: " + (hasRtl ? "是" : "否"));
}

void testParagraph(sk_sp<SkUnicode> unicode, sk_sp<SkFontMgr> fontMgr) {
    auto collection = sk_make_sp<skia::textlayout::FontCollection>();
    collection->setDefaultFontManager(fontMgr);
    collection->enableFontFallback();

    skia::textlayout::ParagraphStyle paraStyle;
    skia::textlayout::TextStyle textStyle;
    textStyle.setColor(SK_ColorBLACK);
    textStyle.setFontSize(18);
    paraStyle.setTextStyle(textStyle);

    auto builder = skia::textlayout::ParagraphBuilder::make(paraStyle, collection, unicode);
    if (!builder) {
        check(false, "paragraph.builder", "ParagraphBuilder::make 返回 nullptr");
        return;
    }
    builder->addText("中文排版换行测试文本用来验证段落布局是否真的工作");
    auto paragraph = builder->Build();
    paragraph->layout(120.0f);
    const size_t lines = paragraph->lineNumber();
    check(paragraph != nullptr && lines > 1, "paragraph.layout",
          "行数 " + std::to_string(lines) + "（宽 120px）");
}

void testSvg(sk_sp<SkFontMgr> fontMgr) {
    static constexpr char kSvg[] =
            R"(<svg xmlns="http://www.w3.org/2000/svg" width="64" height="64">)"
            R"(<circle cx="32" cy="32" r="28" fill="#3b82f6"/></svg>)";
    auto stream = SkMemoryStream::MakeDirect(kSvg, sizeof(kSvg) - 1);
    auto dom = SkSVGDOM::Builder().setFontManager(fontMgr).make(*stream);
    if (!dom) {
        check(false, "svg.parse", "SkSVGDOM 构建失败");
        return;
    }
    dom->setContainerSize(SkSize::Make(64, 64));
    auto surface = SkSurfaces::Raster(SkImageInfo::MakeN32Premul(64, 64));
    surface->getCanvas()->clear(SK_ColorTRANSPARENT);
    dom->render(surface->getCanvas());

    SkPixmap pm;
    bool painted = false;
    if (surface->peekPixels(&pm)) {
        painted = SkColorGetA(pm.getColor(32, 32)) > 0;
    }
    check(painted, "svg.render", painted ? "中心像素非透明" : "渲染后中心仍透明");
}

}  // namespace

int main(int argc, char** argv) {
    const char* outPath = argc > 1 ? argv[1] : "libskia2-smoke.png";

    sk_sp<SkUnicode> unicode = SkUnicodes::Libgrapheme::Make();
    if (!unicode) {
        std::printf("SkUnicodes::Libgrapheme::Make() 返回 nullptr —— 文本栈完全不可用\n");
        return 1;
    }
    sk_sp<SkFontMgr> fontMgr = makeFontMgr();
    check(fontMgr != nullptr, "fontmgr.create",
          fontMgr ? std::to_string(fontMgr->countFamilies()) + " 个字体族" : "nullptr");

    testRasterAndCodec(outPath);
    testGrapheme(unicode);
    testLineBreakCJK(unicode);
    testWords(unicode);
    testBidi(unicode);
    testSvg(fontMgr);
    if (fontMgr) {
        testParagraph(unicode, fontMgr);
    }

    std::printf("\n%d 项失败\n", g_failures);
    return g_failures == 0 ? 0 : 1;
}
