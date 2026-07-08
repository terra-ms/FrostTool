"""Download Natural Earth boundary source files into backend/static/.

Run once from the project root:
    python download_geodata.py

Requires geopandas (pip install geopandas).

Files saved (these are the *_src inputs for scripts/simplify_borders.py —
run that script afterwards to produce the clipped/simplified files the
frontend serves):
    backend/static/ne_admin0_src.geojson — country borders, 10m, full world
    backend/static/ne_admin1_src.geojson — province borders, 10m, clipped to
        the Europe bbox from backend/core/config.py at download time (the
        full-world 10m admin-1 GeoJSON is >100 MB — too large to commit)

Note: the 50m admin-1 dataset only contains provinces for the 9 largest
countries (in Europe: Russia only) — the 10m dataset covers all countries.
"""

import sys
from pathlib import Path

from backend.core.config import CONTINENTS

STATIC = Path(__file__).parent / "backend" / "static"
STATIC.mkdir(parents=True, exist_ok=True)

_MIN_LAT, _MAX_LAT, _MIN_LON, _MAX_LON = CONTINENTS["Europe"]

SOURCES = {
    "ne_admin0_src.geojson": {
        "url": "https://naciscdn.org/naturalearth/10m/cultural/ne_10m_admin_0_countries.zip",
        "clip_europe": False,
    },
    "ne_admin1_src.geojson": {
        "url": "https://naciscdn.org/naturalearth/10m/cultural/ne_10m_admin_1_states_provinces.zip",
        "clip_europe": True,
    },
}

try:
    import geopandas as gpd
except ImportError:
    print("geopandas is required:  pip install geopandas")
    sys.exit(1)

for filename, cfg in SOURCES.items():
    dest = STATIC / filename
    if dest.exists():
        print(f"  skip   {filename}  (already exists — delete it to re-download)")
        continue
    print(f"  fetch  {filename}  from {cfg['url']} ...", end="", flush=True)
    gdf = gpd.read_file(cfg["url"])
    if cfg["clip_europe"]:
        gdf = gdf.cx[_MIN_LON:_MAX_LON, _MIN_LAT:_MAX_LAT]
        gdf = gdf[["geometry"]]  # properties are unused and dominate file size
    gdf.to_file(dest, driver="GeoJSON")
    size_kb = dest.stat().st_size // 1024
    print(f"  {size_kb} KB")

print("Done. Now run:  python scripts/simplify_borders.py")
