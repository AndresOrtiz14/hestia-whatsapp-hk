# gateway_app/services/workers_db.py
"""
Consultas de workers desde Supabase.

✅ FIX: Todas las queries filtran por org_id/hotel_id usando JOIN con orgusers.
   - public.users no tiene org_id/hotel_id
   - public.orgusers SÍ tiene org_id y default_hotel_id
   - JOIN: users.id = orgusers.user_id → filtra por organización y hotel
"""
import os
import logging
import re
import unicodedata
from typing import List, Dict, Any, Optional

from gateway_app.services.db import fetchall, fetchone, execute, using_pg

logger = logging.getLogger(__name__)


# ============================================================
# HELPERS
# ============================================================

def _env_int(name: str) -> int:
    v = (os.getenv(name) or "").strip()
    if not v:
        raise RuntimeError(f"Missing required env var: {name}")
    try:
        return int(v)
    except ValueError as e:
        raise RuntimeError(f"Env var {name} must be an int, got: {v!r}") from e


def _default_scope() -> tuple[int, int]:
    """Source of truth: Render env vars ORG_ID_DEFAULT y HOTEL_ID_DEFAULT."""
    org_id = _env_int("ORG_ID_DEFAULT")
    hotel_id = _env_int("HOTEL_ID_DEFAULT")
    return org_id, hotel_id


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
    return "".join(ch for ch in (phone or "").strip() if ch.isdigit())


def _norm(s: str) -> str:
    if not s:
        return ""
    s = s.strip().lower()
    s = unicodedata.normalize("NFD", s)
    s = "".join(ch for ch in s if unicodedata.category(ch) != "Mn")
    s = re.sub(r"\s+", " ", s)
    return s


# ============================================================
# SQL base: SELECT de workers filtrado por org/hotel via orgusers
# ============================================================

_WORKERS_BASE_SQL = """
    SELECT 
        u.id,
        u.username AS nombre_completo,
        u.telefono,
        u.area,
        u.activo,
        u.turno_activo
    FROM public.users u
    JOIN public.orgusers ou ON ou.user_id = u.id
    WHERE u.activo = true
      AND ou.org_id = ?
      AND ou.default_hotel_id = ?
      AND u.area IN ('HOUSEKEEPING', 'MANTENCION', 'MANTENIMIENTO', 
                      'AREAS_COMUNES', 'ROOMSERVICE')
"""


# ============================================================
# TURNO (operan por teléfono único, no necesitan filtro org/hotel)
# ============================================================

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


# ============================================================
# RUNTIME SESSIONS (no depende de org/hotel)
# ============================================================

def _get_pg_conn():
    dsn = os.getenv("DATABASE_URL")
    if not dsn:
        raise RuntimeError("DATABASE_URL no está configurada")

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
                "turno_activo": turno_activo,
                "ocupada": ocupada,
                "pausada": pausada,
                "area": area,
            }
        return out
    except Exception:
        logger.exception("Error leyendo runtime_sessions; devolviendo {}")
        return {}


# ============================================================
# QUERIES DE WORKERS (todas filtradas por org/hotel via orgusers)
# ============================================================

