"""
UI texts y helpers de formato para el bot de Supervisión.
"""

from typing import Dict, Any, List, Optional
from datetime import datetime


def texto_menu_principal(tickets_pendientes: int = 0, tickets_progreso: int = 0) -> str:
    """
    Genera el menú principal del supervisor.
    
    Args:
        tickets_pendientes: Cantidad de tickets sin asignar
        tickets_progreso: Cantidad de tickets en progreso
    
    Returns:
        Texto del menú formateado
    """
    return f"""👤 Menú Supervisor

1. 📋 Ver tickets pendientes ({tickets_pendientes})
2. 🔄 Ver tickets en progreso ({tickets_progreso})
3. 👥 Ver estado de mucamas
4. ➕ Crear ticket manual
5. 📊 Estadísticas del día

Escribe el número o 'M' para este menú"""


def formato_ticket_simple(ticket: Dict[str, Any]) -> str:
    """
    Formato simple de ticket para listas.
    
    Args:
        ticket: Dict con datos del ticket
    
    Returns:
        Línea formateada
        
    Ejemplo:
        🔴 #1503 · Hab. 210 · Cambio sábanas · 15 min
    """
    prioridad_emoji = {
        "ALTA": "🔴",
        "MEDIA": "🟡",
        "BAJA": "🟢"
    }.get(ticket.get("prioridad", "MEDIA"), "🟡")
    
    ticket_id = ticket.get("id")
    habitacion = ticket.get("habitacion", "???")
    detalle = ticket.get("detalle", "Sin detalle")
    
    # Truncar detalle si es muy largo
    if len(detalle) > 30:
        detalle = detalle[:27] + "..."
    
    # Calcular tiempo si está disponible
    tiempo_str = ""
    if ticket.get("tiempo_sin_resolver_mins"):
        mins = ticket["tiempo_sin_resolver_mins"]
        tiempo_str = f" · {mins} min"
    
    return f"{prioridad_emoji} #{ticket_id} · Hab. {habitacion} · {detalle}{tiempo_str}"


def formato_ticket_detallado(ticket: Dict[str, Any]) -> str:
    """
    Formato detallado de ticket (>10 min sin resolver).
    
    Args:
        ticket: Dict con datos del ticket
    
    Returns:
        Texto formateado con detalles
    """
    prioridad_emoji = {
        "ALTA": "🔴",
        "MEDIA": "🟡",
        "BAJA": "🟢"
    }.get(ticket.get("prioridad", "MEDIA"), "🟡")
    
    ticket_id = ticket.get("id")
    habitacion = ticket.get("habitacion", "???")
    detalle = ticket.get("detalle", "Sin detalle")
    asignado_a = ticket.get("asignado_a_nombre", "Sin asignar")
    
    # Tiempo total
    created_at = ticket.get("created_at")
    tiempo_total = 0
    if created_at:
        # Calcular diferencia (simplificado, asumir string ISO)
        tiempo_total = ticket.get("tiempo_sin_resolver_mins", 0)
    
    # Tiempo efectivo vs pausas
    total_paused = ticket.get("total_paused_seconds", 0) // 60
    tiempo_efectivo = max(0, tiempo_total - total_paused)
    
    mensaje = f"""⚠️ #{ticket_id} · Hab. {habitacion} · {detalle} · {asignado_a}

🕐 Tiempo total: {tiempo_total} min
⏱️ Trabajo efectivo: {tiempo_efectivo} min
⏸️ Pausas: {total_paused} min

Estado actual: {ticket.get('estado', 'desconocido')}

💡 Lleva más de 10 min sin resolver"""
    
    return mensaje


def formato_mucama_estado(mucama: Dict[str, Any]) -> str:
    """
    Formato de estado de mucama para lista.
    
    Args:
        mucama: Dict con datos de la mucama
    
    Returns:
        Línea formateada
        
    Ejemplo:
        1. ✅ María - Disponible (5 tickets hoy)
    """
    nombre = mucama.get("nombre", "Sin nombre")
    estado = mucama.get("estado", "desconocido")
    ticket_activo = mucama.get("ticket_activo")
    tickets_hoy = mucama.get("tickets_completados_hoy", 0)
    
    # Emoji según estado
    emoji = "✅"  # Disponible
    estado_texto = "Disponible"
    
    if estado == "ocupada" or ticket_activo:
        emoji = "🔴"
        estado_texto = f"Ocupada (#{ticket_activo})"
    elif estado == "en_pausa":
        emoji = "⏸️"
        estado_texto = "En pausa"
    
    return f"{emoji} {nombre} - {estado_texto} ({tickets_hoy} tickets hoy)"


def formato_recomendacion_mucama(index: int, mucama: Dict[str, Any], score: int) -> str:
    """
    Formato de recomendación de mucama con score.
    
    Args:
        index: Número en la lista (1, 2, 3...)
        mucama: Dict con datos de la mucama
        score: Score de recomendación (0-100)
    
    Returns:
        Texto formateado
    """
    nombre = mucama.get("nombre", "Sin nombre")
    estado = mucama.get("estado", "desconocido")
    tickets_hoy = mucama.get("tickets_completados_hoy", 0)
    promedio = mucama.get("promedio_tiempo_resolucion", 0)
    
    # Emoji según estado
    if estado == "disponible":
        emoji = "✅"
        estado_texto = "Disponible"
    elif estado == "en_pausa":
        emoji = "⏸️"
        estado_texto = "En pausa"
    else:
        emoji = "🔴"
        estado_texto = f"Ocupada (#{mucama.get('ticket_activo')})"
    
    return f"""{index}. {emoji} {nombre} - {estado_texto} (score: {score})
   └─ {tickets_hoy} tickets hoy, promedio {promedio:.0f} min"""


