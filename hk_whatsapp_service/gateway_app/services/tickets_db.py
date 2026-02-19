# gateway_app/services/tickets_db.py
"""
Persistencia de tickets en Supabase (Postgres) o SQLite fallback.

Alineado al schema REAL de public.tickets:
(org_id, hotel_id, area, prioridad, estado, detalle, canal_origen, ubicacion, huesped_whatsapp, ...)

Convención actual del proyecto:
- Al crear: huesped_whatsapp = teléfono del supervisor (creado_por)
- Al asignar: huesped_whatsapp = "{worker_phone}|{worker_name}" (para que HK filtre por phone)
"""

import os

import logging
from typing import Dict, Any, List, Optional

from gateway_app.services.db import fetchone, fetchall, execute, using_pg
import re

logger = logging.getLogger(__name__)

def _env_int(name: str) -> int:
    v = (os.getenv(name) or "").strip()
    if not v:
        raise RuntimeError(f"Missing required env var: {name}")
    try:
        return int(v)
    except ValueError as e:
        raise RuntimeError(f"Env var {name} must be an int, got: {v!r}") from e


def _default_scope() -> tuple[int, int]:
    # Source of truth: Render env vars
    org_id = _env_int("ORG_ID_DEFAULT")
    hotel_id = _env_int("HOTEL_ID_DEFAULT")
    return org_id, hotel_id


def crear_ticket(
    habitacion: str,
    detalle: str,
    prioridad: str,
    creado_por: str,
    origen: str = "supervisor",
    *,
    area: str = "HOUSEKEEPING",
    canal_origen: str = "WHATSAPP_BOT_SUPERVISION",
    org_id=None,
    hotel_id=None,
    # ── NUEVOS parámetros de routing ──────────────────────────
    routing_source: str = None,
    routing_reason: str = None,
    routing_confidence: float = None,
    routing_version: str = None,
):
    """
    Crea un ticket en public.tickets.
    org_id/hotel_id se toman desde env si no se pasan.
    routing_* se toman del clasificador de tickets.
    """
    if org_id is None or hotel_id is None:
        d_org, d_hotel = _default_scope()
        org_id = d_org if org_id is None else org_id
        hotel_id = d_hotel if hotel_id is None else hotel_id

    table = "public.tickets" if using_pg() else "tickets"
    estado = "PENDIENTE"

    logger.info(
        "Creando ticket | Org=%s | Hotel=%s | Ubic=%s | Prioridad=%s | Area=%s | Routing=%s (%.2f)",
        org_id, hotel_id, habitacion, prioridad, area,
        routing_source or "none",
        routing_confidence or 0.0,
    )

    if using_pg():
        sql = f"""
            INSERT INTO {table} (
                org_id, hotel_id, area, prioridad, estado, detalle,
                canal_origen, ubicacion,
                huesped_whatsapp,
                qr_required,
                assignment_notif_sent,
                csat_survey_triggered,
                in_progress_notif_sent,
                routing_source,
                routing_reason,
                routing_confidence,
                routing_version,
                created_at
            )
            VALUES (
                ?, ?, ?, ?, ?, ?,
                ?, ?,
                ?,
                false,
                false,
                false,
                false,
                ?,
                ?,
                ?,
                ?,
                NOW()
            )
            RETURNING *
        """
        ticket = fetchone(
            sql,
            [
                org_id,
                hotel_id,
                area,
                prioridad,
                estado,
                detalle,
                canal_origen,
                habitacion,         # ubicacion
                creado_por,         # huesped_whatsapp
                routing_source,
                routing_reason,
                routing_confidence,
                routing_version,
            ],
        )
        return ticket

    # SQLite fallback (dev local)
    sql = f"""
        INSERT INTO {table} (
            org_id, hotel_id, area, prioridad, estado, detalle,
            canal_origen, ubicacion,
            huesped_whatsapp,
            qr_required,
            assignment_notif_sent,
            csat_survey_triggered,
            in_progress_notif_sent,
            routing_source,
            routing_reason,
            routing_confidence,
            routing_version,
            created_at
        )
        VALUES (
            ?, ?, ?, ?, ?, ?,
            ?, ?,
            ?,
            0, 0, 0, 0,
            ?, ?, ?, ?,
            datetime('now')
        )
    """
    # (Para SQLite, el RETURNING * no funciona igual;
    #  adaptar según tu setup local si lo usas)
    execute(sql, [
        org_id, hotel_id, area, prioridad, estado, detalle,
        canal_origen, habitacion,
        creado_por,
        routing_source, routing_reason, routing_confidence, routing_version,
    ])
    return fetchone(f"SELECT * FROM {table} ORDER BY id DESC LIMIT 1")