def obtener_todos_workers(
    *,
    org_id: Optional[int] = None,
    hotel_id: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """
    Obtiene trabajadores activos FILTRADOS por org_id y hotel_id.
    Usa JOIN con orgusers (que tiene org_id y default_hotel_id).
    """
    if org_id is None or hotel_id is None:
        d_org, d_hotel = _default_scope()
        org_id = d_org if org_id is None else org_id
        hotel_id = d_hotel if hotel_id is None else hotel_id

    sql = _WORKERS_BASE_SQL + "\n    ORDER BY u.username"

    try:
        workers = fetchall(sql, [org_id, hotel_id])

        # Enriquecer con runtime_sessions SOLO para flags efímeros (no turno)
        phones = [w.get("telefono") for w in workers if w.get("telefono")]
        sessions = obtener_runtime_sessions_por_telefonos(phones) or {}

        for w in workers:
            phone = w.get("telefono")
            data = (sessions.get(phone, {}) or {})

            # Turno desde BD (fuente de verdad)
            w["turno_activo"] = bool(w.get("turno_activo", False))

            # Estado efímero desde runtime
            w["pausada"] = bool(data.get("pausada", False))
            w["ocupada"] = bool(data.get("ocupada", False))

            # Área normalizada
            w["area"] = normalizar_area(w.get("area") or data.get("area") or "HOUSEKEEPING")

        logger.info(
            f"👥 {len(workers)} workers (org={org_id}, hotel={hotel_id}); "
            f"turno_activo={sum(1 for w in workers if w.get('turno_activo'))}; "
            f"areas_sample={[w.get('area') for w in workers[:5]]}"
        )
        return workers

    except Exception as e:
        logger.exception(f"❌ Error obteniendo workers: {e}")
        return []


def buscar_worker_por_nombre(
    nombre: str,
    *,
    org_id: Optional[int] = None,
    hotel_id: Optional[int] = None,
) -> Optional[Dict[str, Any]]:
    """
    Busca un worker por nombre (case-insensitive + sin tildes).
    Retorna el mejor match. Filtrado por org/hotel via orgusers.
    """
    if org_id is None or hotel_id is None:
        d_org, d_hotel = _default_scope()
        org_id = d_org if org_id is None else org_id
        hotel_id = d_hotel if hotel_id is None else hotel_id

    nombre_norm = _norm(nombre)
    if not nombre_norm:
        return None

    sql = _WORKERS_BASE_SQL

    try:
        workers = fetchall(sql, [org_id, hotel_id]) or []

        logger.info(f"🔍 Buscando '{nombre}' entre {len(workers)} workers activos (org={org_id}, hotel={hotel_id})")

        # Filtrar candidatos por nombre normalizado
        candidatos: List[Dict[str, Any]] = []
        for w in workers:
            w_norm = _norm(w.get("nombre_completo") or "")
            if nombre_norm in w_norm:
                candidatos.append(w)
                logger.debug(f"   ✓ Match: '{w.get('nombre_completo')}' contiene '{nombre}'")

        if not candidatos:
            logger.info(f"👥 0 workers encontrados con '{nombre}'")
            logger.info(f"📋 Workers disponibles:")
            for w in workers[:5]:
                logger.info(f"   - {w.get('nombre_completo')}")
            return None

        # Ranking: exact match > startswith > contains
        def score(w: Dict[str, Any]) -> int:
            w_norm = _norm(w.get("nombre_completo") or "")
            if w_norm == nombre_norm:
                return 3
            if w_norm.startswith(nombre_norm):
                return 2
            return 1

        candidatos.sort(key=lambda w: (score(w), (w.get("nombre_completo") or "").lower()), reverse=True)
        elegido = candidatos[0]

        logger.info(f"✅ Worker encontrado: {elegido.get('nombre_completo')} (área: {elegido.get('area')})")
        return elegido

    except Exception as e:
        logger.exception(f"❌ Error buscando worker: {e}")
        return None


def buscar_workers_por_nombre(
    nombre: str,
    *,
    org_id: Optional[int] = None,
    hotel_id: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """
    Busca múltiples workers que coincidan con el nombre (match sin tildes).
    Filtrado por org/hotel via orgusers.
    """
    if org_id is None or hotel_id is None:
        d_org, d_hotel = _default_scope()
        org_id = d_org if org_id is None else org_id
        hotel_id = d_hotel if hotel_id is None else hotel_id

    nombre_norm = _norm(nombre)
    if not nombre_norm:
        return []

    sql = _WORKERS_BASE_SQL + "\n    ORDER BY u.username"

    try:
        workers = fetchall(sql, [org_id, hotel_id])

        matches = []
        for w in (workers or []):
            nombre_worker = _norm(w.get("nombre_completo") or "")
            if nombre_norm in nombre_worker:
                w["turno_activo"] = bool(w.get("turno_activo", False))
                w["area"] = normalizar_area(w.get("area") or "HOUSEKEEPING")
                matches.append(w)

        logger.info(f"👥 {len(matches)} workers encontrados con '{nombre}' (org={org_id}, hotel={hotel_id})")
        return matches

    except Exception as e:
        logger.exception(f"❌ Error buscando workers: {e}")
        return []


def buscar_worker_por_telefono(
    telefono: str,
    *,
    org_id: Optional[int] = None,
    hotel_id: Optional[int] = None,
) -> Optional[Dict[str, Any]]:
    """
    Busca un worker por número de teléfono.
    Filtrado por org/hotel via orgusers.
    """
    if org_id is None or hotel_id is None:
        d_org, d_hotel = _default_scope()
        org_id = d_org if org_id is None else org_id
        hotel_id = d_hotel if hotel_id is None else hotel_id

    sql = _WORKERS_BASE_SQL + """
        AND u.telefono = ?
        LIMIT 1
    """

    try:
        worker = fetchone(sql, [org_id, hotel_id, telefono])

        if worker:
            worker["turno_activo"] = bool(worker.get("turno_activo", False))
            worker["area"] = normalizar_area(worker.get("area") or "HOUSEKEEPING")
            logger.info(f"✅ Worker encontrado por teléfono: {worker['nombre_completo']} (org={org_id}, hotel={hotel_id})")
        else:
            logger.info(f"⚠️ No se encontró worker con teléfono: {telefono} (org={org_id}, hotel={hotel_id})")

        return worker

    except Exception as e:
        logger.exception(f"❌ Error buscando worker por teléfono: {e}")
        return None