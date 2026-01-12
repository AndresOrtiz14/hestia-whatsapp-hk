# gateway_app/services/tickets_db.py
"""
Persistencia de tickets en Supabase.
ADAPTADO al schema del bot de huéspedes (Hotel Diego de Almagro).
"""

import logging
from typing import Dict, Any, List, Optional

from gateway_app.services.db import execute, fetchone, fetchall, using_pg

logger = logging.getLogger(__name__)


def crear_ticket(
    habitacion: str,
    detalle: str,
    prioridad: str,
    creado_por: str,
    origen: str = "supervisor"
) -> Dict[str, Any]:
    """
    Crea un nuevo ticket en la base de datos.
    
    ADAPTADO al schema del bot de huéspedes:
    - habitacion → ubicacion
    - origen → canal_origen
    - created_by se omite (no tenemos usuarios en la tabla users)
    
    Args:
        habitacion: Número de habitación
        detalle: Descripción del problema
        prioridad: ALTA, MEDIA, BAJA
        creado_por: Teléfono de quien creó (se guarda en huesped_whatsapp)
        origen: supervisor, huesped, trabajador
    
    Returns:
        Dict con datos del ticket creado (incluyendo ID)
    """
    logger.info(f"💾 Creando ticket | Hab: {habitacion} | Prioridad: {prioridad}")
    
    table = "public.tickets" if using_pg() else "tickets"
    
    # Mapeo de valores al schema del hotel
    area = "HOUSEKEEPING"
    canal_origen = "WHATSAPP_BOT_SUPERVISION"
    
    # Valores por defecto para org_id y hotel_id
    org_id = 1
    hotel_id = 1
    
    # SOLUCIÓN: Guardar el teléfono en huesped_whatsapp en vez de created_by
    sql = f"""
        INSERT INTO {table}
        (org_id, hotel_id, area, prioridad, estado, detalle, canal_origen, ubicacion, huesped_whatsapp, created_at)
        VALUES (?, ?, ?, ?, 'PENDIENTE', ?, ?, ?, ?, NOW())
    """
    
    try:
        execute(
            sql, 
            [org_id, hotel_id, area, prioridad, detalle, canal_origen, habitacion, creado_por],
            commit=True
        )
        
        # Obtener el ticket recién creado
        ticket = fetchone(
            f"SELECT * FROM {table} WHERE huesped_whatsapp = ? ORDER BY created_at DESC LIMIT 1",
            [creado_por]
        )
        
        if ticket:
            logger.info(f"✅ Ticket #{ticket['id']} creado exitosamente en DB")
            return ticket
        else:
            logger.error("❌ No se pudo recuperar el ticket creado")
            return None
            
    except Exception as e:
        logger.exception(f"❌ Error creando ticket en DB: {e}")
        raise

def asignar_ticket(
    ticket_id: int,
    asignado_a_phone: str,
    asignado_a_nombre: str
) -> bool:
    """
    Asigna un ticket a un trabajador.
    
    Args:
        ticket_id: ID del ticket
        asignado_a_phone: Teléfono del trabajador
        asignado_a_nombre: Nombre del trabajador
    
    Returns:
        True si se asignó correctamente
    """
    logger.info(f"👤 Asignando ticket #{ticket_id} → {asignado_a_nombre}")
    
    table = "public.tickets" if using_pg() else "tickets"
    
    # NOTA: assigned_to en el schema del hotel espera user_id (integer)
    # Por ahora guardamos el nombre en huesped_whatsapp y actualizamos estado
    
    sql = f"""
        UPDATE {table}
        SET estado = 'ASIGNADO',
            huesped_whatsapp = ?,
            assigned_at = NOW()
        WHERE id = ?
    """
    
    try:
        # Guardamos el phone + nombre en huesped_whatsapp como: "56912345678|María González"
        phone_with_name = f"{asignado_a_phone}|{asignado_a_nombre}"
        execute(sql, [phone_with_name, ticket_id], commit=True)
        logger.info(f"✅ Ticket #{ticket_id} asignado en DB")
        return True
    except Exception as e:
        logger.exception(f"❌ Error asignando ticket: {e}")
        return False


def obtener_tickets_pendientes() -> List[Dict[str, Any]]:
    """Obtiene todos los tickets pendientes."""
    table = "public.tickets" if using_pg() else "tickets"
    
    if using_pg():
        sql = f"""
            SELECT *,
                   EXTRACT(EPOCH FROM (NOW() - created_at))/60 as tiempo_sin_resolver_mins
            FROM {table}
            WHERE estado = 'PENDIENTE'
            ORDER BY 
                CASE prioridad 
                    WHEN 'ALTA' THEN 1
                    WHEN 'MEDIA' THEN 2
                    WHEN 'BAJA' THEN 3
                END,
                created_at ASC
        """
    else:
        sql = f"""
            SELECT *,
                   (julianday('now') - julianday(created_at)) * 1440 as tiempo_sin_resolver_mins
            FROM {table}
            WHERE estado = 'PENDIENTE'
            ORDER BY 
                CASE prioridad 
                    WHEN 'ALTA' THEN 1
                    WHEN 'MEDIA' THEN 2
                    WHEN 'BAJA' THEN 3
                END,
                created_at ASC
        """
    
    try:
        tickets = fetchall(sql)
        logger.info(f"📋 {len(tickets)} tickets pendientes desde DB")
        return tickets
    except Exception as e:
        logger.exception(f"❌ Error obteniendo tickets pendientes: {e}")
        return []