def asignar_ticket(ticket_id: int, asignado_a_phone: str, asignado_a_nombre: str) -> bool:
    """
    Asigna ticket: estado=ASIGNADO y guarda "phone|nombre" en huesped_whatsapp.
    """
    table = "public.tickets" if using_pg() else "tickets"

    sql = f"""
        UPDATE {table}
        SET estado = 'ASIGNADO',
            huesped_whatsapp = ?,
            assigned_at = NOW()
        WHERE id = ?
    """
    phone_with_name = f"{asignado_a_phone}|{asignado_a_nombre}"

    try:
        execute(sql, [phone_with_name, ticket_id], commit=True)
        return True
    except Exception as e:
        logger.exception("Error asignando ticket: %s", e)
        return False

def _norm_phone(phone: str) -> str:
    return re.sub(r"\D+", "", phone or "")

def obtener_tickets_asignados_a(phone: str) -> List[Dict[str, Any]]:
    """
    Retorna tickets asignados al worker.
    Busca en huesped_whatsapp (formato: "phone|nombre" cuando está asignado).
    """
    table = "public.tickets" if using_pg() else "tickets"

    sql = f"""
    SELECT *
    FROM {table}
    WHERE huesped_whatsapp LIKE ?
      AND estado IN ('ASIGNADO', 'EN_CURSO', 'PAUSADO')
      AND deleted_at IS NULL
    ORDER BY 
        CASE prioridad
            WHEN 'ALTA' THEN 1
            WHEN 'MEDIA' THEN 2
            WHEN 'BAJA' THEN 3
            ELSE 4
        END,
        created_at ASC
    """

    try:
        tickets = fetchall(sql, [f"{phone}|%"])
        logger.info(f"📋 Encontrados {len(tickets)} tickets para {phone}")
        return tickets
    except Exception as e:
        logger.exception("Error obteniendo tickets asignados: %s", e)
        return []

def obtener_tickets_asignados_y_en_curso(
    *,
    org_id: Optional[int] = None,
    hotel_id: Optional[int] = None,
) -> list:
    """
    Obtiene tickets con estado ASIGNADO o EN_CURSO
    FILTRADOS por org_id y hotel_id.
    """
    if org_id is None or hotel_id is None:
        d_org, d_hotel = _default_scope()
        org_id = d_org if org_id is None else org_id
        hotel_id = d_hotel if hotel_id is None else hotel_id

    try:
        tickets = fetchall(
            """
            SELECT 
                t.id,
                t.ubicacion,
                t.detalle,
                t.prioridad,
                t.estado,
                t.huesped_whatsapp,
                CASE 
                    WHEN POSITION('|' IN COALESCE(t.huesped_whatsapp, '')) > 0 
                    THEN SPLIT_PART(t.huesped_whatsapp, '|', 2)
                    ELSE NULL
                END as worker_name,
                CASE 
                    WHEN POSITION('|' IN COALESCE(t.huesped_whatsapp, '')) > 0 
                    THEN SPLIT_PART(t.huesped_whatsapp, '|', 1)
                    ELSE t.huesped_whatsapp
                END as worker_phone,
                t.created_at,
                t.assigned_at
            FROM public.tickets t
            WHERE t.org_id = ?
              AND t.hotel_id = ?
              AND t.estado IN ('ASIGNADO', 'EN_CURSO')
              AND t.deleted_at IS NULL
            ORDER BY 
                CASE t.prioridad
                    WHEN 'ALTA' THEN 1
                    WHEN 'MEDIA' THEN 2
                    WHEN 'BAJA' THEN 3
                    ELSE 4
                END,
                t.created_at ASC
            """,
            [org_id, hotel_id],
        )
        
        logger.info(f"📊 {len(tickets)} tickets ASIGNADOS/EN_CURSO obtenidos (org={org_id}, hotel={hotel_id})")
        return tickets
        
    except Exception as e:
        logger.error(f"❌ Error obteniendo tickets asignados/en_curso: {e}")
        return []

