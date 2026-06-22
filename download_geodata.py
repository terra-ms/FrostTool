"""Download Natural Earth boundary files into backend/static/.

Run once from the project root:
    python download_geodata.py

Requires geopandas (pip install geopandas).

Files saved:
    backend/static/ne_admin0.geojson  — country borders  (10m,  ~20 MB)
    backend/static/ne_admin1.geojson  — province borders (50m,  ~8 MB)
"""

import sys
from pathlib import Path

STATIC = Path(__file__).parent / "backend" / "static"
STATIC.mkdir(parents=True, exist_ok=True)

SOURCES = {
    "ne_admin0.geojson": (
        "https://naciscdn.org/naturalearth/10m/cultural/ne_10m_admin_0_countries.zip"
    ),
    "ne_admin1.geojson": (
        "https://naciscdn.org/naturalearth/50m/cultural/ne_50m_admin_1_states_provinces.zip"
    ),
}

try:
    import geopandas as gpd
except ImportError:
    print("geopandas is required:  pip install geopandas")
    sys.exit(1)

for filename, url in SOURCES.items():
    dest = STATIC / filename
    if dest.exists():
        print(f"  skip   {filename}  (already exists)")
        continue
    print(f"  fetch  {filename}  from {url} ...", end="", flush=True)
    gdf = gpd.read_file(url)
    gdf.to_file(dest, driver="GeoJSON")
    size_kb = dest.stat().st_size // 1024
    print(f"  {size_kb} KB")

print("Done. Restart the backend to serve the new files.")
