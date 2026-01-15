"""
Consultas de workers desde Supabase.
"""
import logging
from typing import List, Dict, Any, Optional

from gateway_app.services.db import fetchall, fetchone

logger = logging.getLogger(__name__)


def obtener_todos_workers() -> List[Dict[str, Any]]:
    """
    Obtiene todos los trabajadores activos.
    
    Returns:
        Lista de workers desde BD
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
        ORDER BY username
    """
    
    try:
        workers = fetchall(sql)
        logger.info(f"👥 {len(workers)} workers activos desde BD")
        return workers
    except Exception as e:
        logger.exception(f"❌ Error obteniendo workers: {e}")
        return []


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
    
# workers_db.py (idea mínima)
# después de traer users/workers desde users table
# 1) obtener runtime_sessions para esos teléfonos
# 2) mezclar data en cada worker

# Ejemplo conceptual:
sessions = obtener_runtime_sessions_por_telefonos(phones)  # dict phone -> data
for w in workers:
    data = sessions.get(w["telefono"], {}) or {}
    w["turno_activo"] = bool(data.get("turno_activo", False))
    w["pausada"] = bool(data.get("pausada", False))
    w["ocupada"] = bool(data.get("ocupada", False))
    # área: usa users.area si existe, si no usa data.area, si no HK
    w["area"] = w.get("area") or data.get("area") or "HOUSEKEEPING"

logger.info(
    f"👥 {len(workers)} workers; turno_activo={sum(1 for w in workers if w.get('turno_activo'))}; "
    f"areas_sample={[w.get('area') for w in workers[:5]]}"
)
