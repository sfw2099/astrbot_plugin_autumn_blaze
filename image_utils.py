import re

COUPLE_HTML = """<!DOCTYPE html>
<html><head><meta charset="utf-8"><style>
* { margin:0; padding:0; box-sizing:border-box; }
body { background:#fff; font-family:"Microsoft YaHei","SimHei","PingFang SC",sans-serif;
       display:flex; align-items:center; justify-content:center;
       width:{{ width }}px; height:{{ height }}px; }
.wrap { display:flex; align-items:center; gap:50px; padding:30px 50px; }
.p { text-align:center; }
.p img { width:260px; height:260px; border-radius:24px; display:block; }
.p .n { margin-top:8px; font-size:24px; color:#444; }
.h { font-size:56px; color:#ff4d4f; line-height:1; flex-shrink:0; }
</style></head><body>
<div class="wrap">
  <div class="p"><img src="{{ avatar_a }}"><div class="n">{{ name_a }}</div></div>
  <div class="h">❤</div>
  <div class="p"><img src="{{ avatar_b }}"><div class="n">{{ name_b }}</div></div>
</div>
</body></html>"""

GRID_HTML = """<!DOCTYPE html>
<html><head><meta charset="utf-8"><style>
* { margin:0; padding:0; box-sizing:border-box; }
body { background:#fff; font-family:"Microsoft YaHei","SimHei","PingFang SC",sans-serif;
       width:{{ width }}px; height:{{ height }}px; }
.grid { display:flex; flex-wrap:wrap; gap:16px; padding:20px; justify-content:center; align-content:flex-start; }
.grid img { width:{{ cell }}px; height:{{ cell }}px; border-radius:20px; }
</style></head><body>
<div class="grid">
{% for qq in qq_list %}<img src="https://q4.qlogo.cn/headimg_dl?dst_uin={{ qq }}&spec=640">{% endfor %}
</div>
</body></html>"""


def _extract_http_url(file_url: str) -> str:
    m = re.search(r'(https?://[^\s"\'<>]+)', file_url)
    return m.group(1) if m else file_url


async def render_couple(plugin, qq_a: str, qq_b: str, name_a: str, name_b: str) -> str:
    avatar_a = f"https://q4.qlogo.cn/headimg_dl?dst_uin={qq_a}&spec=640"
    avatar_b = f"https://q4.qlogo.cn/headimg_dl?dst_uin={qq_b}&spec=640"
    width = 700
    height = 360
    url = await plugin.html_render(COUPLE_HTML, {
        "avatar_a": avatar_a, "avatar_b": avatar_b,
        "name_a": name_a, "name_b": name_b,
        "width": width, "height": height,
    }, options={
        "type": "png", "scale": "device",
        "clip": {"x": 0, "y": 0, "width": width, "height": height},
        "full_page": False, "device_scale_factor_level": "ultra",
    })
    return _extract_http_url(url)


async def render_grid(plugin, qq_list: list[str]) -> str:
    n = len(qq_list)
    cols = min(n, 5)
    rows = (n + cols - 1) // cols
    cell = 200
    gap = 16
    width = gap * 2 + cols * cell + (cols - 1) * gap
    height = gap * 2 + rows * cell + (rows - 1) * gap
    url = await plugin.html_render(GRID_HTML, {
        "qq_list": qq_list,
        "cell": cell,
        "width": width, "height": height,
    }, options={
        "type": "png", "scale": "device",
        "clip": {"x": 0, "y": 0, "width": width, "height": height},
        "full_page": False, "device_scale_factor_level": "ultra",
    })
    return _extract_http_url(url)
