import json
from pathlib import Path

from dash import html

from frontend.config import API_BASE_URL

_JS_CONTENT: str = (Path(__file__).parent / "gdd_map.js").read_text(encoding="utf-8")

_HTML_TEMPLATE = """\
<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1"/>
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/leaflet@1.9.4/dist/leaflet.css"/>
<style>
  *{{margin:0;padding:0;box-sizing:border-box;}}
  html,body,#map{{width:100%;height:100%;background:#1B6758;}}
  #render-info{{
    position:absolute;top:10px;left:50%;transform:translateX(-50%);
    z-index:9999;pointer-events:none;display:none;
    background:rgba(27,103,88,0.88);border:1px solid #3C8361;
    border-radius:8px;padding:6px 14px;
    font-family:'Space Mono',monospace;font-size:11px;color:#D6CDA4;
    white-space:nowrap;backdrop-filter:blur(6px);
  }}
  #loading{{
    position:absolute;top:50%;left:50%;transform:translate(-50%,-50%);
    z-index:9998;display:none;
    font-family:'Space Mono',monospace;font-size:13px;color:#D6CDA4;text-align:center;
  }}
  .spinner{{
    width:50px;height:50px;
    border:4px solid rgba(214,205,164,0.2);border-top:4px solid #D6CDA4;
    border-radius:50%;animation:spin 0.8s linear infinite;margin:0 auto 12px;
  }}
  @keyframes spin{{0%{{transform:rotate(0deg);}}100%{{transform:rotate(360deg);}}}}
  .loading-text{{color:#D6CDA4;font-size:12px;letter-spacing:1px;opacity:0.9;}}
</style>
</head>
<body>
<div id="map"></div>
<div id="render-info"></div>
<div id="loading">
  <div class="spinner"></div>
  <div class="loading-text">COMPUTING FROST RISK</div>
</div>
<script src="https://cdn.jsdelivr.net/npm/leaflet@1.9.4"></script>
<script src="https://cdn.jsdelivr.net/npm/georaster@1.6.0"></script>
<script src="https://cdn.jsdelivr.net/npm/georaster-layer-for-leaflet"></script>
<script src="https://cdn.jsdelivr.net/npm/chroma-js@2.4.2"></script>
<script>window.__API_URL__ = {api_url};</script>
<script>{js}</script>
{extra}
</body>
</html>
"""


def _build_html(extra: str = "") -> str:
    return _HTML_TEMPLATE.format(
        api_url=json.dumps(API_BASE_URL),
        js=_JS_CONTENT,
        extra=extra,
    )


def get_gdd_map_html() -> str:
    return _build_html()


def get_gdd_map_html_with_raster(raster_url: str, year: int, crop: str) -> str:
    auto_load = f"""\
<script>
window.addEventListener('load', function() {{
  setTimeout(function() {{
    window.loadGDDRaster({json.dumps(raster_url)}, {json.dumps(year)}, {json.dumps(crop)});
  }}, 100);
}});
</script>"""
    return _build_html(extra=auto_load)


def create_gdd_map_frame() -> html.Iframe:
    return html.Iframe(
        id="gdd-map-frame",
        srcDoc=get_gdd_map_html(),
        style={"width": "100%", "height": "100%", "border": "none"},
    )
