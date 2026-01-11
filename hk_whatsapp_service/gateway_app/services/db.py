# gateway_app/services/db.py
"""
Database connection and query helpers.
Compatible con psycopg v3 (Python 3.13+).
Versión simple sin pooling - perfecta para bots de WhatsApp.
"""

import os
import logging
from contextlib import suppress

logger = logging.getLogger(__name__)

# ==================== CONFIGURACIÓN ====================

DATABASE_URL = os.getenv("DATABASE_URL", "")
USE_PG = DATABASE_URL.startswith("postgresql://") or DATABASE_URL.startswith("postgres://")

# Importar drivers según sea necesario
pg = None

if USE_PG:
    try:
        import psycopg
        pg = psycopg
        logger.info("✅ psycopg v3 importado correctamente")
    except Exception as e:
        logger.error(f"❌ psycopg import failed: {e}")
        raise RuntimeError("DATABASE_URL configurado pero psycopg no disponible")


# ==================== FUNCIONES PÚBLICAS ====================

def using_pg() -> bool:
    """Retorna True si está usando PostgreSQL."""
    return USE_PG


def db():
    """
    Obtiene una conexión a la base de datos:
    - PostgreSQL si DATABASE_URL está configurado
    - SQLite local en caso contrario
    
    IMPORTANTE: Cada llamada crea una nueva conexión.
    Para bots de WhatsApp esto es perfecto (pocas requests concurrentes).
    """
    if USE_PG:
        try:
            conn = pg.connect(DATABASE_URL)
            return conn
        except Exception as e:
            logger.exception(f"Error conectando a PostgreSQL: {e}")
            raise
    
    # SQLite para desarrollo local
    import sqlite3
    db_path = os.getenv("DATABASE_PATH", "./gateway.db")
    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


def _execute(conn, query, params=()):
    """
    Ejecuta query en el backend correcto.
    Convierte '?' → '%s' para PostgreSQL automáticamente.
    """
    if USE_PG:
        # PostgreSQL usa %s, no ?
        query_pg = query.replace('?', '%s')
        cur = conn.cursor()
        cur.execute(query_pg, params)
        return cur
    else:
        # SQLite usa ?
        return conn.execute(query, params)


def fetchone(query, params=()):
    """
    Ejecuta query y retorna UNA fila como dict (o None).
    Maneja automáticamente commit y cierre de conexión.
    """
    conn = db()
    try:
        cur = _execute(conn, query, params)
        row = cur.fetchone()
        
        if USE_PG:
            # IMPORTANTE: Obtener description ANTES de cerrar cursor
            if row is not None:
                columns = [desc[0] for desc in cur.description]
                result = dict(zip(columns, row))
            else:
                result = None
            
            conn.commit()
            cur.close()
            return result
        else:
            # SQLite con row_factory retorna Row
            return dict(row) if row else None
    finally:
        with suppress(Exception):
            conn.close()


def fetchall(query, params=()):
    """
    Ejecuta query y retorna TODAS las filas como lista de dicts.
    """
    conn = db()
    try:
        cur = _execute(conn, query, params)
        rows = cur.fetchall()
        
        if USE_PG:
            # IMPORTANTE: Obtener description ANTES de cerrar cursor
            if rows and len(rows) > 0:
                columns = [desc[0] for desc in cur.description]
                result = [dict(zip(columns, row)) for row in rows]
            else:
                result = []
            
            conn.commit()
            cur.close()
            return result
        else:
            # SQLite con row_factory retorna Rows
            return [dict(row) for row in rows]
    finally:
        with suppress(Exception):
            conn.close()

def execute(query, params=(), commit=True):
    """
    Ejecuta query sin retornar resultados (INSERT, UPDATE, DELETE).
    
    Args:
        query: Query SQL con placeholders ?
        params: Parámetros para la query
        commit: Si hacer commit automáticamente (default: True)
    """
    conn = db()
    try:
        cur = _execute(conn, query, params)
        
        if USE_PG:
            cur.close()
        
        if commit:
            conn.commit()
    finally:
        with suppress(Exception):
            conn.close()


def insert_and_get_id(query, params=()):
    """
    Ejecuta INSERT y retorna el ID generado.
    
    Para PostgreSQL: agrega RETURNING id automáticamente
    Para SQLite: usa cursor.lastrowid
    """
    conn = db()
    try:
        if USE_PG:
            # Agregar RETURNING id si no está
            sql_text = query
            if 'RETURNING' not in sql_text.upper():
                sql_text = sql_text.rstrip().rstrip(';') + ' RETURNING id'
            
            cur = _execute(conn, sql_text, params)
            row = cur.fetchone()
            conn.commit()
            cur.close()
            
            # Retornar el ID (primera columna)
            return row[0] if row else None
        else:
            cur = _execute(conn, query, params)
            conn.commit()
            return cur.lastrowid
    finally:
        with suppress(Exception):
            conn.close()