def obtener_tickets_por_worker(worker_phone: str):
    """
    Alias por compatibilidad.
    Algunos orquestadores importan `obtener_tickets_por_worker`.
    En este proyecto, la función real es `obtener_tickets_asignados_a`.
    """
    return obtener_tickets_asignados_a(worker_phone)    


def obtener_tickets_por_estado(
    estado: str,
    *,
    org_id: Optional[int] = None,
    hotel_id: Optional[int] = None,
) -> List[Dict[str, Any]]:
    table = "public.tickets" if using_pg() else "tickets"

    if org_id is None or hotel_id is None:
        d_org, d_hotel = _default_scope()
        org_id = d_org if org_id is None else org_id
        hotel_id = d_hotel if hotel_id is None else hotel_id

    try:
        return fetchall(
            f"""
            SELECT *
            FROM {table}
            WHERE org_id = ?
              AND hotel_id = ?
              AND estado = ?
              AND deleted_at IS NULL
            ORDER BY created_at DESC
            """,
            [org_id, hotel_id, estado],
        ) or []
    except Exception as e:
        logger.exception("Error obteniendo tickets por estado: %s", e)
        return []


def obtener_ticket_por_id(ticket_id: int) -> Optional[Dict[str, Any]]:
    table = "public.tickets" if using_pg() else "tickets"
    try:
        return fetchone(f"SELECT * FROM {table} WHERE id = ?", [ticket_id])
    except Exception as e:
        logger.exception("Error obteniendo ticket por id: %s", e)
        return None

def actualizar_estado_ticket(ticket_id: int, nuevo_estado: str) -> bool:
    """
    Actualiza el estado de un ticket.
    
    Args:
        ticket_id: ID del ticket
        nuevo_estado: Nuevo estado (ASIGNADO, EN_CURSO, PAUSADO, RESUELTO)
    
    Returns:
        True si se actualizó correctamente
    """
    table = "public.tickets" if using_pg() else "tickets"
    
    sql = f"""
        UPDATE {table}
        SET estado = ?
        WHERE id = ?
    """
    
    try:
        execute(sql, [nuevo_estado, ticket_id], commit=True)
        logger.info(f"✅ Ticket #{ticket_id} actualizado a {nuevo_estado}")
        return True
    except Exception as e:
        logger.exception(f"❌ Error actualizando estado de ticket: {e}")
        return False
    
# ============================================================
# COMPAT / ALIASES para orchestrator_hk_multiticket.py
# (evita ImportError cuando el HK intenta "tomar")
# ============================================================

def actualizar_ticket_estado(ticket_id: int, nuevo_estado: str) -> bool:
    """
    Alias compatible con el orquestador HK.
    Debe actualizar el estado del ticket (ej: ASIGNADO -> EN_CURSO).
    """
    # Si ya tienes una función equivalente, úsala aquí:
    # Ejemplos típicos: actualizar_estado_ticket, set_ticket_estado, cambiar_estado_ticket
    return actualizar_estado_ticket(ticket_id, nuevo_estado)

def obtener_pendientes(
    *,
    org_id: Optional[int] = None,
    hotel_id: Optional[int] = None,
) -> List[Dict[str, Any]]:
    table = "public.tickets" if using_pg() else "tickets"

    if org_id is None or hotel_id is None:
        org_id, hotel_id = _default_scope()

    estados = ("PENDIENTE", "PENDIENTE_APROBACION", "PENDIENTE_APROBACIÓN")
    placeholders = ",".join(["?"] * len(estados))

    return fetchall(
        f"""
        SELECT *
        FROM {table}
        WHERE org_id = ?
          AND hotel_id = ?
          AND estado IN ({placeholders})
          AND deleted_at IS NULL
        ORDER BY created_at DESC
        """,
        [org_id, hotel_id, *estados],
    ) or []

