import os
import io
import math
import requests
from PIL import Image, ImageDraw, ImageFont

_AVATAR_SIZE = 320
_CANVAS_PADDING = 60
_HEART_GAP = 80
_BG_COLOR = (255, 255, 255)
_HEART_COLOR = (255, 77, 79)


def _avatar_url(qq: str) -> str:
    return f"https://q4.qlogo.cn/headimg_dl?dst_uin={qq}&spec=640"


def _download_avatar(url: str) -> Image.Image:
    resp = requests.get(url, timeout=10)
    resp.raise_for_status()
    img = Image.open(io.BytesIO(resp.content)).convert("RGBA")
    return img


def _round_corners(img: Image.Image, radius: int) -> Image.Image:
    mask = Image.new("L", img.size, 0)
    draw = ImageDraw.Draw(mask)
    draw.rounded_rectangle((0, 0, img.width, img.height), radius=radius, fill=255)
    rounded = Image.new("RGBA", img.size, (0, 0, 0, 0))
    rounded.paste(img, (0, 0), mask)
    return rounded


def _try_get_font(size: int) -> ImageFont.FreeTypeFont:
    font_paths = [
        # TrueType Fonts (prefer .ttf over .ttc for compatibility)
        "C:/Windows/Fonts/simhei.ttf",
        "C:/Windows/Fonts/simkai.ttf",
        "C:/Windows/Fonts/Deng.ttf",
        "C:/Windows/Fonts/Dengb.ttf",
        # TrueType Collections
        "C:/Windows/Fonts/msyh.ttc",
        "C:/Windows/Fonts/msyhbd.ttc",
        "C:/Windows/Fonts/simsun.ttc",
        "C:/Windows/Fonts/mingliu.ttc",
        "C:/Windows/Fonts/msjh.ttc",
    ]

    for path in font_paths:
        if os.path.exists(path):
            try:
                font = ImageFont.truetype(path, size)
                return font
            except Exception:
                continue

    font_dir = "C:/Windows/Fonts"
    if os.path.isdir(font_dir):
        for f in sorted(os.listdir(font_dir)):
            if not f.lower().endswith(".ttf"):
                continue
            fp = os.path.join(font_dir, f)
            try:
                font = ImageFont.truetype(fp, size)
                bbox = ImageDraw.Draw(Image.new("L", (1, 1))).textbbox((0, 0), "\u4e2d", font=font)
                if bbox[2] - bbox[0] > 1:
                    return font
            except Exception:
                continue

    return ImageFont.load_default()


def merge_couple_image(qq_a: str, qq_b: str, name_a: str, name_b: str, output_path: str):
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    avatar_a = _download_avatar(_avatar_url(qq_a)).resize((_AVATAR_SIZE, _AVATAR_SIZE), Image.LANCZOS)
    avatar_b = _download_avatar(_avatar_url(qq_b)).resize((_AVATAR_SIZE, _AVATAR_SIZE), Image.LANCZOS)
    avatar_a = _round_corners(avatar_a, 32)
    avatar_b = _round_corners(avatar_b, 32)

    total_w = _CANVAS_PADDING * 2 + _AVATAR_SIZE * 2 + _HEART_GAP
    total_h = _CANVAS_PADDING * 2 + _AVATAR_SIZE + 60
    canvas = Image.new("RGBA", (total_w, total_h), _BG_COLOR)
    draw = ImageDraw.Draw(canvas)

    left_x = _CANVAS_PADDING
    right_x = _CANVAS_PADDING + _AVATAR_SIZE + _HEART_GAP
    avatar_y = _CANVAS_PADDING
    canvas.paste(avatar_a, (left_x, avatar_y), avatar_a)
    canvas.paste(avatar_b, (right_x, avatar_y), avatar_b)

    heart_center_x = total_w // 2
    heart_center_y = avatar_y + _AVATAR_SIZE // 2
    font_large = _try_get_font(56)
    heart_text = "❤"
    bbox = draw.textbbox((0, 0), heart_text, font=font_large)
    hw, hh = bbox[2] - bbox[0], bbox[3] - bbox[1]
    draw.text((heart_center_x - hw // 2, heart_center_y - hh // 2), heart_text, fill=_HEART_COLOR, font=font_large)

    font_small = _try_get_font(32)
    for name, cx in [(name_a, left_x + _AVATAR_SIZE // 2), (name_b, right_x + _AVATAR_SIZE // 2)]:
        bbox = draw.textbbox((0, 0), name, font=font_small)
        tw = bbox[2] - bbox[0]
        text_y = avatar_y + _AVATAR_SIZE + 12
        draw.text((cx - tw // 2, text_y), name, fill=(80, 80, 80), font=font_small)

    canvas = canvas.convert("RGB")
    canvas.save(output_path, "PNG")


def merge_grid_image(qq_list: list[str], output_path: str):
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    n = len(qq_list)
    if n == 0:
        return
    cols = min(n, 5)
    rows = math.ceil(n / cols)

    cell = _AVATAR_SIZE
    gap = 20
    total_w = gap * 2 + cols * cell + (cols - 1) * gap
    total_h = gap * 2 + rows * cell + (rows - 1) * gap + (60 if rows == 1 else 0)
    canvas = Image.new("RGBA", (total_w, total_h), _BG_COLOR)

    for idx, qq in enumerate(qq_list):
        try:
            avatar = _download_avatar(_avatar_url(qq)).resize((cell, cell), Image.LANCZOS)
            avatar = _round_corners(avatar, 28)
            row = idx // cols
            col = idx % cols
            x = gap + col * (cell + gap)
            y = gap + row * (cell + gap)
            canvas.paste(avatar, (x, y), avatar)
        except Exception:
            pass

    canvas = canvas.convert("RGB")
    canvas.save(output_path, "PNG")
