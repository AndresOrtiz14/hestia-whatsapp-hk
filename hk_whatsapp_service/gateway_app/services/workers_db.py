# gateway_app/services/workers_db.py
"""
Queries de workers via NestJS HTTP API.

Mantiene las mismas firmas de función que la versión psycopg para no
tener que modificar los flows existentes.

El estado efímero (pausada, ocupada) sigue leyéndose desde runtime_sessions
via workers_db_direct.py — NestJS no necesita conocer ese estado.
"""
from __future__ import annotations

import logging
import re
import unicodedata
from typing import Dict, Any, List, Optional

from gateway_app.services.api_client import api_get, api_patch
from gateway_app.services.mappers import worker_from_nestjs, supervisor_from_nestjs

logger = logging.getLogger(__name__)


# ============================================================
# HELPERS
# ============================================================

def _norm(s: str) -> str:
    """Normaliza texto para comparación: lowercase, sin tildes, espacios colapsados."""
    if not s:
        return ""
    s = s.strip().lower()
    s = unicodedata.normalize("NFD", s)
    s = "".join(ch for ch in s if unicodedata.category(ch) != "Mn")
    s = re.sub(r"\s+", " ", s)
    return s


def normalizar_area(area: str) -> str:
    """Normaliza variantes de nombres de área al canónico Flask."""
    a = (area or "").strip().upper()
    if a in ("MANTENCION", "MANTENCIÓN", "MAINTENANCE"):
        return "MANTENIMIENTO"
    if a in ("AREAS COMUNES", "ÁREAS COMUNES", "AREAS_COMUNES", "AC", "COMMON_AREAS"):
        return "AREAS_COMUNES"
    if a in ("HK",):
        return "HOUSEKEEPING"
    return a or "HOUSEKEEPING"


def _normalize_phone(phone: str) -> str:
    return re.sub(r"\D", "", (phone or "").strip())


def _enriquecer_con_runtime(workers: List[Dict]) -> List[Dict]:
    """
    Superpone estado efímero (pausada, ocupada) desde runtime_sessions.
    turno_activo viene de NestJS — no se sobreescribe aquí.
    """
    if not workers:
        return workers
    phones = [w.get("telefono") for w in workers if w.get("telefono")]
    if not phones:
        return workers
    try:
        from gateway_app.services.workers_db_direct import (
            obtener_runtime_sessions_por_telefonos,
        )
        sessions = obtener_runtime_sessions_por_telefonos(phones) or {}
        for w in workers:
            sess = sessions.get(w.get("telefono"), {}) or {}
            w["pausada"] = bool(sess.get("pausada", False))
            w["ocupada"] = bool(sess.get("ocupada", False))
    except Exception:
        logger.exception("_enriquecer_con_runtime: error leyendo runtime_sessions")
    return workers


# ============================================================
# WORKERS — LECTURA
# ============================================================

def obtener_todos_workers(*, property_id: str) -> List[Dict[str, Any]]:
    """Retorna todos los workers activos de la property."""
    data = api_get("/api/v1/users/workers", params={"propertyId": property_id})
    if not data:
        return []
    workers = [worker_from_nestjs(u) for u in (data if isinstance(data, list) else [])]
    logger.info(
        "obtener_todos_workers: %s workers property=%s", len(workers), property_id
    )
    return _enriquecer_con_runtime(workers)


def obtener_supervisores_por_area(
    area: str,
    *,
    property_id: str,
) -> List[Dict[str, Any]]:
    """
    Retorna supervisores del área indicada.
    Reemplaza os.getenv('SUPERVISOR_PHONES_*').
    Si area está vacío retorna todos los supervisores de la property.
    """
    params: Dict[str, str] = {"propertyId": property_id}
    if area:
        from gateway_app.services.mappers import AREA_TO_NESTJS
        params["areaCode"] = AREA_TO_NESTJS.get(area.upper(), area.upper())

    data = api_get("/api/v1/users/supervisors", params=params)
    if not data:
        return []
    supervisores = [
        supervisor_from_nestjs(u)
        for u in (data if isinstance(data, list) else [])
    ]
    logger.info(
        "obtener_supervisores_por_area: %s supervisores area=%s property=%s",
        len(supervisores), area, property_id,
    )
    return supervisores


