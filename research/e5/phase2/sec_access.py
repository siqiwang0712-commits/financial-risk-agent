"""Shared conservative request spacing across the precise SEC source clients."""
from __future__ import annotations

import threading
import time

from finrisk.xbrl import SecClient

_last = 0.
_lock = threading.Lock()


class SpacedSecClient(SecClient):
    def _space(self):
        global _last
        with _lock:
            time.sleep(max(0., .3-(time.monotonic()-_last)))
            _last = time.monotonic()

    def get_json(self, url, cache_key=None):
        self._space()
        return super().get_json(url, cache_key)

    def get_bytes(self, url, cache_key=None):
        self._space()
        return super().get_bytes(url, cache_key)
