import os
import io
import math
import re
import requests
from PIL import Image, ImageDraw, ImageFont

COUPLE_HTML = None  # unused, kept for reference

_TEMP_DIR = None


def _init_temp(temp_dir: str):
    global _TEMP_DIR
    _TEMP_DIR = temp_dir


def _temp_path(prefix: str) -> str:
    ts = re.sub(r'[^\d]', '', str(__import__('time').time()))
    os.makedirs(_TEMP_DIR, exist_ok=True) if _TEMP_DIR else None
    return os.path.join(_TEMP_DIR or os.getcwd(), f"{prefix}_{ts}.png")


def _avatar_img(qq: str) -> Image.Image:
    url = f"https://q4.qlogo.cn/headimg_dl?dst_uin={qq}&spec=640"
    resp = requests.get(url, timeout=10)
    resp.raise_for_status()
    return Image.open(io.BytesIO(resp.content)).convert("RGBA")


def _round_corners(img: Image.Image, r: int) -> Image.Image:
    mask = Image.new("L", img.size, 0)
    draw = ImageDraw.Draw(mask)
    draw.rounded_rectangle((0, 0, img.width, img.height), radius=r, fill=255)
    out = Image.new("RGBA", img.size)
    out.paste(img, (0, 0), mask)
    return out


def _try_font(size: int) -> ImageFont.FreeTypeFont:
    paths = [
        "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
        "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "C:/Windows/Fonts/simhei.ttf",
        "C:/Windows/Fonts/msyh.ttc",
        "C:/Windows/Fonts/simsun.ttc",
    ]
    for p in paths:
        if os.path.exists(p):
            try:
                return ImageFont.truetype(p, size)
            except Exception:
                continue

    # Scan Linux font dirs
    for d in ["/usr/share/fonts", "/usr/local/share/fonts"]:
        if not os.path.isdir(d):
            continue
        for root, _, files in os.walk(d):
            for f in sorted(files):
                if not f.lower().endswith((".ttf", ".ttc")):
                    continue
                fp = os.path.join(root, f)
                try:
                    font = ImageFont.truetype(fp, size)
                    bbox = ImageDraw.Draw(Image.new("L", (1, 1))).textbbox((0, 0), "中", font=font)
                    if bbox[2] - bbox[0] > 1:
                        return font
                except Exception:
                    continue
    return ImageFont.load_default()


async def render_couple(plugin, qq_a: str, qq_b: str, name_a: str, name_b: str) -> str:
    return _render_couple_pil(plugin, qq_a, qq_b, name_a, name_b)


def _render_couple_pil(plugin, qq_a: str, qq_b: str, name_a: str, name_b: str) -> str:
    if _TEMP_DIR is None:
        _init_temp(os.path.join(plugin.data_dir, "temp"))
    out = _temp_path("couple")

    av = 260
    gap = 50
    pad = 40
    w = pad * 2 + av * 2 + gap
    h = pad * 2 + av + 50
    canvas = Image.new("RGB", (w, h), (255, 255, 255))

    im_a = _round_corners(_avatar_img(qq_a).resize((av, av), Image.LANCZOS), 24)
    im_b = _round_corners(_avatar_img(qq_b).resize((av, av), Image.LANCZOS), 24)
    canvas.paste(im_a, (pad, pad), im_a)
    canvas.paste(im_b, (pad + av + gap, pad), im_b)

    draw = ImageDraw.Draw(canvas)
    fnt = _try_font(28)
    for name, cx in [(name_a, pad + av // 2), (name_b, pad + av + gap + av // 2)]:
        bbox = draw.textbbox((0, 0), name, font=fnt)
        tw = bbox[2] - bbox[0]
        draw.text((cx - tw // 2, pad + av + 8), name, fill=(80, 80, 80), font=fnt)

    # Heart
    hfnt = _try_font(48)
    cx, cy = w // 2, pad + av // 2
    hb = draw.textbbox((0, 0), "❤", font=hfnt)
    hw = hb[2] - hb[0]
    draw.text((cx - hw // 2, cy - (hb[3] - hb[1]) // 2), "❤", fill=(255, 77, 79), font=hfnt)

    canvas.save(out, "PNG")
    return out


async def render_grid(plugin, qq_list: list[str]) -> str:
    return _render_grid_pil(plugin, qq_list)


def _render_grid_pil(plugin, qq_list: list[str]) -> str:
    if _TEMP_DIR is None:
        _init_temp(os.path.join(plugin.data_dir, "temp"))
    out = _temp_path("grid")

    n = len(qq_list)
    if n == 0:
        return out
    cols = min(n, 5)
    rows = math.ceil(n / cols)
    cell = 200
    gap = 16
    pad = 20
    w = pad * 2 + cols * cell + (cols - 1) * gap
    h = pad * 2 + rows * cell + (rows - 1) * gap
    canvas = Image.new("RGB", (w, h), (255, 255, 255))

    for i, qq in enumerate(qq_list):
        try:
            im = _round_corners(_avatar_img(qq).resize((cell, cell), Image.LANCZOS), 20)
            x = pad + (i % cols) * (cell + gap)
            y = pad + (i // cols) * (cell + gap)
            canvas.paste(im, (x, y), im)
        except Exception:
            continue

    canvas.save(out, "PNG")
    return out