def tomar_ticket_asignado(ticket_id: int, worker_phone: str) -> bool:
    """
    ✅ FIX C1: Marca un ticket como EN_CURSO SOLO si está asignado a ese worker.
    Valida pertenencia via huesped_whatsapp (formato "phone|nombre").
    
    Nota: Actualmente no se usa (el orquestador HK usa actualizar_ticket_estado),
    pero queda disponible si se necesita validación estricta de pertenencia.
    """
    p = _norm_phone(worker_phone)
    if not p:
        return False

    table = "public.tickets" if using_pg() else "tickets"

    # Verificar que el ticket pertenece al worker y está en estado válido
    ticket = fetchone(
        f"""
        SELECT id, huesped_whatsapp, estado
        FROM {table}
        WHERE id = ?
          AND estado IN ('ASIGNADO', 'PENDIENTE')
        """,
        [ticket_id],
    )

    if not ticket:
        logger.warning(f"⚠️ tomar_ticket_asignado: ticket #{ticket_id} no encontrado o estado inválido")
        return False

    # Validar que huesped_whatsapp empieza con el teléfono del worker
    hw = ticket.get("huesped_whatsapp") or ""
    hw_phone = hw.split("|")[0] if "|" in hw else hw
    hw_phone_norm = _norm_phone(hw_phone)

    if hw_phone_norm != p:
        logger.warning(
            f"⚠️ tomar_ticket_asignado: ticket #{ticket_id} asignado a {hw_phone_norm}, "
            f"no a {p}"
        )
        return False

    # Actualizar estado
    try:
        execute(
            f"""
            UPDATE {table}
            SET estado = 'EN_CURSO',
                started_at = COALESCE(started_at, {'NOW()' if using_pg() else 'CURRENT_TIMESTAMP'})
            WHERE id = ?
            """,
            [ticket_id],
            commit=True,
        )
        logger.info(f"✅ tomar_ticket_asignado: ticket #{ticket_id} tomado por {p}")
        return True
    except Exception as e:
        logger.exception(f"❌ Error tomando ticket {ticket_id} para {p}: {e}")
        return False

def agregar_media_a_ticket(
    ticket_id: int,
    media_type: str,
    storage_url: str,
    whatsapp_media_id: str,
    mime_type: str,
    file_size_bytes: int,
    uploaded_by: str
) -> Optional[int]:
    """
    Agrega un registro de media a un ticket.
    
    Args:
        ticket_id: ID del ticket
        media_type: 'image', 'video', 'document', 'audio'
        storage_url: URL en Supabase Storage (puede ser vacío si falló el upload)
        whatsapp_media_id: ID original del media en WhatsApp
        mime_type: Tipo MIME (image/jpeg, video/mp4, etc.)
        file_size_bytes: Tamaño en bytes
        uploaded_by: Teléfono del usuario que subió el media
    
    Returns:
        ID del registro creado o None si falló
    """
    from gateway_app.services.db import execute, fetchone, using_pg
    
    table = "public.ticket_media" if using_pg() else "ticket_media"
    
    sql = f"""
        INSERT INTO {table} 
        (ticket_id, media_type, storage_url, whatsapp_media_id, mime_type, file_size_bytes, uploaded_by)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        RETURNING id
    """
    
    try:
        if using_pg():
            result = fetchone(sql, [
                ticket_id, media_type, storage_url, whatsapp_media_id,
                mime_type, file_size_bytes, uploaded_by
            ])
            return result["id"] if result else None
        else:
            # SQLite no soporta RETURNING
            execute(sql.replace("RETURNING id", ""), [
                ticket_id, media_type, storage_url, whatsapp_media_id,
                mime_type, file_size_bytes, uploaded_by
            ], commit=True)
            result = fetchone("SELECT last_insert_rowid() as id")
            return result["id"] if result else None
            
    except Exception as e:
        logger.exception(f"❌ Error agregando media a ticket #{ticket_id}: {e}")
        return None


