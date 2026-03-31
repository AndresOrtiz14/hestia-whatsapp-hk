# gateway_app/services/tickets_db.py
"""
Persistencia de tickets via NestJS HTTP API.

Mantiene las mismas firmas de función que la versión psycopg para no
tener que modificar los flows existentes.

Excepciones que siguen usando psycopg directo:
- agregar_media_a_ticket → el endpoint POST /tickets/:id/media aún no existe en NestJS
- obtener_media_de_ticket, contar_media_de_ticket, eliminar_media,
  mover_media_a_ticket → ídem, operan sobre ticket_media via db.py
"""
import logging
import os
import re
from typing import Any, Dict, List, Optional

from gateway_app.services.api_client import api_get, api_post, api_put
from gateway_app.services.mappers import (
    AREA_TO_NESTJS,
    STATUS_TO_NESTJS,
    ticket_from_nestjs,
    ticket_to_nestjs,
)

logger = logging.getLogger(__name__)


# ============================================================
# HELPERS INTERNOS
# ============================================================

def _default_property_id() -> str:
    """
    Lee PROPERTY_ID_DEFAULT del env.
    Usado por los stubs de compatibilidad que no reciben property_id explícito.
    """
    v = os.getenv("PROPERTY_ID_DEFAULT", "").strip()
    if not v:
        raise RuntimeError("Missing required env var: PROPERTY_ID_DEFAULT")
    return v


def _is_uuid(s: str) -> bool:
    """Detecta si una cadena es un UUID (para distinguir phone vs worker_id en asignar_ticket)."""
    return bool(re.match(
        r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$',
        (s or '').lower(),
    ))


def _resolve_ticket_uuid(ticket_id, property_id: str = None) -> Optional[str]:
    """
    Convierte un idCode numérico al UUID del ticket.
    Si ticket_id ya es un UUID, lo retorna tal cual.
    """
    if _is_uuid(str(ticket_id)):
        return str(ticket_id)
    ticket = obtener_ticket_por_id(int(ticket_id), property_id=property_id)
    return ticket.get("id") if ticket else None


def _items(data) -> list:
    """Extrae la lista de items de una respuesta NestJS (lista directa o {items: [...]})."""
    if isinstance(data, list):
        return data
    return (data or {}).get("items", [])


# ============================================================
# CREAR
# ============================================================

def crear_ticket(
    habitacion: str,
    detalle: str,
    prioridad: str,
    creado_por: str,
    origen: str = "supervisor",
    *,
    area: str = "HOUSEKEEPING",
    property_id: str = None,
    # absorber parámetros de la firma vieja para no romper llamadas existentes
    org_id=None,
    hotel_id=None,
    canal_origen: str = None,
    routing_source: str = None,
    routing_reason: str = None,
    routing_confidence: float = None,
    routing_version: str = None,
    **kwargs,
) -> Optional[str]:
    """
    Crea un ticket en NestJS.
    Retorna el UUID del ticket creado, o None si falla.

    Acepta tanto la firma nueva (property_id) como la vieja (org_id/hotel_id)
    para compatibilidad con flows existentes.
    """
    if not property_id:
        property_id = _default_property_id()

    payload = ticket_to_nestjs(
        {
            "ubicacion": habitacion,
            "detalle":   detalle,
            "prioridad": prioridad,
            "area":      area,
        },
        property_id=property_id,
    )
    result = api_post("/api/v1/tickets", payload)
    if not result:
        logger.error(
            "crear_ticket: api_post falló property=%s habitacion=%s",
            property_id, habitacion,
        )
        return None

    logger.info("crear_ticket: ticket=%s property=%s", result.get("id"), property_id)
    # Retorna el ticket normalizado (dict) para que los flows puedan hacer ticket["id"]
    return ticket_from_nestjs(result)


# ============================================================
# LEER
# ============================================================

def _enriquecer_workers(tickets: list, property_id: str) -> list:
    """Rellena worker_name en tickets donde falta pero assigned_to está presente.

    El endpoint de NestJS devuelve assignedToUserId pero no el objeto assignee
    embebido, por lo que ticket_from_nestjs deja worker_name=None. Este helper
    resuelve el nombre consultando la caché de workers (TTL 5 min).
    """
    sin_nombre = [t for t in tickets if not t.get("worker_name") and t.get("assigned_to")]
    if not sin_nombre or not property_id:
        return tickets
    from gateway_app.services.workers_db import obtener_todos_workers
    workers = obtener_todos_workers(property_id=property_id)
    by_id = {w["id"]: w["nombre_completo"] for w in workers if w.get("id")}
    for t in sin_nombre:
        nombre = by_id.get(t["assigned_to"])
        if nombre:
            t["worker_name"] = nombre
    return tickets


