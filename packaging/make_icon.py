"""Erzeugt das App-Icon (Windows .ico, PNG für macOS/Installer) aus dem Fach-Zeichen.

Tinte-blaues Quadrat, darin weiß: ein Fach mit einem Blatt. Aufruf: python packaging/make_icon.py
"""
from pathlib import Path

from PIL import Image, ImageDraw

INK = (40, 70, 196, 255)
WHITE = (255, 255, 255, 255)
OUT = Path(__file__).parent / "assets"


def draw(size: int) -> Image.Image:
    s = size * 4  # überabgetastet, dann verkleinert = glatte Kanten
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([0, 0, s - 1, s - 1], radius=int(s * 0.22), fill=INK)
    m, w = s * 0.24, max(2, int(s * 0.055))
    box = [m, m, s - m, s - m]
    d.rounded_rectangle(box, radius=int(s * 0.1), outline=WHITE, width=w)
    shelf_y = m + (s - 2 * m) * 0.62
    d.rectangle([m, shelf_y - w / 2, s - m, shelf_y + w / 2], fill=WHITE)
    sheet = [m + (s - 2 * m) * 0.26, m + (s - 2 * m) * 0.27, s - m - (s - 2 * m) * 0.26, shelf_y]
    d.rounded_rectangle(sheet, radius=int(s * 0.02), fill=WHITE)
    return img.resize((size, size), Image.LANCZOS)


if __name__ == "__main__":
    OUT.mkdir(exist_ok=True)
    big = draw(1024)
    big.save(OUT / "fach.png")
    draw(256).save(OUT / "fach.ico", sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    print("geschrieben:", *sorted(p.name for p in OUT.iterdir()))
