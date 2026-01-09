# gateway_app/services/db.py
"""
DB helper with Postgres primary + SQLite fallback.

Key design choice for portability:
- Write SQL using "?" placeholders.
- This module converts "?" -> "%s" automatically when using Postgres (psycopg2).
- It also removes Postgres-only casts like "::jsonb" when using SQLite.

Public API:
    execute(sql, params, commit=True/False)
    fetchone(sql, params)
    fetchall(sql, params)
    insert_and_get_id(sql, params)
    using_pg()
"""

from __future__ import annotations

import logging
import os
import re
import sqlite3
from contextlib import contextmanager
from typing import Any, Dict, Iterable, List, Optional, Tuple

from gateway_app.config import cfg

logger = logging.getLogger(__name__)

# psycopg2 is optional; if missing we fall back to SQLite even for postgres-like URLs.
psycopg2 = None  # type: ignore[assignment]
_psycopg2_import_error: Exception | None = None

try:
    import psycopg2  # type: ignore[assignment]
    import psycopg2.extras  # type: ignore[import-not-found]
except Exception as e:  # keep broad, but do NOT hide the reason
    _psycopg2_import_error = e
    logger.exception("psycopg2 import failed (package may be installed but import crashed): %s", e)
    psycopg2 = None  # type: ignore[assignment]
# type: ignore[assignment]


# ---------- URL helpers ----------


def _is_postgres_url(url: str) -> bool:
    if not url:
        return False
    lower = url.lower()
    return lower.startswith("postgres://") or lower.startswith("postgresql://")


def _sqlite_path_from_url(url: str) -> str:
    """
    Convert DATABASE_URL into a filesystem path for SQLite.

    Accepts:
        - "sqlite:///./gateway.db" -> "./gateway.db"
        - "sqlite:////tmp/gateway.db" -> "/tmp/gateway.db"
        - "./gateway.db" -> "./gateway.db" (no scheme)
    """
    if not url:
        return "./gateway.db"

    lower = url.lower()
    if lower.startswith("sqlite:///"):
        return url[10:]
    if lower.startswith("sqlite:////"):
        return url[11:]
    return url


# ---------- SQL adaptation ----------


def _qmark_to_percent_s(sql: str) -> str:
    """
    Convert ? placeholders into %s placeholders for psycopg2,
    skipping quoted string literals.

    This is intentionally simple but safe enough for our gateway SQL patterns.
    """
    out: List[str] = []
    in_single = False
    i = 0
    while i < len(sql):
        ch = sql[i]

        if ch == "'" and not in_single:
            in_single = True
            out.append(ch)
            i += 1
            continue

        if ch == "'" and in_single:
            # handle escaped '' inside strings
            if i + 1 < len(sql) and sql[i + 1] == "'":
                out.append("''")
                i += 2
                continue
            in_single = False
            out.append(ch)
            i += 1
            continue

        if ch == "?" and not in_single:
            out.append("%s")
            i += 1
            continue

        out.append(ch)
        i += 1

    return "".join(out)


_RETURNING_RE = re.compile(r"\s+RETURNING\s+.+?$", re.IGNORECASE | re.DOTALL)


def _adapt_sql(sql: str, *, use_postgres: bool) -> str:
    """
    - If Postgres: convert ? -> %s
    - If SQLite: remove ::jsonb / ::json casts and normalize NOW() -> CURRENT_TIMESTAMP
                and strip RETURNING clause (for wider SQLite compatibility).
    """
    if use_postgres:
        return _qmark_to_percent_s(sql)

    # SQLite
    s = sql
    s = re.sub(r"::\s*jsonb", "", s, flags=re.IGNORECASE)
    s = re.sub(r"::\s*json", "", s, flags=re.IGNORECASE)
    s = re.sub(r"\bNOW\(\)\b", "CURRENT_TIMESTAMP", s, flags=re.IGNORECASE)
    s = _RETURNING_RE.sub("", s)
    return s


