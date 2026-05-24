"""Generate PWA icons for Phase Detector.

W12-E: produces 192x192, 512x512 (regular) and 512x512 (maskable) PNG icons
with a wordmark "P" on the Phase Detector brand purple (#5B21B6).

Run once at build time; output committed under
``web/phase-detector/public/icons/``.
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

BRAND_BG = (91, 33, 182)  # #5B21B6 — Phase Detector primary
LETTER_COLOR = (255, 255, 255)
OUT_DIR = Path(__file__).resolve().parents[1] / "web" / "phase-detector" / "public" / "icons"


def _load_font(size: int) -> ImageFont.FreeTypeFont:
    # Try common system fonts on macOS / Linux; fall back to PIL default.
    candidates = [
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
        "/System/Library/Fonts/SFNS.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf",
    ]
    for path in candidates:
        p = Path(path)
        if p.exists():
            try:
                return ImageFont.truetype(str(p), size=size)
            except Exception:
                continue
    return ImageFont.load_default()


def _draw_icon(size: int, maskable: bool) -> Image.Image:
    img = Image.new("RGBA", (size, size), BRAND_BG + (255,))
    draw = ImageDraw.Draw(img)
    # For maskable, leave ~10% safe area; render letter slightly smaller.
    letter_size = int(size * (0.45 if maskable else 0.6))
    font = _load_font(letter_size)
    text = "P"
    bbox = draw.textbbox((0, 0), text, font=font)
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]
    # Center precisely (textbbox returns offsets that include side-bearing).
    x = (size - tw) // 2 - bbox[0]
    y = (size - th) // 2 - bbox[1]
    draw.text((x, y), text, fill=LETTER_COLOR, font=font)
    return img


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    _draw_icon(192, maskable=False).save(OUT_DIR / "icon-192.png", "PNG")
    _draw_icon(512, maskable=False).save(OUT_DIR / "icon-512.png", "PNG")
    _draw_icon(512, maskable=True).save(OUT_DIR / "maskable-512.png", "PNG")
    print(f"wrote 3 icons to {OUT_DIR}")


if __name__ == "__main__":
    main()
