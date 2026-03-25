# gateway_app/services/runtime_state.py
"""
Runtime state persistence — in-memory store.

Sufficient for a single Gunicorn sync worker. State is lost on process restart.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

_sessions: Dict[str, Dict[str, Any]] = {}


def load_runtime_session(phone: str) -> Optional[Dict[str, Any]]:
    return _sessions.get(phone)


def save_runtime_session(phone: str, data: Dict[str, Any]) -> None:
    _sessions[phone] = data


def delete_runtime_session(phone: str) -> None:
    _sessions.pop(phone, None)