def obtener_ticket_por_id(ticket_id, *, property_id: str = None) -> Optional[Dict[str, Any]]:
    """Retorna el ticket normalizado al formato Flask, o None."""
    if not ticket_id:
        return None
    if not property_id:
        property_id = _default_property_id()
    data = api_get(f"/api/v1/tickets/property/{property_id}/code/{int(ticket_id)}")
    if not data:
        return None
    ticket = ticket_from_nestjs(data)
    [ticket] = _enriquecer_workers([ticket], property_id)
    return ticket


def obtener_pendientes(
    *,
    property_id: str = None,
    org_id=None,
    hotel_id=None,
) -> List[Dict[str, Any]]:
    """Tickets con status open (PENDIENTE en Flask)."""
    if not property_id:
        property_id = _default_property_id()
    data = api_get("/api/v1/tickets", params={
        "propertyId": property_id,
        "status":     STATUS_TO_NESTJS["PENDIENTE"],
    })
    return [ticket_from_nestjs(t) for t in _items(data)]


def obtener_asignados(*, property_id: str = None) -> List[Dict[str, Any]]:
    """Tickets con status assigned (ASIGNADO en Flask)."""
    if not property_id:
        property_id = _default_property_id()
    data = api_get("/api/v1/tickets", params={
        "propertyId": property_id,
        "status":     STATUS_TO_NESTJS["ASIGNADO"],
    })
    tickets = [ticket_from_nestjs(t) for t in _items(data)]
    return _enriquecer_workers(tickets, property_id)


def obtener_en_curso(*, property_id: str = None) -> List[Dict[str, Any]]:
    """Tickets con status in_progress (EN_CURSO en Flask)."""
    if not property_id:
        property_id = _default_property_id()
    data = api_get("/api/v1/tickets", params={
        "propertyId": property_id,
        "status":     STATUS_TO_NESTJS["EN_CURSO"],
    })
    tickets = [ticket_from_nestjs(t) for t in _items(data)]
    return _enriquecer_workers(tickets, property_id)


def obtener_tickets_worker(
    worker_phone: str,
    *,
    property_id: str = None,
) -> List[Dict[str, Any]]:
    """
    Tickets asignados a un worker específico.
    Busca el user por teléfono para obtener su UUID,
    luego filtra tickets por assignedToUserId.
    """
    if not property_id:
        property_id = _default_property_id()

    from gateway_app.services.workers_db import buscar_worker_por_telefono
    worker = buscar_worker_por_telefono(worker_phone, property_id=property_id)
    if not worker:
        logger.info("obtener_tickets_worker: no worker para phone=%s", worker_phone)
        return []

    data = api_get("/api/v1/tickets", params={
        "propertyId":       property_id,
        "assignedToUserId": worker["id"],
    })
    return [ticket_from_nestjs(t) for t in _items(data)]


# ============================================================
# ACTUALIZAR ESTADO
# ============================================================

def asignar_ticket(
    ticket_id,
    worker_id: str,
    asignado_a_nombre: str = "",   # absorbe el 3er arg de la firma vieja
    *,
    asignado_por: str = "",
    property_id: str = None,
) -> bool:
    """
    Asigna el ticket a un worker y lo mueve a estado assigned.

    Acepta dos calling conventions:
    - Nueva (NestJS): asignar_ticket(ticket_uuid, worker_uuid)
    - Antigua (psycopg): asignar_ticket(ticket_int, worker_phone, nombre)

    Si worker_id no parece un UUID se asume que es un teléfono y se busca
    el UUID correspondiente via workers_db.
    """
    ticket_uuid = _resolve_ticket_uuid(ticket_id, property_id=property_id)
    if not ticket_uuid:
        logger.error("asignar_ticket: no se pudo resolver UUID para idCode=%s", ticket_id)
        return False

    if not _is_uuid(str(worker_id)):
        from gateway_app.services.workers_db import buscar_worker_por_telefono
        _pid = property_id or (os.getenv("PROPERTY_ID_DEFAULT", "") or None)
        worker = buscar_worker_por_telefono(worker_id, property_id=_pid) if _pid else None
        if not worker:
            logger.error("asignar_ticket: no worker para phone=%s", worker_id)
            return False
        worker_id = worker["id"]

    result = api_put(f"/api/v1/tickets/{ticket_uuid}", {
        "assignedToUserId": worker_id,
        "status":           STATUS_TO_NESTJS["ASIGNADO"],
    })
    ok = result is not None
    if ok:
        logger.info("asignar_ticket: ticket=%s worker=%s", ticket_id, worker_id)
    else:
        logger.error("asignar_ticket: falló ticket=%s worker=%s", ticket_id, worker_id)
    return ok


