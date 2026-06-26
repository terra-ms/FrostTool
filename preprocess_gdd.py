"""
Recompute GDD results for crops whose parameters have changed.

Year stacks (crop-agnostic) are reused as-is.
GDD result files are always overwritten, so stale cached results are replaced.

Usage — local mode (reads/writes to local PRECOMPUTED_DIR):
    python preprocess_gdd.py

Usage — S3 mode (reads year stacks from S3, writes new GDD results to S3):
    S3_BUCKET=<your-bucket> python preprocess_gdd.py

Options:
    --years  1979-2026     Year range, inclusive (default: 1979-2026)
    --crops  grapevine apple  Crops to process (default: grapevine apple)
"""

import argparse
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import numpy as np

from backend.core.config import PRECOMPUTED_DIR
from backend.services import storage
from backend.services.gdd_service import (
    _NEVER_REACHED_BUDBREAK,
    GDDResult,
    _load_year_stack,
    _result_path,
    _write_gdd_result,
    load_crops,
    CropParams,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


def _compute_gdd_result(year: int, crop: CropParams) -> GDDResult | None:
    try:
        stack = _load_year_stack(year)
    except Exception as exc:
        logger.warning("year=%d — no stack available (%s), skipping", year, exc)
        return None

    nan_mask = np.any(np.isnan(stack.tmean_stack), axis=0) | np.any(
        np.isnan(stack.tmin_stack), axis=0
    )
    tavg_c = stack.tmean_stack - 273.15
    tmin_c = stack.tmin_stack - 273.15

    gdd_daily = np.maximum(tavg_c - crop.base_temperature, 0.0)
    gdd_accum = np.cumsum(gdd_daily, axis=0)

    sensitive = gdd_accum >= crop.gdd_threshold
    ever_sensitive = sensitive.any(axis=0)
    frost = sensitive & (tmin_c < crop.frost_threshold)

    frost_count = frost.sum(axis=0).astype(np.float32)
    frost_count[nan_mask] = np.nan
    frost_count[(~ever_sensitive) & (~nan_mask)] = _NEVER_REACHED_BUDBREAK

    return GDDResult(frost_count, stack.bounds)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Recompute GDD results for selected crops and year range."
    )
    parser.add_argument(
        "--years",
        default="1979-2026",
        help="Inclusive year range, e.g. 1979-2026 (default: %(default)s)",
    )
    parser.add_argument(
        "--crops",
        nargs="+",
        default=["grapevine", "apple"],
        help="Crop names matching crops.txt sections (default: %(default)s)",
    )
    args = parser.parse_args()

    start_year, end_year = (int(x) for x in args.years.split("-"))
    years = list(range(start_year, end_year + 1))

    all_crops = load_crops()
    crops_to_process: dict[str, CropParams] = {}
    for name in args.crops:
        if name not in all_crops:
            logger.error("Crop '%s' not found in crops.txt — aborting", name)
            sys.exit(1)
        crops_to_process[name] = all_crops[name]

    mode = (
        f"S3 (bucket={storage.S3_BUCKET})"
        if storage.using_s3()
        else f"local ({PRECOMPUTED_DIR})"
    )
    logger.info("Mode   : %s", mode)
    logger.info("Crops  : %s", list(crops_to_process))
    logger.info("Years  : %d–%d (%d years)", start_year, end_year, len(years))
    logger.info("")

    skipped, saved, failed = 0, 0, 0

    for year in years:
        for crop in crops_to_process.values():
            result = _compute_gdd_result(year, crop)
            if result is None:
                skipped += 1
                continue
            try:
                path = _result_path(year, crop.name)
                _write_gdd_result(path, result)
                logger.info("Saved  year=%d crop=%-10s  → %s", year, crop.name, path)
                saved += 1
            except Exception as exc:
                logger.error("Failed year=%d crop=%s: %s", year, crop.name, exc)
                failed += 1

    logger.info("")
    logger.info("Done — saved=%d  skipped=%d  failed=%d", saved, skipped, failed)


if __name__ == "__main__":
    main()
