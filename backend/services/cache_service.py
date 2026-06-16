import logging
import threading
from collections import OrderedDict
from pathlib import Path

import diskcache
import numpy as np

logger = logging.getLogger(__name__)

_CACHE_TTL_SECONDS: int = 3600
_MEMORY_LIMIT: int = 60  # max arrays in memory (60 × ~26 MB ≈ 1.5 GB)
_DISK_SIZE_LIMIT: int = (
    20 * 1024 * 1024 * 1024
)  # 20 GB — fits 180 days × 2 types × ~25 MB


class TemperatureCache:
    """Two-level cache: in-memory LRU (fast) backed by diskcache (persistent)."""

    def __init__(
        self,
        ttl_seconds: int = _CACHE_TTL_SECONDS,
        cache_dir: Path | None = None,
        memory_limit: int = _MEMORY_LIMIT,
        disk_size_limit: int = _DISK_SIZE_LIMIT,
    ) -> None:
        if cache_dir is None:
            from backend.core.config import CACHE_DIR as _DEFAULT_CACHE_DIR

            cache_dir = _DEFAULT_CACHE_DIR
        self._disk = diskcache.Cache(str(cache_dir), size_limit=disk_size_limit)
        self._ttl = ttl_seconds
        self._mem: OrderedDict[str, np.ndarray] = OrderedDict()
        self._mem_limit = memory_limit
        self._mem_lock = threading.Lock()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _mem_get(self, key: str) -> np.ndarray | None:
        with self._mem_lock:
            if key in self._mem:
                self._mem.move_to_end(key)
                return self._mem[key]
        return None

    def _mem_set(self, key: str, data: np.ndarray) -> None:
        with self._mem_lock:
            self._mem[key] = data
            self._mem.move_to_end(key)
            if len(self._mem) > self._mem_limit:
                self._mem.popitem(last=False)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get(self, key: str) -> np.ndarray | None:
        # ttl=0 is only used in tests; skip memory to let disk expiry take effect.
        if self._ttl > 0:
            hit = self._mem_get(key)
            if hit is not None:
                logger.debug(f"Memory cache hit: {key}")
                return hit

        value: np.ndarray | None = self._disk.get(key, default=None)
        if value is None:
            return None

        logger.debug(f"Disk cache hit: {key}")
        if self._ttl > 0:
            self._mem_set(key, value)
        return value

    def set(self, key: str, data: np.ndarray) -> None:
        if self._ttl > 0:
            self._mem_set(key, data)
        self._disk.set(key, data, expire=self._ttl if self._ttl > 0 else 0)


temperature_cache = TemperatureCache()
