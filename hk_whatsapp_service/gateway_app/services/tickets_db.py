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
    org_id: Optional[int] = None,
    hotel_id: Optional[int] = None,
) -> Optional[Dict[str, Any]]:
    """
    Crea un ticket en public.tickets (schema real).
    org_id/hotel_id se toman desde env (ORG_ID_DEFAULT/HOTEL_ID_DEFAULT) si no se pasan.
    """
    if org_id is None or hotel_id is None:
        d_org, d_hotel = _default_scope()
        org_id = d_org if org_id is None else org_id
        hotel_id = d_hotel if hotel_id is None else hotel_id

    table = "public.tickets" if using_pg() else "tickets"
    estado = "PENDIENTE"

    logger.info(
        "Creando ticket | Org=%s | Hotel=%s | Ubic=%s | Prioridad=%s | Area=%s",
        org_id, hotel_id, habitacion, prioridad, area
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

def _norm_phone(phone: str) -> str:
    return re.sub(r"\D+", "", phone or "")

def tomar_ticket_asignado(ticket_id: int, worker_phone: str) -> bool:
    """
    Marca un ticket como EN_CURSO SOLO si está asignado a ese worker_phone.
    Esto evita bugs tipo "tomar 38 -> toma otro" y valida pertenencia en BD.
    """
    p = _norm_phone(worker_phone)
    if not p:
        return False

    # Considera ambas variantes por si tu BD guarda con o sin '+'
    p_plus = f"+{p}"

    sql = """
        UPDATE public.tickets
        SET estado = 'EN_CURSO',
            started_at = COALESCE(started_at, NOW())
        WHERE id = ?
          AND (worker_phone = ? OR worker_phone = ?)
          AND estado IN ('ASIGNADO', 'PENDIENTE')
    """

    try:
        # Ajusta el helper de ejecución al que uses:
        # - si tienes execute(sql, params) que retorna rowcount, úsalo
        # - si tienes run(sql, params) idem
        rows = execute(sql, [ticket_id, p, p_plus])  # <-- asegúrate que execute devuelva filas afectadas
        ok = bool(rows and rows > 0)
        logger.info(f"✅ tomar_ticket_asignado ticket_id={ticket_id} phone={p} ok={ok} rows={rows}")
        return ok
    except Exception as e:
        logger.exception(f"❌ Error tomando ticket {ticket_id} para {p}: {e}")
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

def obtener_tickets_asignados_y_en_curso() -> list:
    """
    Obtiene todos los tickets con estado ASIGNADO o EN_CURSO.
    Extrae el nombre del worker de huesped_whatsapp (formato: "phone|nombre").
    
    Returns:
        Lista de tickets ordenados por prioridad y fecha
    """
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
                -- ✅ FIX v2: Usar POSITION en lugar de LIKE
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
            WHERE t.estado IN ('ASIGNADO', 'EN_CURSO')
            ORDER BY 
                CASE t.prioridad
                    WHEN 'ALTA' THEN 1
                    WHEN 'MEDIA' THEN 2
                    WHEN 'BAJA' THEN 3
                    ELSE 4
                END,
                t.created_at ASC
            """
        )
        
        logger.info(f"📊 {len(tickets)} tickets ASIGNADOS/EN_CURSO obtenidos")
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
