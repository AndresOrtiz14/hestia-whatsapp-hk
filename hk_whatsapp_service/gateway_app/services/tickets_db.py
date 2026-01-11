# gateway_app/services/tickets_db.py
"""
Persistencia de tickets en Supabase.
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
    
    Args:
        habitacion: Número de habitación
        detalle: Descripción del problema
        prioridad: ALTA, MEDIA, BAJA
        creado_por: Teléfono de quien creó
        origen: supervisor, huesped, trabajador
    
    Returns:
        Dict con datos del ticket creado (incluyendo ID)
    """
    logger.info(f"💾 Creando ticket | Hab: {habitacion} | Prioridad: {prioridad}")
    
    table = "public.tickets" if using_pg() else "tickets"
    
    sql = f"""
        INSERT INTO {table}
        (habitacion, detalle, prioridad, origen, estado, creado_por, tiempo_sin_resolver_mins)
        VALUES (?, ?, ?, ?, 'pendiente', ?, 0)
    """
    
    try:
        execute(sql, [habitacion, detalle, prioridad, origen, creado_por], commit=True)
        
        # Obtener el ticket recién creado
        ticket = fetchone(
            f"SELECT * FROM {table} WHERE creado_por = ? ORDER BY created_at DESC LIMIT 1",
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
    asignado_a: str,
    asignado_a_nombre: str
) -> bool:
    """
    Asigna un ticket a un trabajador.
    
    Args:
        ticket_id: ID del ticket
        asignado_a: Teléfono del trabajador
        asignado_a_nombre: Nombre del trabajador
    
    Returns:
        True si se asignó correctamente
    """
    logger.info(f"👤 Asignando ticket #{ticket_id} → {asignado_a_nombre}")
    
    table = "public.tickets" if using_pg() else "tickets"
    
    sql = f"""
        UPDATE {table}
        SET asignado_a = ?,
            asignado_a_nombre = ?,
            estado = 'en_progreso'
        WHERE id = ?
    """
    
    try:
        execute(sql, [asignado_a, asignado_a_nombre, ticket_id], commit=True)
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
            WHERE estado = 'pendiente'
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
            WHERE estado = 'pendiente'
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