# ---------- Connection handling ----------


def _connect_postgres(dsn: str):
    if psycopg2 is None:
        # Show the real reason instead of the misleading "not installed"
        raise RuntimeError(
            f"psycopg2 import failed; cannot use Postgres. Root cause: {_psycopg2_import_error!r}"
        )
    return psycopg2.connect(dsn, cursor_factory=psycopg2.extras.DictCursor)


def _connect_sqlite(path: str):
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def _get_connection():
    url = (cfg.DATABASE_URL or "").strip()

    # If URL looks like Postgres but psycopg2 isn't available, fail loudly (prod safety)
    if _is_postgres_url(url) and psycopg2 is None:
        raise RuntimeError(
        f"DATABASE_URL looks like Postgres but psycopg2 is unavailable. Root cause: {_psycopg2_import_error!r}"
    )


    if _is_postgres_url(url) and psycopg2 is not None:
        logger.debug("DB: using Postgres")
        return _connect_postgres(url)

    # SQLite fallback (intended for local dev)
    sqlite_path = _sqlite_path_from_url(url or "./gateway.db")
    os.makedirs(os.path.dirname(sqlite_path) or ".", exist_ok=True)
    logger.debug("DB: using SQLite at %s", sqlite_path)
    return _connect_sqlite(sqlite_path)



@contextmanager
def _cursor(*, commit: bool = False) -> Tuple[Any, Any]:
    conn = _get_connection()
    cur = conn.cursor()
    try:
        yield conn, cur
        if commit:
            conn.commit()
    except Exception:
        try:
            conn.rollback()
        except Exception:
            pass
        raise
    finally:
        try:
            cur.close()
        except Exception:
            pass
        try:
            conn.close()
        except Exception:
            pass


# ---------- Public helpers ----------


def using_pg() -> bool:
    url = (cfg.DATABASE_URL or "").strip()
    return psycopg2 is not None and _is_postgres_url(url)


def execute(sql: str, params: Optional[Iterable[Any]] = None, *, commit: bool = False) -> None:
    use_postgres = using_pg()
    effective_sql = _adapt_sql(sql, use_postgres=use_postgres)
    with _cursor(commit=commit) as (_conn, cur):
        cur.execute(effective_sql, tuple(params or []))


def fetchone(sql: str, params: Optional[Iterable[Any]] = None) -> Optional[Dict[str, Any]]:
    use_postgres = using_pg()
    effective_sql = _adapt_sql(sql, use_postgres=use_postgres)
    with _cursor(commit=False) as (_conn, cur):
        cur.execute(effective_sql, tuple(params or []))
        row = cur.fetchone()
        if row is None:
            return None
        return dict(row)


def fetchall(sql: str, params: Optional[Iterable[Any]] = None) -> List[Dict[str, Any]]:
    use_postgres = using_pg()
    effective_sql = _adapt_sql(sql, use_postgres=use_postgres)
    with _cursor(commit=False) as (_conn, cur):
        cur.execute(effective_sql, tuple(params or []))
        rows = cur.fetchall()
        return [dict(r) for r in rows]


def insert_and_get_id(sql: str, params: Optional[Iterable[Any]] = None) -> Any:
    """
    Insert a row and return its primary key.

    - Postgres: appends "RETURNING id" if missing.
    - SQLite: uses lastrowid.
    """
    use_postgres = using_pg()
    effective_sql = sql

    if use_postgres and "returning" not in sql.lower():
        effective_sql = sql.rstrip().rstrip(";") + " RETURNING id"

    effective_sql = _adapt_sql(effective_sql, use_postgres=use_postgres)

    with _cursor(commit=True) as (_conn, cur):
        cur.execute(effective_sql, tuple(params or []))

        if use_postgres:
            row = cur.fetchone()
            if not row:
                return None
            row_dict = dict(row)
            return row_dict.get("id")
        else:
            return getattr(cur, "lastrowid", None)
