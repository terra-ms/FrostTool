"""
Clip GeoJSON border files to Europe and simplify for fast browser rendering.

Source files (_src) are the original Natural Earth downloads and are never
overwritten.  Run this once whenever the source data changes:

    python scripts/simplify_borders.py

Output files are written to backend/static/ and committed to the repo.
"""

import json
import sys
from pathlib import Path

from shapely.geometry import box, mapping, shape

sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.core.config import CONTINENTS  # noqa: E402

STATIC_DIR = Path(__file__).parent.parent / "backend" / "static"

# Clip to the exact raster bbox so border and heatmap outer limits align
_MIN_LAT, _MAX_LAT, _MIN_LON, _MAX_LON = CONTINENTS["Europe"]
EUROPE_CLIP = box(_MIN_LON, _MIN_LAT, _MAX_LON, _MAX_LAT)

CONFIGS = [
    {
        "src": STATIC_DIR / "ne_admin0_src.geojson",  # Natural Earth 10m, 25 MB
        "dst": STATIC_DIR / "ne_admin0.geojson",
        "tolerance": 0.002,  # ~200 m — smooth through zoom 10
    },
    {
        "src": STATIC_DIR / "ne_admin1_src.geojson",  # Natural Earth 10m, Europe-clipped
        "dst": STATIC_DIR / "ne_admin1.geojson",
        "tolerance": 0.002,  # ~200 m — smooth through zoom 10
    },
]

COORD_PRECISION = 5  # ~1 m precision at equator


def _round_coords(obj: object) -> object:
    if isinstance(obj, float):
        return round(obj, COORD_PRECISION)
    if isinstance(obj, list):
        return [_round_coords(v) for v in obj]
    return obj


def simplify_file(src: Path, dst: Path, tolerance: float) -> None:
    print(f"Reading {src.name} ({src.stat().st_size / 1_000_000:.1f} MB)…")
    with src.open(encoding="utf-8") as f:
        fc = json.load(f)

    out_features = []
    skipped = 0
    for feat in fc["features"]:
        geom = shape(feat["geometry"])

        # Clip to Europe — discards Americas, Asia, Africa, Pacific
        clipped = geom.intersection(EUROPE_CLIP)
        if clipped.is_empty:
            skipped += 1
            continue

        simplified = clipped.simplify(tolerance, preserve_topology=True)
        if simplified.is_empty:
            skipped += 1
            continue

        coords = _round_coords(mapping(simplified)["coordinates"])
        out_features.append(
            {
                "type": "Feature",
                "properties": {},
                "geometry": {
                    "type": mapping(simplified)["type"],
                    "coordinates": coords,
                },
            }
        )

    out = {"type": "FeatureCollection", "features": out_features}
    with dst.open("w", encoding="utf-8") as f:
        json.dump(out, f, separators=(",", ":"))

    size_mb = dst.stat().st_size / 1_000_000
    print(
        f"  done: {dst.name}: {len(out_features)} features kept"
        f" ({skipped} outside Europe skipped), {size_mb:.2f} MB"
    )


if __name__ == "__main__":
    for cfg in CONFIGS:
        simplify_file(cfg["src"], cfg["dst"], cfg["tolerance"])
    print("Done.")
