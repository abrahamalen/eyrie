"""Draws Eyrie's tray and app icons (run: python3 widget/make_icons.py; needs Pillow and
`make setup` for the Geist font in frontend/node_modules).

The mark is the app's logo: "e." in Geist Bold. Tray icons are monochrome macOS template
images, so the menu bar tints them for light or dark. The dot is where state shows: a small
dot when all is fine, a big raised dot for "needs you", an exclamation mark for "problem"."""
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "widget" / "src-tauri" / "icons"
FONT = ROOT / "frontend/node_modules/@fontsource-variable/geist/files/geist-latin-wght-normal.woff2"
SS = 8  # supersampling factor for smooth edges
INK, PAPER, BRAND = (25, 31, 46, 255), (246, 244, 239, 255), (13, 132, 158, 255)


def font(size: float) -> ImageFont.FreeTypeFont:
    f = ImageFont.truetype(str(FONT), round(size))
    f.set_variation_by_axes([700])
    return f


def mark(d: ImageDraw.ImageDraw, S: float, colour, dot_colour=None, state: str = "ok", tight: bool = True) -> None:
    """ "e." drawn into an S x S square. tight=True fills the square (tray); else leaves room (tile)."""
    f = font(S * (1.25 if tight else 0.78))
    l, t, r, b = d.textbbox((0, 0), "e", font=f)
    gw, gh = r - l, b - t
    dot = gh * 0.26
    total = gw + dot * 0.55 + dot
    x = (S - total) / 2 - l
    y = (S - gh) / 2 - t
    d.text((x, y), "e", font=f, fill=colour)
    dx = x + l + gw + dot * 0.55  # dot's left edge
    base = y + t + gh
    c = dot_colour or colour
    if state == "ok":
        d.ellipse([dx, base - dot, dx + dot, base], fill=c)
    elif state == "attention":
        R = dot * 1.5  # sits on the e's shoulder, kept inside the square
        left = min(dx - R * 0.2, S - R)
        top = max(0, y + t - R * 0.2)
        d.ellipse([left, top, left + R, top + R], fill=c)
    elif state == "problem":
        w = dot * 0.95
        d.rounded_rectangle([dx, y + t, dx + w, base - dot * 1.5], radius=w / 2, fill=c)
        d.ellipse([dx, base - w, dx + w, base], fill=c)


def tray(name: str, px: int, state: str) -> None:
    S = px * SS
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    mark(ImageDraw.Draw(img), S, (0, 0, 0, 255), state=state)
    img.resize((px, px), Image.LANCZOS).save(OUT / name)


def app_icon(px: int = 1024) -> None:
    S = px * 2
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    pad = S * 0.08
    d.rounded_rectangle([pad, pad, S - pad, S - pad], radius=S * 0.2, fill=INK)
    mark(d, S, PAPER, dot_colour=BRAND, tight=False)
    img.resize((px, px), Image.LANCZOS).save(OUT / "app-icon.png")


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    for state in ("ok", "attention", "problem"):
        tray(f"tray-{state}.png", 22, state)
        tray(f"tray-{state}@2x.png", 44, state)
    app_icon()
    print("wrote", sorted(p.name for p in OUT.iterdir()))