def obtener_tickets_en_progreso() -> List[Dict[str, Any]]:
    """Obtiene todos los tickets en progreso."""
    table = "public.tickets" if using_pg() else "tickets"
    
    if using_pg():
        sql = f"""
            SELECT *,
                   EXTRACT(EPOCH FROM (NOW() - started_at))/60 as tiempo_sin_resolver_mins
            FROM {table}
            WHERE estado IN ('ASIGNADO', 'ACEPTADO', 'EN_CURSO')
            ORDER BY started_at ASC
        """
    else:
        sql = f"""
            SELECT *,
                   (julianday('now') - julianday(started_at)) * 1440 as tiempo_sin_resolver_mins
            FROM {table}
            WHERE estado IN ('ASIGNADO', 'ACEPTADO', 'EN_CURSO')
            ORDER BY started_at ASC
        """
    
    try:
        tickets = fetchall(sql)
        logger.info(f"🔄 {len(tickets)} tickets en progreso desde DB")
        return tickets
    except Exception as e:
        logger.exception(f"❌ Error obteniendo tickets en progreso: {e}")
        return []


def obtener_ticket_por_id(ticket_id: int) -> Optional[Dict[str, Any]]:
    """Obtiene un ticket por ID."""
    table = "public.tickets" if using_pg() else "tickets"
    sql = f"SELECT * FROM {table} WHERE id = ?"
    
    try:
        ticket = fetchone(sql, [ticket_id])
        if ticket:
            logger.info(f"✅ Ticket #{ticket_id} encontrado")
        else:
            logger.warning(f"⚠️ Ticket #{ticket_id} no encontrado")
        return ticket
    except Exception as e:
        logger.exception(f"❌ Error obteniendo ticket: {e}")
        return None


def completar_ticket(ticket_id: int) -> bool:
    """Marca un ticket como completado."""
    logger.info(f"✅ Completando ticket #{ticket_id}")
    
    table = "public.tickets" if using_pg() else "tickets"
    
    # ADAPTADO: Usa 'RESUELTO' en vez de 'completado'
    sql = f"""
        UPDATE {table}
        SET estado = 'RESUELTO',
            finished_at = NOW()
        WHERE id = ?
    """
    
    try:
        execute(sql, [ticket_id], commit=True)
        logger.info(f"✅ Ticket #{ticket_id} completado")
        return True
    except Exception as e:
        logger.exception(f"❌ Error completando ticket: {e}")

def obtener_tickets_por_estado(estado: str) -> List[Dict[str, Any]]:
    """
    Obtiene tickets filtrados por estado.
    
    Args:
        estado: PENDIENTE, ASIGNADO, EN_CURSO, RESUELTO, etc.
    
    Returns:
        Lista de tickets
    """
    table = "public.tickets" if using_pg() else "tickets"
    
    sql = f"""
        SELECT *
        FROM {table}
        WHERE estado = ?
        ORDER BY created_at DESC
    """
    
    try:
        tickets = fetchall(sql, [estado])
        logger.info(f"📋 {len(tickets)} tickets con estado '{estado}'")
        return tickets
    except Exception as e:
        logger.exception(f"❌ Error obteniendo tickets por estado: {e}")
        return []


def obtener_tickets_asignados_a(phone: str) -> List[Dict[str, Any]]:
    """
    Obtiene todos los tickets asignados a un trabajador específico.
    
    Args:
        phone: Teléfono del trabajador
    
    Returns:
        Lista de tickets asignados
    """
    table = "public.tickets" if using_pg() else "tickets"
    
    # Buscamos en huesped_whatsapp (que tiene formato "phone|nombre")
    sql = f"""
        SELECT *
        FROM {table}
        WHERE huesped_whatsapp LIKE ?
        AND estado IN ('ASIGNADO', 'ACEPTADO', 'EN_CURSO', 'PAUSADO')
        ORDER BY created_at ASC
    """
    
    try:
        # Buscar tickets donde el phone coincida
        tickets = fetchall(sql, [f"{phone}%"])
        logger.info(f"📋 {len(tickets)} tickets asignados a {phone}")
        return tickets
    except Exception as e:
        logger.exception(f"❌ Error obteniendo tickets asignados: {e}")
        return []


def actualizar_estado_ticket(
    ticket_id: int,
    nuevo_estado: str,
    worker_phone: str = None
) -> bool:
    """
    Actualiza el estado de un ticket.
    
    Args:
        ticket_id: ID del ticket
        nuevo_estado: ACEPTADO, EN_CURSO, PAUSADO, RESUELTO
        worker_phone: Teléfono del worker (para verificar ownership)
    
    Returns:
        True si se actualizó correctamente
    """
    logger.info(f"🔄 Actualizando ticket #{ticket_id} → {nuevo_estado}")
    
    table = "public.tickets" if using_pg() else "tickets"
    
    # Actualizar campos según el estado
    if nuevo_estado == "ACEPTADO":
        sql = f"""
            UPDATE {table}
            SET estado = ?,
                accepted_at = NOW()
            WHERE id = ?
        """
    elif nuevo_estado == "EN_CURSO":
        sql = f"""
            UPDATE {table}
            SET estado = ?,
                started_at = NOW()
            WHERE id = ?
        """
    elif nuevo_estado == "RESUELTO":
        sql = f"""
            UPDATE {table}
            SET estado = ?,
                finished_at = NOW()
            WHERE id = ?
        """
    else:
        # PAUSADO o cualquier otro
        sql = f"""
            UPDATE {table}
            SET estado = ?
            WHERE id = ?
        """
    
    try:
        execute(sql, [nuevo_estado, ticket_id], commit=True)
        logger.info(f"✅ Ticket #{ticket_id} actualizado a '{nuevo_estado}'")
        return True
    except Exception as e:
        logger.exception(f"❌ Error actualizando estado: {e}")
        return False