def buscar_worker_por_nombre(
    nombre: str,
    *,
    property_id: str,
) -> Optional[Dict[str, Any]]:
    """
    Busca un worker por nombre (case-insensitive, sin tildes).
    Retorna el mejor match o None.
    """
    workers = obtener_todos_workers(property_id=property_id) or []
    nombre_norm = _norm(nombre)
    if not nombre_norm:
        return None

    candidatos = [
        w for w in workers
        if nombre_norm in _norm(w.get("nombre_completo", ""))
    ]
    if not candidatos:
        logger.info(
            "buscar_worker_por_nombre: no match para '%s' property=%s",
            nombre, property_id,
        )
        return None

    def score(w: Dict) -> int:
        wn = _norm(w.get("nombre_completo", ""))
        if wn == nombre_norm:           return 3
        if wn.startswith(nombre_norm):  return 2
        return 1

    candidatos.sort(key=score, reverse=True)
    elegido = candidatos[0]
    logger.info(
        "buscar_worker_por_nombre: encontrado '%s' property=%s",
        elegido.get("nombre_completo"), property_id,
    )
    return elegido


def buscar_workers_por_nombre(
    nombre: str,
    *,
    property_id: str,
) -> List[Dict[str, Any]]:
    """Retorna todos los workers que coinciden con el nombre."""
    workers = obtener_todos_workers(property_id=property_id) or []
    nombre_norm = _norm(nombre)
    if not nombre_norm:
        return []
    return [
        w for w in workers
        if nombre_norm in _norm(w.get("nombre_completo", ""))
    ]


def buscar_worker_por_telefono(
    telefono: str,
    *,
    property_id: str,
) -> Optional[Dict[str, Any]]:
    """Busca un worker por número de teléfono."""
    phone_clean = _normalize_phone(telefono)
    if not phone_clean:
        return None

    # Intentar primero sin prefijo, luego con '+' (el backend puede almacenar +56 9 XXXX XXXX)
    data = None
    for phone_variant in (phone_clean, "+" + phone_clean):
        data = api_get("/api/v1/users/by-phone", params={
            "phoneNumber": phone_variant,
            "propertyId":  property_id,
        })
        if data:
            break

    if not data:
        logger.info(
            "buscar_worker_por_telefono: no encontrado phone=%s property=%s",
            phone_clean, property_id,
        )
        return None

    worker = worker_from_nestjs(data)
    logger.info(
        "buscar_worker_por_telefono: encontrado '%s' phone=%s",
        worker.get("nombre_completo"), phone_clean,
    )
    return worker


# ============================================================
# TURNO
# ============================================================

def activar_turno_por_telefono(phone: str, *, property_id: str) -> bool:
    """Activa el turno del worker identificado por su teléfono."""
    worker = buscar_worker_por_telefono(phone, property_id=property_id)
    if not worker:
        logger.warning(
            "activar_turno_por_telefono: no worker para phone=%s property=%s",
            phone, property_id,
        )
        return False
    result = api_patch(f"/api/v1/users/{worker['id']}/turno", {"turnoActivo": True})
    ok = result is not None
    if ok:
        logger.info("activar_turno_por_telefono: activado user=%s", worker["id"])
    return ok


def desactivar_turno_por_telefono(phone: str, *, property_id: str) -> bool:
    """Desactiva el turno del worker identificado por su teléfono."""
    worker = buscar_worker_por_telefono(phone, property_id=property_id)
    if not worker:
        logger.warning(
            "desactivar_turno_por_telefono: no worker para phone=%s property=%s",
            phone, property_id,
        )
        return False
    result = api_patch(f"/api/v1/users/{worker['id']}/turno", {"turnoActivo": False})
    ok = result is not None
    if ok:
        logger.info("desactivar_turno_por_telefono: desactivado user=%s", worker["id"])
    return ok


