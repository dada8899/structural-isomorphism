"""W12-B (session #10, 2026-05-15): generate 1200x630 OG card PNGs for
phase-detector pages.

Why a Python generator instead of @vercel/og: the production deploy is a
static Next.js export served by nginx — there's no edge runtime, no
fonts.googleapis.com call at request time, and we already have PIL
installed in the project venv. PIL renders consistent, byte-stable PNGs
that can be checked into git or generated as a build step.

Design (per CLAUDE.md "design competitors first" rule, sampling Linear /
Apple / Stripe / Lobehub / OpenWebUI OG cards 2026-05-15):

  +-----------------------------------------------------+
  | [double-circle mark]  Phase Detector                |
  |                                                     |
  |                                                     |
  |       <PAGE TITLE — large serif, 4-7 words>         |
  |                                                     |
  |       <Subtitle — 1 line, gray>                     |
  |                                                     |
  |                                                     |
  |                       phase.bytedance.city          |
  +-----------------------------------------------------+

  - 1200 x 630 PNG (Twitter + OG canonical size)
  - Background: #FAFAFA with subtle 1px border
  - Wordmark + double-circle logo (top-left)
  - Title in serif (Noto Serif SC fallback → DejaVu Serif → default)
  - Subtitle smaller, #525252
  - URL footer in JetBrains Mono (top-right or bottom-right)

Idempotent: identical inputs → identical PNG bytes.

Run:
    .venv/bin/python scripts/generate_og_cards.py
    ls web/phase-detector/public/og/*.png | wc -l   # expect ≥ 10
"""
from __future__ import annotations

import argparse
import dataclasses
import sys
from pathlib import Path
from typing import Optional

try:
    from PIL import Image, ImageDraw, ImageFont
except ImportError as exc:  # pragma: no cover
    print(f"PIL not installed: {exc}. Run pip install pillow.", file=sys.stderr)
    sys.exit(1)


REPO_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = REPO_ROOT / "web" / "phase-detector" / "public" / "og"

CANVAS_W, CANVAS_H = 1200, 630
BG_COLOR = (250, 250, 250)  # #FAFAFA
BORDER_COLOR = (228, 228, 231)  # zinc-200
TEXT_PRIMARY = (24, 24, 27)  # zinc-900
TEXT_SECONDARY = (82, 82, 91)  # zinc-600
TEXT_TERTIARY = (161, 161, 170)  # zinc-400
ACCENT_COLOR = (79, 70, 229)  # indigo-600 — used sparingly for accent dot


@dataclasses.dataclass(frozen=True)
class OgCardSpec:
    """One OG card to generate."""

    slug: str  # output file slug (home, about, ...)
    title: str  # main headline
    subtitle: str  # 1-line subtitle
    eyebrow: Optional[str] = None  # small uppercase label above title


# 12 OG card specs covering all top-level + dynamic pages.
SPECS: list[OgCardSpec] = [
    OgCardSpec(
        slug="home",
        title="100 家公司的状态评分",
        subtitle="同一套数学：地震、银行挤兑、电网级联、上市公司。",
        eyebrow="Phase Detector",
    ),
    OgCardSpec(
        slug="companies",
        title="公司清单",
        subtitle="按动力学家族 / 临界点状态 / 行业筛选，100+ ticker。",
        eyebrow="Browse",
    ),
    OgCardSpec(
        slug="company",
        title="公司详情",
        subtitle="单家公司的相位评分 + 关键指标 + 30 天轨迹。",
        eyebrow="Detail",
    ),
    OgCardSpec(
        slug="universality",
        title="普适类清单",
        subtitle="26+ 个跨域普适类，每一类背后是同一组方程。",
        eyebrow="Taxonomy",
    ),
    OgCardSpec(
        slug="compare",
        title="对比",
        subtitle="2-5 家公司并排对比：CPS 状态、共享模式匹配。",
        eyebrow="Compare",
    ),
    OgCardSpec(
        slug="pricing",
        title="定价",
        subtitle="Free / Pro $19 / Team $99 — 给认真研究的人。",
        eyebrow="Pricing",
    ),
    OgCardSpec(
        slug="backtest",
        title="Backtest 透明度报告",
        subtitle="Walk-forward v0.1 — 927 tickers, 59 snapshots. 公开发布零结果。",
        eyebrow="Transparency",
    ),
    OgCardSpec(
        slug="about",
        title="关于",
        subtitle="Phase Detector 的来源、团队、价值取向。",
        eyebrow="About",
    ),
    OgCardSpec(
        slug="methodology",
        title="方法",
        subtitle="怎么打分、怎么分类、AI 怎么从公开资料里读出来。",
        eyebrow="Methodology",
    ),
    OgCardSpec(
        slug="newsletter",
        title="Structural Signals — 每周一封",
        subtitle="相位翻转 + 方法论 + 跨域 preprint。无广告无列表买卖。",
        eyebrow="Newsletter",
    ),
    OgCardSpec(
        slug="newsletter-001",
        title="Structural Signals #001",
        subtitle="10 phase flips, block-bootstrap CIs, 4 cross-domain preprints.",
        eyebrow="Issue · 2026-05-15",
    ),
    OgCardSpec(
        slug="newsletter-rss",
        title="Newsletter RSS",
        subtitle="订阅 Structural Signals 的 RSS feed (RSS 2.0).",
        eyebrow="RSS",
    ),
]