def iniciar_ticket(ticket_id) -> bool:
    """Mueve el ticket a EN_CURSO."""
    ticket_uuid = _resolve_ticket_uuid(ticket_id)
    if not ticket_uuid:
        logger.error("iniciar_ticket: no se pudo resolver UUID para idCode=%s", ticket_id)
        return False
    from datetime import datetime, timezone
    result = api_put(f"/api/v1/tickets/{ticket_uuid}", {
        "status":    STATUS_TO_NESTJS["EN_CURSO"],
        "startedAt": datetime.now(timezone.utc).isoformat(),
    })
    return result is not None


def pausar_ticket(ticket_id, *, motivo: str = "") -> bool:
    """Mueve el ticket a PAUSADO."""
    ticket_uuid = _resolve_ticket_uuid(ticket_id)
    if not ticket_uuid:
        logger.error("pausar_ticket: no se pudo resolver UUID para idCode=%s", ticket_id)
        return False
    body = {"status": STATUS_TO_NESTJS["PAUSADO"]}
    if motivo:
        body["notes"] = motivo
    result = api_put(f"/api/v1/tickets/{ticket_uuid}", body)
    return result is not None


def finalizar_ticket(ticket_id, *, motivo: str = "") -> bool:
    """Mueve el ticket a RESUELTO (finished en NestJS)."""
    ticket_uuid = _resolve_ticket_uuid(ticket_id)
    if not ticket_uuid:
        logger.error("finalizar_ticket: no se pudo resolver UUID para idCode=%s", ticket_id)
        return False
    body = {"status": STATUS_TO_NESTJS["RESUELTO"]}
    if motivo:
        body["notes"] = motivo
    result = api_put(f"/api/v1/tickets/{ticket_uuid}", body)
    ok = result is not None
    if ok:
        logger.info("finalizar_ticket: ticket=%s", ticket_id)
    return ok


# ============================================================
# MEDIA — photo_url guardado directamente en el ticket via API
# ============================================================

def guardar_photo_url_ticket(ticket_id, photo_url: str) -> bool:
    """
    Guarda la URL de Supabase Storage en el campo photoUrl del ticket via NestJS API.
    El backend (Prisma) debe tener el campo photoUrl en el modelo Ticket.
    """
    from gateway_app.services.api_client import api_put
    result = api_put(f"/api/v1/tickets/{ticket_id}", {"photoUrl": photo_url})
    ok = result is not None
    if ok:
        logger.info("guardar_photo_url_ticket: ticket=%s url=%s", ticket_id, photo_url)
    else:
        logger.warning("guardar_photo_url_ticket: falló ticket=%s", ticket_id)
    return ok


def obtener_media_de_ticket(ticket_id, *, property_id: str = None) -> List[Dict[str, Any]]:
    """Obtiene el media de un ticket a partir de su campo photo_url."""
    try:
        ticket = obtener_ticket_por_id(ticket_id, property_id=property_id)
        if ticket and ticket.get("photo_url"):
            return [{"storage_url": ticket["photo_url"], "media_type": "image"}]
        return []
    except Exception:
        logger.exception("obtener_media_de_ticket: error ticket=%s", ticket_id)
        return []


def contar_media_de_ticket(ticket_id) -> int:
    """Cuenta cuántos medios tiene un ticket via psycopg directo."""
    try:
        from gateway_app.services.db import fetchone
        result = fetchone(
            "SELECT COUNT(*) as count FROM public.ticket_media WHERE ticket_id = ?",
            [str(ticket_id)],
        )
        return result["count"] if result else 0
    except Exception:
        logger.exception("contar_media_de_ticket: psycopg falló ticket=%s", ticket_id)
        return 0


def eliminar_media(media_id) -> bool:
    """Elimina un registro de media via psycopg directo."""
    try:
        from gateway_app.services.db import execute
        execute(
            "DELETE FROM public.ticket_media WHERE id = ?",
            [media_id],
            commit=True,
        )
        return True
    except Exception:
        logger.exception("eliminar_media: psycopg falló id=%s", media_id)
        return False


