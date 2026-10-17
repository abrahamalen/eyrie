"""Draws Eyrie's tray and app icons (run: python3 widget/make_icons.py; needs Pillow).

The mark is a nest (an eyrie): a bowl of twigs with a bird above it. Tray icons are
monochrome macOS template images, so the menu bar tints them for light or dark; state is
shown by shape (a dot for "needs you", a warning mark for "problem")."""
from pathlib import Path

from PIL import Image, ImageDraw

OUT = Path(__file__).parent / "src-tauri" / "icons"
SS = 8  # supersampling factor for smooth edges


def nest(draw: ImageDraw.ImageDraw, s: float, ox: float, oy: float, colour, bird_colour=None) -> None:
    """The mark drawn into a square of side s (in px) at offset (ox, oy): an eyrie is a nest on
    a high crag, so a solid peak (with a lower shoulder) and a bird in flight above it."""
    P = lambda x, y: (ox + s * x, oy + s * y)  # noqa: E731
    draw.polygon([P(0.04, 0.92), P(0.46, 0.34), P(0.62, 0.56), P(0.72, 0.46), P(0.96, 0.92)], fill=colour)
    b = bird_colour or colour
    wing = max(1, round(s * 0.075))
    draw.line([P(0.54, 0.2), P(0.65, 0.12), P(0.74, 0.21)], fill=b, width=wing, joint="curve")
    draw.line([P(0.74, 0.21), P(0.83, 0.12), P(0.94, 0.2)], fill=b, width=wing, joint="curve")


def tray(name: str, px: int, badge: str | None) -> None:
    S = px * SS
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    nest(d, S, 0, 0, (0, 0, 0, 255))
    if badge == "dot":
        r = S * 0.17
        cx, cy = S * 0.18, S * 0.2
        d.ellipse([cx - r * 1.45, cy - r * 1.45, cx + r * 1.45, cy + r * 1.45], fill=(0, 0, 0, 0))  # gap
        d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(0, 0, 0, 255))
    elif badge == "warn":
        cx, top, h = S * 0.2, S * 0.02, S * 0.42
        tri = [(cx, top), (cx + h * 0.58, top + h), (cx - h * 0.58, top + h)]
        d.polygon(tri, fill=(0, 0, 0, 255))
        bar = S * 0.035
        d.rectangle([cx - bar, top + h * 0.32, cx + bar, top + h * 0.7], fill=(0, 0, 0, 0))
        d.ellipse([cx - bar, top + h * 0.78, cx + bar, top + h * 0.78 + bar * 2], fill=(0, 0, 0, 0))
    img.resize((px, px), Image.LANCZOS).save(OUT / name)


def app_icon(px: int = 1024) -> None:
    S = px * 2
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    pad = S * 0.08
    d.rounded_rectangle([pad, pad, S - pad, S - pad], radius=S * 0.2, fill=(25, 31, 46, 255))  # ink
    inner = S * 0.5
    nest(d, inner, (S - inner) / 2, (S - inner) / 2 + S * 0.02, (246, 244, 239, 255), bird_colour=(13, 132, 158, 255))
    img.resize((px, px), Image.LANCZOS).save(OUT / "app-icon.png")


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    for state, badge in (("ok", None), ("attention", "dot"), ("problem", "warn")):
        tray(f"tray-{state}.png", 22, badge)
        tray(f"tray-{state}@2x.png", 44, badge)
    app_icon()
    print("wrote", sorted(p.name for p in OUT.iterdir()))
