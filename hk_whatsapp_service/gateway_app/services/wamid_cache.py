# gateway_app/services/wamid_cache.py
"""
In-memory deduplication cache for WhatsApp message IDs (wamids).

Entries expire after TTL_SECONDS to bound memory usage.
"""

from __future__ import annotations

import logging
import time
from typing import Dict

logger = logging.getLogger(__name__)

TTL_SECONDS = 300

_seen: Dict[str, float] = {}


def _evict() -> None:
    cutoff = time.time() - TTL_SECONDS
    to_delete = [k for k, v in _seen.items() if v < cutoff]
    for k in to_delete:
        del _seen[k]


def is_duplicate_wamid(wamid: str) -> bool:
    """Return True if wamid was already seen; register it if not."""
    _evict()
    if wamid in _seen:
        return True
    _seen[wamid] = time.time()
    return False
