# gateway_app/services/db.py
"""
Database connection and query helpers.
Adaptado del bot de huéspedes del Hotel Diego de Almagro.
Soporta PostgreSQL (Supabase) con pooling y SQLite local.
"""

import os
import logging
import time
from contextlib import suppress
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

# ==================== CONFIGURACIÓN ====================

DATABASE_URL = os.getenv("DATABASE_URL", "")
USE_PG = DATABASE_URL.startswith("postgresql://") or DATABASE_URL.startswith("postgres://")

# Detectar si es Supabase Pooler (puerto 6543)
IS_SUPABASE_POOLER = False
if USE_PG:
    parsed = urlparse(DATABASE_URL)
    IS_SUPABASE_POOLER = parsed.port == 6543

# Importar drivers según sea necesario
pg = None
pg_pool = None
pg_extras = None

if USE_PG:
    try:
        import psycopg2 as pg
        import psycopg2.pool as pg_pool
        import psycopg2.extras as pg_extras
    except Exception as e:
        logger.error(f"psycopg2 import failed: {e}")
        raise RuntimeError("DATABASE_URL configurado pero psycopg2 no disponible")

PG_POOL = None  # Se crea la primera vez que se usa


# ==================== CONNECTION POOL ====================

def _init_pg_pool():
    """
    Crea el pool de conexiones de PostgreSQL (una sola vez).
    Usa pool pequeño para Supabase Pooler (6543).
    """
    global PG_POOL
    
    if not USE_PG:
        return None
    
    if PG_POOL is not None:
        return PG_POOL
    
    if pg is None or pg_pool is None:
        raise RuntimeError("DATABASE_URL configurado pero psycopg2 no disponible")
    
    try:
        # Pool pequeño si es Supabase Pooler, más grande si es directo
        max_conn = 2 if IS_SUPABASE_POOLER else 5
        max_conn = int(os.getenv("PG_POOL_MAX", str(max_conn)))
        
        logger.info(f"Creando pool PostgreSQL (max={max_conn}, pooler={IS_SUPABASE_POOLER})")
        
        PG_POOL = pg_pool.SimpleConnectionPool(
            minconn=1,
            maxconn=max_conn,
            dsn=DATABASE_URL
        )
        
        logger.info("✅ Pool PostgreSQL creado exitosamente")
        return PG_POOL
        
    except Exception as e:
        logger.exception(f"Error creando pool PostgreSQL: {e}")
        raise


def _pg_conn_with_retry(tries: int = 3, backoff: float = 0.35):
    """
    Obtiene conexión del pool con reintentos automáticos.
    Útil para manejar hiccups transitorios de Supabase Pooler.
    """
    last_error = None
    
    for attempt in range(tries):
        try:
            pool = _init_pg_pool()
            conn = pool.getconn()
            
            # Ping rápido para verificar que está viva
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
            
            return conn
            
        except Exception as e:
            last_error = e
            
            # Si obtuvimos conexión pero falló el ping, cerrarla
            with suppress(Exception):
                if 'conn' in locals():
                    pool.putconn(conn, close=True)
            
            # Esperar antes de reintentar (backoff exponencial)
            if attempt < tries - 1:
                wait_time = backoff * (2 ** attempt)
                logger.warning(f"Reintento {attempt + 1}/{tries} en {wait_time:.2f}s")
                time.sleep(wait_time)
    
    # Si todos los intentos fallaron
    logger.error(f"Todos los reintentos fallaron: {last_error}")
    raise last_error


# ==================== FUNCIONES PÚBLICAS ====================

def using_pg() -> bool:
    """Retorna True si está usando PostgreSQL."""
    return USE_PG


def db():
    """
    Obtiene una conexión a la base de datos:
    - PostgreSQL (con reintentos) si DATABASE_URL está configurado
    - SQLite local en caso contrario
    """
    if USE_PG:
        return _pg_conn_with_retry(tries=3)
    
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
        cur = conn.cursor(cursor_factory=pg_extras.RealDictCursor)
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
        if USE_PG:
            cur = _execute(conn, query, params)
            row = cur.fetchone()
            cur.close()
            conn.commit()
            return dict(row) if row else None
        else:
            with conn:
                cur = _execute(conn, query, params)
                row = cur.fetchone()
                return dict(row) if row else None
    finally:
        if USE_PG:
            with suppress(Exception):
                PG_POOL.putconn(conn)
        else:
            with suppress(Exception):
                conn.close()


def fetchall(query, params=()):
    """
    Ejecuta query y retorna TODAS las filas como lista de dicts.
    """
    conn = db()
    try:
        if USE_PG:
            cur = _execute(conn, query, params)
            rows = cur.fetchall()
            cur.close()
            conn.commit()
            return [dict(row) for row in rows]
        else:
            with conn:
                cur = _execute(conn, query, params)
                rows = cur.fetchall()
                return [dict(row) for row in rows]
    finally:
        if USE_PG:
            with suppress(Exception):
                PG_POOL.putconn(conn)
        else:
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
        if USE_PG:
            cur = _execute(conn, query, params)
            cur.close()
            if commit:
                conn.commit()
        else:
            with conn:
                _execute(conn, query, params)
                if commit:
                    conn.commit()
    finally:
        if USE_PG:
            with suppress(Exception):
                PG_POOL.putconn(conn)
        else:
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
            cur.close()
            conn.commit()
            
            # Retornar el ID
            return row['id'] if isinstance(row, dict) else row[0]
        else:
            with conn:
                cur = _execute(conn, query, params)
                conn.commit()
                return cur.lastrowid
    finally:
        if USE_PG:
            with suppress(Exception):
                PG_POOL.putconn(conn)
        else:
            with suppress(Exception):
                conn.close()