def mover_media_a_ticket(whatsapp_media_id: str, ticket_id) -> bool:
    """
    Mueve un media pendiente (sin ticket) a un ticket específico via psycopg directo.
    Útil cuando el ticket se crea después de recibir el media.
    """
    try:
        from gateway_app.services.db import execute
        execute(
            """
            UPDATE public.ticket_media
            SET ticket_id = ?
            WHERE whatsapp_media_id = ? AND ticket_id IS NULL
            """,
            [str(ticket_id), whatsapp_media_id],
            commit=True,
        )
        return True
    except Exception:
        logger.exception("mover_media_a_ticket: psycopg falló ticket=%s", ticket_id)
        return False


# ============================================================
# STUBS DE COMPATIBILIDAD
# Mismos nombres que la versión psycopg — los flows no se tocan.
# ============================================================

def obtener_tickets_asignados_a(
    phone: str,
    *,
    property_id: str = None,
) -> List[Dict[str, Any]]:
    """
    Tickets asignados al worker identificado por teléfono.
    Stub compat → delega a obtener_tickets_worker.
    """
    if not property_id:
        property_id = _default_property_id()
    return obtener_tickets_worker(phone, property_id=property_id)


def obtener_tickets_por_worker(worker_phone: str, **kwargs) -> List[Dict[str, Any]]:
    """Alias de compatibilidad → obtener_tickets_asignados_a."""
    return obtener_tickets_asignados_a(worker_phone, **kwargs)


def obtener_tickets_asignados_y_en_curso(
    *,
    org_id=None,
    hotel_id=None,
    property_id: str = None,
) -> List[Dict[str, Any]]:
    """
    Tickets ASIGNADO + EN_CURSO.
    Stub compat → une obtener_asignados + obtener_en_curso.
    """
    if not property_id:
        property_id = _default_property_id()
    return (
        obtener_asignados(property_id=property_id)
        + obtener_en_curso(property_id=property_id)
    )


def obtener_tickets_por_estado(
    estado: str,
    *,
    org_id=None,
    hotel_id=None,
    property_id: str = None,
) -> List[Dict[str, Any]]:
    """
    Tickets filtrados por estado Flask (PENDIENTE, ASIGNADO, EN_CURSO…).
    Stub compat → mapea estado y llama a NestJS.
    """
    if not property_id:
        property_id = _default_property_id()
    nestjs_status = STATUS_TO_NESTJS.get(estado.upper(), estado.lower())
    data = api_get("/api/v1/tickets", params={
        "propertyId": property_id,
        "status":     nestjs_status,
    })
    return [ticket_from_nestjs(t) for t in _items(data)]


def actualizar_estado_ticket(ticket_id, nuevo_estado: str) -> bool:
    """
    Actualiza el estado de un ticket.
    Stub compat → despacha a la función NestJS correspondiente.
    """
    estado = nuevo_estado.upper()
    if estado == "EN_CURSO":
        return iniciar_ticket(ticket_id)
    if estado == "PAUSADO":
        return pausar_ticket(ticket_id)
    if estado in ("RESUELTO", "COMPLETADO"):
        return finalizar_ticket(ticket_id)
    # Fallback genérico
    ticket_uuid = _resolve_ticket_uuid(ticket_id)
    if not ticket_uuid:
        logger.error("actualizar_estado_ticket: no se pudo resolver UUID para idCode=%s", ticket_id)
        return False
    result = api_put(
        f"/api/v1/tickets/{ticket_uuid}",
        {"status": STATUS_TO_NESTJS.get(estado, estado.lower())},
    )
    ok = result is not None
    if ok:
        logger.info("actualizar_estado_ticket: ticket=%s → %s", ticket_id, nuevo_estado)
    return ok


def actualizar_ticket_estado(ticket_id, nuevo_estado: str) -> bool:
    """Alias de compatibilidad → actualizar_estado_ticket."""
    return actualizar_estado_ticket(ticket_id, nuevo_estado)


def actualizar_area_ticket(ticket_id, nueva_area: str) -> bool:
    """
    Actualiza el área de un ticket.
    Stub compat → PUT /api/v1/tickets/:id con areaCode.
    """
    ticket_uuid = _resolve_ticket_uuid(ticket_id)
    if not ticket_uuid:
        logger.error("actualizar_area_ticket: no se pudo resolver UUID para idCode=%s", ticket_id)
        return False
    area_code = AREA_TO_NESTJS.get(nueva_area.upper(), nueva_area.upper())
    result = api_put(f"/api/v1/tickets/{ticket_uuid}", {"areaCode": area_code})
    ok = result is not None
    if ok:
        logger.info("actualizar_area_ticket: ticket=%s → %s", ticket_id, area_code)
    return ok


def completar_ticket(ticket_id) -> bool:
    """Marca un ticket como RESUELTO. Stub compat → finalizar_ticket."""
    return finalizar_ticket(ticket_id)
