import json
from pathlib import Path

from frontend.config import API_BASE_URL

API: str = API_BASE_URL

_MAP_JS_PATH: Path = Path(__file__).parent / "map.js"

_HTML_HEAD = """\
<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1"/>
<link rel="preconnect" href="https://fonts.googleapis.com"/>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Montserrat:wght@400;700&display=swap"/>
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/leaflet@1.9.4/dist/leaflet.css"/>
<style>
  *{margin:0;padding:0;box-sizing:border-box;}
  html,body,#map{width:100%;height:100%;background:#1B6758;}

  #legend{
    position:absolute;bottom:28px;right:10px;z-index:9999;
    background:rgba(27,103,88,0.88);border:1px solid #3C8361;
    border-radius:10px;padding:13px 17px;min-width:170px;
    font-family:'Montserrat',sans-serif;color:#EEF2E6;font-size:11px;
    backdrop-filter:blur(6px);
  }
  #legend .leg-title{font-weight:700;font-size:12px;color:#D6CDA4;margin-bottom:8px;}
  #legend .leg-bar{
    height:13px;width:100%;border-radius:3px;margin-bottom:5px;
    background:linear-gradient(to right,
      #00007f,#0000ff,#007fff,#00ffff,#7fff7f,#ffff00,#ff7f00,#ff0000,#7f0000);
  }
  #legend .leg-labels{display:flex;justify-content:space-between;font-size:10px;color:#EEF2E6;}
  #legend .leg-units{margin-top:6px;color:#D6CDA4;font-size:10px;}

  #tooltip{
    position:absolute;top:16px;left:50%;transform:translateX(-50%);
    z-index:9999;pointer-events:none;
    background:rgba(27,103,88,0.90);border:1px solid #3C8361;
    border-radius:8px;padding:9px 14px;
    font-family:'Montserrat',sans-serif;font-size:11px;color:#EEF2E6;
    white-space:nowrap;backdrop-filter:blur(6px);display:none;
  }
  #tooltip span.hi{color:#D6CDA4;font-weight:700;}
  #tooltip span.lo{color:#D6CDA4;}

  #progress-bar-wrap{
    position:absolute;top:0;left:0;right:0;z-index:9999;
    height:3px;display:none;background:rgba(214,205,164,0.12);
  }
  #progress-bar{
    height:100%;width:0%;border-radius:0 2px 2px 0;
    background:linear-gradient(90deg,#3C8361,#D6CDA4);
    transition:width 0.4s ease;
  }
  #progress-label{
    position:absolute;top:8px;left:50%;transform:translateX(-50%);
    font-family:'Montserrat',sans-serif;font-size:10px;letter-spacing:2px;
    color:#D6CDA4;opacity:0.75;pointer-events:none;white-space:nowrap;
  }
</style>
</head>
"""

_HTML_BODY_OPEN = """\
<body>
<div id="map"></div>
<div id="legend">
  <div class="leg-title" id="leg-title">Temperature</div>
  <div class="leg-bar"></div>
  <div class="leg-labels"><span id="leg-min">—</span><span id="leg-max">—</span></div>
  <div class="leg-units" id="leg-units"></div>
</div>
<div id="tooltip">—</div>
<div id="progress-bar-wrap">
  <div id="progress-bar"></div>
  <div id="progress-label"></div>
</div>
<script src="https://cdn.jsdelivr.net/npm/leaflet@1.9.4"></script>
<script src="https://cdn.jsdelivr.net/npm/georaster@1.6.0"></script>
<script src="https://cdn.jsdelivr.net/npm/georaster-layer-for-leaflet"></script>
<script src="https://cdn.jsdelivr.net/npm/chroma-js@2.4.2"></script>
"""


def _build_html(api_url: str, extra_script: str = "") -> str:
    js = _MAP_JS_PATH.read_text(encoding="utf-8")
    return (
        _HTML_HEAD
        + _HTML_BODY_OPEN
        + f"<script>window.__API_URL__ = {json.dumps(api_url)};</script>\n"
        + f"<script>\n{js}\n</script>\n"
        + extra_script
        + "</body>\n</html>"
    )


def get_map_html(api_url: str) -> str:
    return _build_html(api_url)


def get_map_html_with_initial_raster(
    api_url: str,
    raster_url: str,
    colorscale_url: str,
    date: str,
    continent: str | None,
    temp_type: str,
) -> str:
    """Generate map HTML that auto-loads a raster immediately after the iframe mounts."""
    auto_load = f"""\
<script>
window.addEventListener('load', function() {{
    setTimeout(function() {{
        window.loadRaster(
            {json.dumps(raster_url)},
            {json.dumps(colorscale_url)},
            {json.dumps(date)},
            null,
            {json.dumps(continent) if continent else 'null'},
            {json.dumps(temp_type)}
        );
    }}, 100);
}});
</script>
"""
    return _build_html(api_url, extra_script=auto_load)
