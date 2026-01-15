"""
Consultas de workers desde Supabase.
"""
import logging
from typing import List, Dict, Any, Optional

from gateway_app.services.db import fetchall, fetchone, execute, using_pg

import os
from gateway_app.services.db import execute

logger = logging.getLogger(__name__)

def normalizar_area(area: str) -> str:
    a = (area or "").strip().upper()
    if a in ("MANTENCION", "MANTENCIÓN"):
        return "MANTENIMIENTO"
    if a in ("AREAS COMUNES", "ÁREAS COMUNES", "AREAS_COMUNES", "AC"):
        return "AREAS_COMUNES"
    if a == "HK":
        return "HOUSEKEEPING"
    return a or "HOUSEKEEPING"

def _normalize_phone(phone: str) -> str:
    # deja solo dígitos (ajusta si tú guardas con '+')
    return "".join(ch for ch in (phone or "").strip() if ch.isdigit())

def activar_turno_por_telefono(phone: str) -> bool:
    if not using_pg():
        logger.warning("Turno no activado: no hay DATABASE_URL (modo SQLite).")
        return False

    phone_n = _normalize_phone(phone)
    if not phone_n:
        return False

    row = fetchone(
        """
        UPDATE public.users
        SET turno_activo = ?,
            turno_updated_at = now()
        WHERE telefono = ?
        RETURNING id;
        """,
        (True, phone_n),
    )

    if row:
        logger.info("✅ Turno activado: telefono=%s user_id=%s", phone_n, row["id"])
        return True

    logger.warning("⚠️ No se activó turno: no existe user con telefono=%s", phone_n)
    return False

def desactivar_turno_por_telefono(phone: str) -> bool:
    phone_n = _normalize_phone(phone)
    if not phone_n:
        return False

    execute(
        "UPDATE public.users SET turno_activo = ?, turno_updated_at = now() WHERE telefono = ?",
        (False, phone_n),
    )
    return True



def _get_pg_conn():
    dsn = os.getenv("DATABASE_URL")
    if not dsn:
        raise RuntimeError("DATABASE_URL no está configurada")

    # Intentar psycopg2 primero, fallback a psycopg (v3).
    try:
        import psycopg2  # type: ignore
        return psycopg2.connect(dsn, sslmode="require")
    except Exception:
        try:
            import psycopg  # type: ignore
            return psycopg.connect(dsn, sslmode="require")
        except Exception as e:
            raise RuntimeError("No hay driver Postgres (psycopg2/psycopg)") from e


def obtener_runtime_sessions_por_telefonos(phones: list[str]) -> dict[str, dict]:
    """
    Devuelve phone -> {turno_activo, ocupada, pausada, area} desde runtime_sessions.
    Nunca debe botar la app: si falla, devuelve {}.
    """
    phones = [str(p).strip() for p in (phones or []) if p]
    if not phones:
        return {}

    sql = """
      SELECT
        phone,
        COALESCE((data->>'turno_activo')::boolean, NULL) AS turno_activo,
        COALESCE((data->>'ocupada')::boolean, NULL)      AS ocupada,
        COALESCE((data->>'pausada')::boolean, NULL)      AS pausada,
        NULLIF(UPPER(data->>'area'), '')                 AS area
      FROM runtime_sessions
      WHERE phone = ANY(%s)
    """

    try:
        conn = _get_pg_conn()
        try:
            cur = conn.cursor()
            cur.execute(sql, (phones,))
            rows = cur.fetchall()
            cur.close()
        finally:
            conn.close()

        out: dict[str, dict] = {}
        for phone, turno_activo, ocupada, pausada, area in rows:
            out[str(phone)] = {
                "turno_activo": turno_activo,  # puede venir None
                "ocupada": ocupada,
                "pausada": pausada,
                "area": area,
            }
        return out
    except Exception:
        logger.exception("Error leyendo runtime_sessions; devolviendo {}")
        return {}

logger = logging.getLogger(__name__)

def normalizar_area(area: str) -> str:
    a = (area or "").strip().upper()

    if a in ("MANTENCION", "MANTENCIÓN"):
        return "MANTENIMIENTO"

    if a in ("AREAS COMUNES", "ÁREAS COMUNES", "AREAS_COMUNES", "AC"):
        return "AREAS_COMUNES"

    if a in ("HK",):
        return "HOUSEKEEPING"

    return a or "HOUSEKEEPING"

