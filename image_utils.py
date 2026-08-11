import os
import io
import math
import re
import requests
from PIL import Image, ImageDraw, ImageFont

COUPLE_HTML = None

_TEMP_DIR = None
_FONT_CACHE_PATH = None
_CJK_FONT_URLS = [
    "https://cdn.jsdelivr.net/gh/googlefonts/noto-cjk@main/Sans/OTF/SimplifiedChinese/NotoSansSC-Regular.otf",
]


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


def _try_system_font(size: int) -> ImageFont.FreeTypeFont | None:
    paths = [
        os.path.join(os.path.dirname(__file__), "HarmonyOS_Sans_SC.ttf"),
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
    return None


def _download_cjk_font() -> str | None:
    global _FONT_CACHE_PATH
    cache_dir = os.path.abspath(os.path.join(_TEMP_DIR or os.getcwd(), "..", "fonts"))
    os.makedirs(cache_dir, exist_ok=True)
    for f in os.listdir(cache_dir):
        if f.lower().endswith((".ttf", ".ttc", ".otf")):
            fp = os.path.join(cache_dir, f)
            try:
                font = ImageFont.truetype(fp, 16)
                bbox = ImageDraw.Draw(Image.new("L", (1, 1))).textbbox((0, 0), "中", font=font)
                if bbox[2] - bbox[0] > 1:
                    _FONT_CACHE_PATH = fp
                    return fp
            except Exception:
                continue
    for url in _CJK_FONT_URLS:
        try:
            resp = requests.get(url, timeout=60)
            if resp.status_code == 200:
                ext = url.rsplit(".", 1)[-1]
                fp = os.path.join(cache_dir, f"cjk_font.{ext}")
                with open(fp, "wb") as f:
                    f.write(resp.content)
                _FONT_CACHE_PATH = fp
                return fp
        except Exception:
            continue
    return None


def _try_font(size: int) -> ImageFont.FreeTypeFont:
    f = _try_system_font(size)
    if f:
        return f
    if _FONT_CACHE_PATH and os.path.exists(_FONT_CACHE_PATH):
        try:
            return ImageFont.truetype(_FONT_CACHE_PATH, size)
        except Exception:
            pass
    dl = _download_cjk_font()
    if dl:
        try:
            return ImageFont.truetype(dl, size)
        except Exception:
            pass
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


async def render_relationship_graph(records, user_map, title, temp_dir, is_ego=False, focus_id=None) -> str:
    return _render_graph_pil(records, user_map, title, temp_dir, is_ego, focus_id)


def _render_graph_pil(records, user_map, title, temp_dir, is_ego=False, focus_id=None) -> str:
    if _TEMP_DIR is None:
        _init_temp(os.path.join(temp_dir, "temp"))
    out = _temp_path("graph")

    nodes = {}
    for r in records:
        uid = str(r.get("user_id"))
        wid = str(r.get("wife_id"))
        nodes[uid] = user_map.get(uid, f"用户{uid}")
        nodes[wid] = user_map.get(wid, f"用户{wid}")

    n = len(nodes)
    if n == 0:
        img = Image.new("RGB", (400, 100), (255, 255, 255))
        ImageDraw.Draw(img).text((200, 50), "暂无数据", fill=(128, 128, 128), font=_try_font(18), anchor="mm")
        img.save(out, "PNG")
        return out

    pad = 60
    node_r = 36
    w = 1920
    h = max(800, pad * 2 + n * 80 + 200)

    img = Image.new("RGB", (w, h), (255, 255, 255))
    draw = ImageDraw.Draw(img)

    font_title = _try_font(28)
    font_name = _try_font(16)
    font_legend = _try_font(14)

    draw.text((w // 2, 20), title, fill=(40, 40, 40), font=font_title, anchor="mt")

    edge_colors = {
        "dian_yuanyang": (235, 47, 150),
        "proposed": (250, 84, 28),
        "forced_all": (207, 19, 34),
        "forced": (255, 77, 79),
        "auto_set": (114, 46, 209),
    }

    node_list = list(nodes.items())
    cx, cy = w // 2, h // 2 + 20
    radius = min(w // 2 - pad * 3, h // 2 - pad) - node_r

    positions = {}
    for i, (uid, name) in enumerate(node_list):
        angle = 2 * math.pi * i / n - math.pi / 2
        x = cx + radius * math.cos(angle)
        y = cy + radius * math.sin(angle)
        positions[uid] = (x, y)

    for r_item in records:
        uid = str(r_item.get("user_id"))
        wid = str(r_item.get("wife_id"))
        if uid not in positions or wid not in positions:
            continue
        x1, y1 = positions[uid]
        x2, y2 = positions[wid]

        color = (24, 144, 255)
        for ek in edge_colors:
            if r_item.get(ek):
                color = edge_colors[ek]
                break

        mx, my = (x1 + x2) / 2, (y1 + y2) / 2
        dx, dy = x2 - x1, y2 - y1
        dist = math.hypot(dx, dy)
        if dist > 0:
            nx, ny = -dy / dist, dx / dist
            mx += nx * 30
            my += ny * 30

        draw.line([(x1, y1), (mx, my), (x2, y2)], fill=color, width=2)

        angle = math.atan2(y2 - my, x2 - mx)
        al = 10
        ax1 = x2 - al * math.cos(angle - 0.5)
        ay1 = y2 - al * math.sin(angle - 0.5)
        ax2 = x2 - al * math.cos(angle + 0.5)
        ay2 = y2 - al * math.sin(angle + 0.5)
        draw.polygon([(x2, y2), (ax1, ay1), (ax2, ay2)], fill=color)

    for uid, (x, y) in positions.items():
        is_focus = is_ego and uid == focus_id
        bg_color = (250, 140, 22) if is_focus else (79, 172, 254)
        draw.ellipse([x - node_r, y - node_r, x + node_r, y + node_r], fill=bg_color, outline=(255, 255, 255), width=3)
        name = nodes[uid][:6]
        bbox = draw.textbbox((0, 0), name, font=font_name)
        tw = bbox[2] - bbox[0]
        draw.text((x - tw // 2, y + node_r + 4), name, fill=(60, 60, 60), font=font_name)

    ly = h - 60
    lx = 20
    for label, clr in [("抽中", (24,144,255)), ("强娶", (255,77,79)), ("牵线", (235,47,150)), ("求婚", (250,84,28)), ("全娶", (207,19,34)), ("互抽", (114,46,209))]:
        draw.rectangle([lx, ly, lx + 14, ly + 14], fill=clr)
        draw.text((lx + 18, ly), label, fill=(80, 80, 80), font=font_legend)
        lx += 90

    img.save(out, "PNG")
    return out
