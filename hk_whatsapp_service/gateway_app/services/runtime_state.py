# gateway_app/services/runtime_state.py
"""
Runtime state persistence using public.runtime_sessions.

Schema (already exists):
    runtime_sessions(phone text primary key, data jsonb not null, updated_at timestamptz)

We store state as JSON text (json.dumps). On Postgres we cast to jsonb in SQL.
"""

from __future__ import annotations

import json
from datetime import datetime
import logging
from typing import Any, Dict, Optional

from gateway_app.services.db import execute, fetchone, using_pg

logger = logging.getLogger(__name__)


def _decode_json_maybe(value: Any) -> Any:
    """
    Handle jsonb coming back as dict OR as string, depending on driver/typecaster.
    """
    if value is None:
        return None
    if isinstance(value, (dict, list)):
        return value
    if isinstance(value, str):
        try:
            return json.loads(value)
        except Exception:
            return None
    return None


def load_runtime_session(phone: str) -> Optional[Dict[str, Any]]:
    table = "public.runtime_sessions" if using_pg() else "runtime_sessions"
    row = fetchone(f"SELECT data FROM {table} WHERE phone = ?", [phone])
    if not row:
        return None
    
    data_raw = row.get("data")
    decoded = _decode_json_maybe(data_raw)
    return decoded if isinstance(decoded, dict) else None



def save_runtime_session(phone: str, data: Dict[str, Any]) -> None:
    payload = json.dumps(data, ensure_ascii=False)

    if using_pg():
        execute(
            """
            INSERT INTO public.runtime_sessions (phone, data, updated_at)
            VALUES (?, ?::jsonb, NOW())
            ON CONFLICT (phone) DO UPDATE
            SET data = EXCLUDED.data,
                updated_at = NOW()
            """,
            [phone, payload],
            commit=True,
        )
    else:
        # SQLite fallback (expects a compatible table if used locally)
        execute(
            """
            INSERT INTO runtime_sessions (phone, data, updated_at)
            VALUES (?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(phone) DO UPDATE
            SET data = excluded.data,
                updated_at = CURRENT_TIMESTAMP
            """,
            [phone, payload],
            commit=True,
        )
        
def persist_state(phone: str, state: dict) -> None:
    """Persiste el estado del usuario."""
    # Si usas runtime_sessions en PostgreSQL:
    from gateway_app.services.db import execute
    import json
    
    sql = """
        INSERT INTO runtime_sessions (phone, data, updated_at)
        VALUES (?, ?::jsonb, NOW())
        ON CONFLICT (phone) DO UPDATE SET
            data = EXCLUDED.data,
            updated_at = NOW()
    """
    execute(sql, [phone, json.dumps(state)], commit=True)