def _try_font(candidates: list[Path | str], size: int) -> ImageFont.ImageFont:
    """Try a list of font paths/names in order; fall back to PIL default."""
    for cand in candidates:
        try:
            return ImageFont.truetype(str(cand), size)
        except (OSError, IOError):
            continue
    return ImageFont.load_default()


def _serif_font(size: int) -> ImageFont.ImageFont:
    return _try_font(
        [
            "/System/Library/Fonts/STHeiti Light.ttc",  # macOS CJK fallback
            "/System/Library/Fonts/Supplemental/Songti.ttc",
            "/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf",
            "DejaVuSerif-Bold.ttf",
        ],
        size,
    )


def _sans_font(size: int, bold: bool = False) -> ImageFont.ImageFont:
    if bold:
        return _try_font(
            [
                "/System/Library/Fonts/PingFang.ttc",
                "/System/Library/Fonts/Helvetica.ttc",
                "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
                "DejaVuSans-Bold.ttf",
            ],
            size,
        )
    return _try_font(
        [
            "/System/Library/Fonts/PingFang.ttc",
            "/System/Library/Fonts/Helvetica.ttc",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "DejaVuSans.ttf",
        ],
        size,
    )


def _mono_font(size: int) -> ImageFont.ImageFont:
    return _try_font(
        [
            "/System/Library/Fonts/Menlo.ttc",
            "/System/Library/Fonts/Monaco.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
            "DejaVuSansMono.ttf",
        ],
        size,
    )


def _draw_logo(draw: ImageDraw.ImageDraw, x: int, y: int, size: int = 28) -> None:
    """Render the double-circle Phase Detector mark.

    Matches the SVG in app/layout.tsx: two circles connected by a diagonal line.
    """
    radius = size // 4
    # Top-left circle.
    draw.ellipse(
        (x, y, x + radius * 2, y + radius * 2),
        outline=TEXT_PRIMARY,
        width=2,
    )
    # Bottom-right circle.
    cx2 = x + size - radius * 2
    cy2 = y + size - radius * 2
    draw.ellipse(
        (cx2, cy2, cx2 + radius * 2, cy2 + radius * 2),
        outline=TEXT_PRIMARY,
        width=2,
    )
    # Connecting line.
    draw.line(
        (x + radius * 2, y + radius * 2, cx2, cy2),
        fill=TEXT_PRIMARY,
        width=2,
    )


def _text_size(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont) -> tuple[int, int]:
    """Cross-version text size helper (textbbox on Pillow ≥ 8)."""
    try:
        l, t, r, b = draw.textbbox((0, 0), text, font=font)
        return r - l, b - t
    except AttributeError:  # very old Pillow
        return draw.textsize(text, font=font)  # type: ignore[attr-defined]


