import logging
import warnings
from datetime import date

import numpy as np

from backend.models.domain import AggregationResult

logger = logging.getLogger(__name__)

VALID_AGGREGATIONS: frozenset[str] = frozenset({"min", "max", "mean"})


class AggregationService:
    @staticmethod
    def aggregate(
        slices: list[tuple[date, np.ndarray]],
        aggregation: str,
        variable: str,
    ) -> AggregationResult:
        if not slices:
            raise ValueError("No data slices to aggregate")
        if aggregation not in VALID_AGGREGATIONS:
            raise ValueError(f"Unknown aggregation '{aggregation}'. Valid: {sorted(VALID_AGGREGATIONS)}")

        grids = [data for _, data in slices]

        # Iterative reduction avoids allocating an N×H×W stack.
        # np.fmin/fmax treat NaN as missing (same semantics as nanmin/nanmax).
        with np.errstate(all="ignore"), warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)
            if aggregation == "min":
                result = grids[0].astype(np.float32, copy=True)
                for arr in grids[1:]:
                    np.fmin(result, arr, out=result)
            elif aggregation == "max":
                result = grids[0].astype(np.float32, copy=True)
                for arr in grids[1:]:
                    np.fmax(result, arr, out=result)
            else:  # mean: track sum + valid-count per cell
                valid = ~np.isnan(grids[0])
                total = np.where(valid, grids[0], 0.0).astype(np.float64)
                count = valid.astype(np.int32)
                for arr in grids[1:]:
                    v = ~np.isnan(arr)
                    total += np.where(v, arr, 0.0)
                    count += v
                result = np.where(count > 0, total / count, np.nan).astype(np.float32)

        logger.debug(
            f"Aggregated {len(slices)} slices of '{variable}' using '{aggregation}'"
        )

        return AggregationResult(
            data=result,
            aggregation=aggregation,
            start_date=slices[0][0],
            end_date=slices[-1][0],
            units="K",
        )