def obtener_runtime_sessions_por_telefonos(phones: list[str]) -> dict[str, dict]:
    """
    Devuelve un dict: phone -> data(jsonb) desde runtime_sessions.
    No lanza excepciones (para no botar el deploy por un tema de query).
    """
    phones = [p for p in (phones or []) if p]
    if not phones:
        return {}

    try:
        # Usa el MISMO cliente que ya uses en este archivo para consultar Supabase.
        # Ajusta el import si tu cliente se llama distinto.
        from .db import USE_PG  # <-- cambia esto si en tu proyecto el cliente está en otro módulo
    except Exception:
        logger.exception("No pude importar supabase client en workers_db")
        return {}

def obtener_todos_workers() -> List[Dict[str, Any]]:
    workers = fetchall("""
        SELECT
            id,
            username as nombre_completo,
            telefono,
            area,
            activo,
            turno_activo,
            turno_updated_at
        FROM public.users
        WHERE activo = true
        AND area IN ('HOUSEKEEPING', 'MANTENCION')
        ORDER BY username
    """)

    phones = [w.get("telefono") for w in workers if w.get("telefono")]
    sessions = obtener_runtime_sessions_por_telefonos(phones)  # si falla, {}

    for w in workers:
        phone = w.get("telefono")
        data = sessions.get(phone, {}) or {}

        # ✅ Turno desde BD (no desde runtime)
        w["turno_activo"] = bool(w.get("turno_activo"))

        # ✅ flags efímeros desde runtime
        w["pausada"] = bool(data.get("pausada", False))
        w["ocupada"] = bool(data.get("ocupada", False))

        w["area"] = normalizar_area(w.get("area") or data.get("area") or "HOUSEKEEPING")

    return workers


def buscar_worker_por_nombre(nombre: str) -> Optional[Dict[str, Any]]:
    """
    Busca un worker por nombre (case-insensitive).
    
    Args:
        nombre: Nombre o parte del nombre
    
    Returns:
        Worker encontrado o None
    """
    sql = """
        SELECT 
            id,
            username as nombre_completo,
            telefono,
            area,
            activo
        FROM public.users
        WHERE activo = true
        AND area IN ('HOUSEKEEPING', 'MANTENCION')
        AND LOWER(username) LIKE LOWER(?)
        LIMIT 1
    """
    
    try:
        worker = fetchone(sql, [f"%{nombre}%"])
        if worker:
            logger.info(f"✅ Worker encontrado: {worker['nombre_completo']}")
        return worker
    except Exception as e:
        logger.exception(f"❌ Error buscando worker: {e}")
        return None


def buscar_workers_por_nombre(nombre: str) -> List[Dict[str, Any]]:
    """
    Busca múltiples workers que coincidan con el nombre.
    
    Args:
        nombre: Nombre o parte del nombre
    
    Returns:
        Lista de workers que coinciden
    """
    sql = """
        SELECT 
            id,
            username as nombre_completo,
            telefono,
            area,
            activo
        FROM public.users
        WHERE activo = true
        AND area IN ('HOUSEKEEPING', 'MANTENCION')
        AND LOWER(username) LIKE LOWER(?)
        ORDER BY username
    """
    
    try:
        workers = fetchall(sql, [f"%{nombre}%"])
        logger.info(f"👥 {len(workers)} workers encontrados con '{nombre}'")
        return workers
    except Exception as e:
        logger.exception(f"❌ Error buscando workers: {e}")
        return []


def buscar_worker_por_telefono(telefono: str) -> Optional[Dict[str, Any]]:
    """
    Busca un worker por número de teléfono.
    
    Args:
        telefono: Número de teléfono (ej: "56996107169")
    
    Returns:
        Worker encontrado o None
    """
    sql = """
        SELECT 
            id,
            username as nombre_completo,
            telefono,
            area,
            activo
        FROM public.users
        WHERE activo = true
        AND area IN ('HOUSEKEEPING', 'MANTENCION')
        AND telefono = ?
        LIMIT 1
    """
    
    try:
        worker = fetchone(sql, [telefono])
        if worker:
            logger.info(f"✅ Worker encontrado por teléfono: {worker['nombre_completo']}")
        else:
            logger.info(f"⚠️ No se encontró worker con teléfono: {telefono}")
        return worker
    except Exception as e:
        logger.exception(f"❌ Error buscando worker por teléfono: {e}")
        return None
    