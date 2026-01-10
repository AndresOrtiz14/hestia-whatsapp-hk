# gateway_app/services/db.py
"""
Database connection and query helpers.
Supports both PostgreSQL (production) and SQLite (local dev).
"""

import os
import logging
from typing import Any, Optional
from contextlib import contextmanager

logger = logging.getLogger(__name__)

# Determine DB type from DATABASE_URL
DATABASE_URL = os.getenv("DATABASE_URL", "")
_IS_POSTGRES = DATABASE_URL.startswith("postgresql://") or DATABASE_URL.startswith("postgres://")

# Connection singletons
_pg_conn = None
_sqlite_conn = None


def using_pg() -> bool:
    """Returns True if using PostgreSQL, False if SQLite."""
    return _IS_POSTGRES


def get_connection():
    """Get or create database connection."""
    global _pg_conn, _sqlite_conn
    
    if _IS_POSTGRES:
        if _pg_conn is None:
            import psycopg
            _pg_conn = psycopg.connect(DATABASE_URL)
        return _pg_conn
    else:
        if _sqlite_conn is None:
            import sqlite3
            db_path = DATABASE_URL.replace("sqlite:///", "") if DATABASE_URL else "./gateway.db"
            _sqlite_conn = sqlite3.connect(db_path, check_same_thread=False)
            _sqlite_conn.row_factory = sqlite3.Row
        return _sqlite_conn


@contextmanager
def get_cursor(commit: bool = False):
    """Context manager for database cursor."""
    conn = get_connection()
    cursor = conn.cursor()
    try:
        yield cursor
        if commit:
            conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        cursor.close()


def _convert_placeholders(sql: str) -> str:
    """
    Convert ? placeholders to %s for PostgreSQL.
    For SQLite, keep ? as is.
    """
    if _IS_POSTGRES:
        return sql.replace("?", "%s")
    return sql


def execute(sql: str, params: list = None, commit: bool = False) -> None:
    """
    Execute SQL statement (INSERT, UPDATE, DELETE).
    
    Args:
        sql: SQL statement with ? placeholders
        params: List of parameters
        commit: Whether to commit after execution
    """
    params = params or []
    sql = _convert_placeholders(sql)
    
    with get_cursor(commit=commit) as cursor:
        cursor.execute(sql, params)


def fetchone(sql: str, params: list = None) -> Optional[dict]:
    """
    Fetch one row as dict.
    
    Args:
        sql: SQL query with ? placeholders
        params: List of parameters
    
    Returns:
        Dict with column names as keys, or None if no results
    """
    params = params or []
    sql = _convert_placeholders(sql)
    
    with get_cursor() as cursor:
        cursor.execute(sql, params)
        row = cursor.fetchone()
        
        if row is None:
            return None
        
        if _IS_POSTGRES:
            # psycopg returns Row-like objects - convert to dict
            columns = [desc[0] for desc in cursor.description]
            return dict(zip(columns, row))
        else:
            # sqlite3 with row_factory returns Row - convert to dict
            return dict(row)


def fetchall(sql: str, params: list = None) -> list[dict]:
    """
    Fetch all rows as list of dicts.
    
    Args:
        sql: SQL query with ? placeholders
        params: List of parameters
    
    Returns:
        List of dicts
    """
    params = params or []
    sql = _convert_placeholders(sql)
    
    with get_cursor() as cursor:
        cursor.execute(sql, params)
        rows = cursor.fetchall()
        
        if _IS_POSTGRES:
            columns = [desc[0] for desc in cursor.description]
            return [dict(zip(columns, row)) for row in rows]
        else:
            return [dict(row) for row in rows]