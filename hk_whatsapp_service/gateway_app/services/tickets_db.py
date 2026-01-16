# gateway_app/services/tickets_db.py
"""
Persistencia de tickets en Supabase (Postgres) o SQLite fallback.

Alineado al schema REAL de public.tickets:
(org_id, hotel_id, area, prioridad, estado, detalle, canal_origen, ubicacion, huesped_whatsapp, ...)

Convención actual del proyecto:
- Al crear: huesped_whatsapp = teléfono del supervisor (creado_por)
- Al asignar: huesped_whatsapp = "{worker_phone}|{worker_name}" (para que HK filtre por phone)
"""

import logging
from typing import Dict, Any, List, Optional

from gateway_app.services.db import fetchone, fetchall, execute, using_pg

logger = logging.getLogger(__name__)

DEFAULT_ORG_ID = 1
DEFAULT_HOTEL_ID = 1


def crear_ticket(
    habitacion: str,
    detalle: str,
    prioridad: str,
    creado_por: str,
    origen: str = "supervisor",
    *,
    area: str = "HOUSEKEEPING",
    canal_origen: str = "WHATSAPP_BOT_SUPERVISION",
    org_id: int = DEFAULT_ORG_ID,
    hotel_id: int = DEFAULT_HOTEL_ID,
) -> Optional[Dict[str, Any]]:
    """
    Crea un ticket en public.tickets (schema real).
    """
    table = "public.tickets" if using_pg() else "tickets"
    estado = "PENDIENTE"

    logger.info("Creando ticket | Hab=%s | Prioridad=%s | Area=%s", habitacion, prioridad, area)

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
                habitacion,   # ubicacion
                creado_por,   # huesped_whatsapp
            ],
        )
        return ticket

    # SQLite fallback (solo para dev local si lo usas)
    sql = f"""
        INSERT INTO {table} (
            org_id, hotel_id, area, prioridad, estado, detalle,
            canal_origen, ubicacion,
            huesped_whatsapp,
            qr_required,
            assignment_notif_sent,
            csat_survey_triggered,
            in_progress_notif_sent,
            created_at
        )
        VALUES (
            ?, ?, ?, ?, ?, ?,
            ?, ?,
            ?,
            0,
            0,
            0,
            0,
            CURRENT_TIMESTAMP
        )
    """
    execute(
        sql,
        [
            org_id,
            hotel_id,
            area,
            prioridad,
            estado,
            detalle,
            canal_origen,
            habitacion,
            creado_por,
        ],
        commit=True,
    )

    ticket = fetchone(
        f"SELECT * FROM {table} WHERE huesped_whatsapp = ? ORDER BY created_at DESC LIMIT 1",
        [creado_por],
    )
    return ticket


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

def obtener_tickets_por_worker(worker_phone: str):
    """
    Alias por compatibilidad.
    Algunos orquestadores importan `obtener_tickets_por_worker`.
    En este proyecto, la función real es `obtener_tickets_asignados_a`.
    """
    return obtener_tickets_asignados_a(worker_phone)


def obtener_tickets_por_estado(estado: str) -> List[Dict[str, Any]]:
    table = "public.tickets" if using_pg() else "tickets"
    try:
        return fetchall(
            f"SELECT * FROM {table} WHERE estado = ? ORDER BY created_at DESC",
            [estado],
        )
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