def _wrap_text(
    draw: ImageDraw.ImageDraw,
    text: str,
    font: ImageFont.ImageFont,
    max_width: int,
) -> list[str]:
    """Word-wrap. For CJK we wrap char-by-char as a fallback."""
    # Try whitespace split first.
    words = text.split()
    if len(words) > 1:
        lines: list[str] = []
        current = words[0]
        for w in words[1:]:
            tentative = f"{current} {w}"
            tw, _ = _text_size(draw, tentative, font)
            if tw <= max_width:
                current = tentative
            else:
                lines.append(current)
                current = w
        lines.append(current)
        return lines
    # CJK / no whitespace: per-char wrap.
    lines = []
    current = ""
    for ch in text:
        tentative = current + ch
        tw, _ = _text_size(draw, tentative, font)
        if tw <= max_width:
            current = tentative
        else:
            if current:
                lines.append(current)
            current = ch
    if current:
        lines.append(current)
    return lines


def render_card(spec: OgCardSpec, out_path: Path) -> None:
    """Render one OG card."""
    img = Image.new("RGB", (CANVAS_W, CANVAS_H), BG_COLOR)
    draw = ImageDraw.Draw(img)

    # Subtle inner border.
    draw.rectangle(
        (8, 8, CANVAS_W - 8, CANVAS_H - 8),
        outline=BORDER_COLOR,
        width=2,
    )

    # Top-left wordmark.
    pad_x, pad_y = 64, 56
    _draw_logo(draw, pad_x, pad_y, size=36)
    wm_font = _sans_font(28, bold=True)
    draw.text(
        (pad_x + 52, pad_y + 4),
        "Phase Detector",
        font=wm_font,
        fill=TEXT_PRIMARY,
    )

    # Eyebrow (uppercase tracking).
    if spec.eyebrow:
        eyebrow_font = _sans_font(20, bold=True)
        draw.text(
            (pad_x, pad_y + 110),
            spec.eyebrow.upper(),
            font=eyebrow_font,
            fill=ACCENT_COLOR,
        )

    # Title — large serif.
    title_font = _serif_font(72)
    title_lines = _wrap_text(draw, spec.title, title_font, CANVAS_W - 2 * pad_x)
    y_title = pad_y + 160 if spec.eyebrow else pad_y + 130
    for line in title_lines:
        draw.text((pad_x, y_title), line, font=title_font, fill=TEXT_PRIMARY)
        _, lh = _text_size(draw, line, title_font)
        y_title += lh + 8

    # Subtitle — smaller sans.
    subtitle_font = _sans_font(30)
    sub_lines = _wrap_text(draw, spec.subtitle, subtitle_font, CANVAS_W - 2 * pad_x)
    y_sub = y_title + 20
    for line in sub_lines:
        draw.text((pad_x, y_sub), line, font=subtitle_font, fill=TEXT_SECONDARY)
        _, lh = _text_size(draw, line, subtitle_font)
        y_sub += lh + 6

    # Footer URL (bottom-right) in mono.
    url_font = _mono_font(22)
    url = "phase.bytedance.city"
    uw, uh = _text_size(draw, url, url_font)
    draw.text(
        (CANVAS_W - pad_x - uw, CANVAS_H - pad_y - uh),
        url,
        font=url_font,
        fill=TEXT_TERTIARY,
    )

    # Footer label (bottom-left) — research preview disclaimer.
    fl_font = _sans_font(20)
    draw.text(
        (pad_x, CANVAS_H - pad_y - uh),
        "研究预览 · 不是投资建议",
        font=fl_font,
        fill=TEXT_TERTIARY,
    )

    out_path.parent.mkdir(parents=True, exist_ok=True)
    # `optimize=True` + fixed metadata keeps bytes stable across runs on same machine.
    img.save(out_path, format="PNG", optimize=True)


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate OG card PNGs.")
    parser.add_argument(
        "--out",
        default=str(OUTPUT_DIR),
        help="Output directory for PNG files.",
    )
    parser.add_argument("--list", action="store_true", help="List specs and exit.")
    args = parser.parse_args()

    out_dir = Path(args.out)
    if args.list:
        for s in SPECS:
            print(f"{s.slug:20s}  {s.title}")
        return 0

    print(f"Rendering {len(SPECS)} OG cards to {out_dir}")
    for spec in SPECS:
        out_path = out_dir / f"{spec.slug}.png"
        render_card(spec, out_path)
        print(f"  wrote {out_path.name}")
    print(f"Done: {len(SPECS)} files.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