def obtener_media_de_ticket(ticket_id: int) -> List[Dict[str, Any]]:
    """
    Obtiene todos los medios asociados a un ticket.
    
    Args:
        ticket_id: ID del ticket
    
    Returns:
        Lista de registros de media
    """
    from gateway_app.services.db import fetchall, using_pg
    
    table = "public.ticket_media" if using_pg() else "ticket_media"
    
    sql = f"""
        SELECT id, ticket_id, media_type, storage_url, whatsapp_media_id,
               mime_type, file_size_bytes, uploaded_by, created_at
        FROM {table}
        WHERE ticket_id = ?
        ORDER BY created_at ASC
    """
    
    try:
        return fetchall(sql, [ticket_id]) or []
    except Exception as e:
        logger.exception(f"❌ Error obteniendo media de ticket #{ticket_id}: {e}")
        return []


def contar_media_de_ticket(ticket_id: int) -> int:
    """
    Cuenta cuántos medios tiene un ticket.
    
    Args:
        ticket_id: ID del ticket
    
    Returns:
        Cantidad de medios
    """
    from gateway_app.services.db import fetchone, using_pg
    
    table = "public.ticket_media" if using_pg() else "ticket_media"
    
    sql = f"SELECT COUNT(*) as count FROM {table} WHERE ticket_id = ?"
    
    try:
        result = fetchone(sql, [ticket_id])
        return result["count"] if result else 0
    except Exception as e:
        logger.exception(f"❌ Error contando media de ticket #{ticket_id}: {e}")
        return 0


def obtener_primer_media_de_ticket(ticket_id: int) -> Optional[Dict[str, Any]]:
    """
    Obtiene el primer media de un ticket (útil para previews).
    
    Args:
        ticket_id: ID del ticket
    
    Returns:
        Registro de media o None
    """
    from gateway_app.services.db import fetchone, using_pg
    
    table = "public.ticket_media" if using_pg() else "ticket_media"
    
    sql = f"""
        SELECT id, ticket_id, media_type, storage_url, whatsapp_media_id,
               mime_type, file_size_bytes, uploaded_by, created_at
        FROM {table}
        WHERE ticket_id = ?
        ORDER BY created_at ASC
        LIMIT 1
    """
    
    try:
        return fetchone(sql, [ticket_id])
    except Exception as e:
        logger.exception(f"❌ Error obteniendo primer media de ticket #{ticket_id}: {e}")
        return None


def eliminar_media(media_id: int) -> bool:
    """
    Elimina un registro de media.
    
    Args:
        media_id: ID del registro de media
    
    Returns:
        True si se eliminó correctamente
    """
    from gateway_app.services.db import execute, using_pg
    
    table = "public.ticket_media" if using_pg() else "ticket_media"
    
    sql = f"DELETE FROM {table} WHERE id = ?"
    
    try:
        execute(sql, [media_id], commit=True)
        return True
    except Exception as e:
        logger.exception(f"❌ Error eliminando media #{media_id}: {e}")
        return False


def mover_media_a_ticket(whatsapp_media_id: str, ticket_id: int) -> bool:
    """
    Mueve un media pendiente (sin ticket) a un ticket específico.
    Útil cuando se crea el ticket después de recibir el media.
    
    Args:
        whatsapp_media_id: ID del media en WhatsApp
        ticket_id: ID del ticket destino
    
    Returns:
        True si se actualizó correctamente
    """
    from gateway_app.services.db import execute, using_pg
    
    table = "public.ticket_media" if using_pg() else "ticket_media"
    
    sql = f"""
        UPDATE {table}
        SET ticket_id = ?
        WHERE whatsapp_media_id = ? AND ticket_id IS NULL
    """
    
    try:
        execute(sql, [ticket_id, whatsapp_media_id], commit=True)
        return True
    except Exception as e:
        logger.exception(f"❌ Error moviendo media a ticket #{ticket_id}: {e}")
        return False