def formato_estadisticas_dia(stats: Dict[str, Any]) -> str:
    """
    Formato de estadísticas del día.
    
    Args:
        stats: Dict con estadísticas
    
    Returns:
        Texto formateado
    """
    fecha = datetime.now().strftime("%d %b %Y")
    
    return f"""📊 Estadísticas - {fecha}

Tickets:
✅ Completados: {stats.get('completados', 0)}
🔄 En progreso: {stats.get('en_progreso', 0)}
📋 Pendientes: {stats.get('pendientes', 0)}
❌ Rechazados: {stats.get('rechazados', 0)}

Mucamas:
👥 Total: {stats.get('total_mucamas', 0)}
✅ Disponibles: {stats.get('mucamas_disponibles', 0)}
🔴 Ocupadas: {stats.get('mucamas_ocupadas', 0)}

⏱️ Tiempo promedio: {stats.get('tiempo_promedio', 0):.1f} min"""


def recordatorio_menu() -> str:
    """
    Recordatorio para volver al menú.
    
    Returns:
        Texto del recordatorio
    """
    return "\n\n💡 Escribe 'M' para ver el menú."


def mensaje_ticket_asignado(ticket_id: int, mucama_nombre: str) -> str:
    """
    Mensaje de confirmación de asignación.
    
    Args:
        ticket_id: ID del ticket
        mucama_nombre: Nombre de la mucama
    
    Returns:
        Texto formateado
    """
    return f"""✅ Ticket #{ticket_id} asignado a {mucama_nombre}

Enviando notificación..."""


def mensaje_ticket_creado(ticket_id: int, habitacion: str, prioridad: str) -> str:
    """
    Mensaje de confirmación de creación de ticket.
    
    Args:
        ticket_id: ID del ticket creado
        habitacion: Número de habitación
        prioridad: Prioridad del ticket
    
    Returns:
        Texto formateado
    """
    prioridad_emoji = {
        "ALTA": "🔴",
        "MEDIA": "🟡",
        "BAJA": "🟢"
    }.get(prioridad, "🟡")
    
    return f"""✅ Ticket creado exitosamente

Ticket #{ticket_id} · Hab. {habitacion}
Prioridad: {prioridad_emoji} {prioridad}

¿Asignar ahora?
1. Sí, asignar
2. Dejar en cola"""


def mensaje_nuevo_ticket_huesped(ticket: Dict[str, Any]) -> str:
    """
    Notificación de nuevo ticket de huésped.
    
    Args:
        ticket: Dict con datos del ticket
    
    Returns:
        Texto formateado
    """
    prioridad_emoji = {
        "ALTA": "🔴",
        "MEDIA": "🟡",
        "BAJA": "🟢"
    }.get(ticket.get("prioridad", "MEDIA"), "🟡")
    
    ticket_id = ticket.get("id")
    habitacion = ticket.get("habitacion", "???")
    detalle = ticket.get("detalle", "Sin detalle")
    prioridad = ticket.get("prioridad", "MEDIA")
    
    return f"""🔔 Nuevo ticket de huésped

Ticket #{ticket_id} · Hab. {habitacion}
Detalle: {detalle}
Prioridad: {prioridad_emoji} {prioridad}

Responde:
• 'asignar' - Para asignar
• #{ticket_id} - Para ver más
• 'M' - Para menú"""


def mensaje_ticket_completado(ticket: Dict[str, Any]) -> str:
    """
    Notificación de ticket completado por mucama.
    
    Args:
        ticket: Dict con datos del ticket
    
    Returns:
        Texto formateado
    """
    ticket_id = ticket.get("id")
    habitacion = ticket.get("habitacion", "???")
    mucama = ticket.get("asignado_a_nombre", "Mucama")
    tiempo = ticket.get("tiempo_resolucion_mins", 0)
    
    return f"""✅ Ticket completado

Ticket #{ticket_id} · Hab. {habitacion}
Resuelto por: {mucama}
Tiempo: {tiempo} min"""


def mensaje_ticket_retrasado(ticket: Dict[str, Any]) -> str:
    """
    Alerta de ticket retrasado (>10 min).
    
    Args:
        ticket: Dict con datos del ticket
    
    Returns:
        Texto formateado
    """
    ticket_id = ticket.get("id")
    habitacion = ticket.get("habitacion", "???")
    mucama = ticket.get("asignado_a_nombre", "Mucama")
    mins = ticket.get("tiempo_sin_resolver_mins", 0)
    
    return f"""⏰ Ticket retrasado

Ticket #{ticket_id} · Hab. {habitacion}
Asignado a: {mucama}
Tiempo transcurrido: {mins} min

¿Necesita ayuda?"""