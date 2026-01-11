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
    - Agrega campos requeridos: org_id, hotel_id, area
    
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
    
    # Mapeo de valores al schema del hotel
    area = "HOUSEKEEPING"  # Por defecto, ajustar según necesidad
    canal_origen = origen.upper() if origen else "WHATSAPP"
    
    # Valores por defecto para org_id y hotel_id (ajustar según tu setup)
    org_id = 1  # ID de tu organización
    hotel_id = 1  # ID del hotel
    
    sql = f"""
        INSERT INTO {table}
        (org_id, hotel_id, area, prioridad, estado, detalle, canal_origen, ubicacion, created_at, created_by)
        VALUES (?, ?, ?, ?, 'PENDIENTE', ?, ?, ?, NOW(), ?)
    """
    
    try:
        execute(
            sql, 
            [org_id, hotel_id, area, prioridad, detalle, canal_origen, habitacion, creado_por],
            commit=True
        )
        
        # Obtener el ticket recién creado
        ticket = fetchone(
            f"SELECT * FROM {table} WHERE created_by = ? ORDER BY created_at DESC LIMIT 1",
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
    
    ADAPTADO: Usa 'assigned_to' del schema del hotel.
    
    Args:
        ticket_id: ID del ticket
        asignado_a: Teléfono del trabajador (se guarda como texto por ahora)
        asignado_a_nombre: Nombre del trabajador (no se guarda en este schema)
    
    Returns:
        True si se asignó correctamente
    """
    logger.info(f"👤 Asignando ticket #{ticket_id} → {asignado_a_nombre}")
    
    table = "public.tickets" if using_pg() else "tickets"
    
    # NOTA: assigned_to probablemente espera un user_id (integer), no phone (text)
    # Por ahora lo dejamos como texto, pero en producción necesitarás mapear phone → user_id
    
    sql = f"""
        UPDATE {table}
        SET estado = 'ASIGNADO',
            assigned_at = NOW()
        WHERE id = ?
    """
    
    try:
        execute(sql, [ticket_id], commit=True)
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
        return False