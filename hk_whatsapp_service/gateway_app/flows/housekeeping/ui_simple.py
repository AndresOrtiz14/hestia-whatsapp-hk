"""
UI simplificada para bot de Housekeeping.
Mensajes cortos y claros.
"""

def texto_menu_simple(turno_activo: bool = True) -> str:
    """
    Menú principal con opciones según estado de turno.
    
    Args:
        turno_activo: Si el turno está activo
    
    Returns:
        Texto del menú
    """
    if turno_activo:
        return """🏨 Menú de Operaciones

1. 📋 Ver mis tareas
2. ➕ Reportar problema
3. 🔴 Terminar turno
4. ❓ Ayuda

💡 O escribe:
- 'tomar' - Tomar tarea
- 'fin' - Finalizar
- 'pausar' - Pausar"""
    else:
        return """🏨 Menú de Operaciones

1. 🟢 Iniciar turno
2. ❓ Ayuda

⚠️ Debes iniciar turno para trabajar"""


def texto_ayuda() -> str:
    """
    Texto de ayuda.
    
    Returns:
        Texto de ayuda
    """
    return """❓ Ayuda

📋 TRABAJAR:
• 'tomar' - Tomar la más urgente
• 'fin' - Finalizar tarea
• 'pausar' / 'reanudar'

➕ REPORTAR:
• 'reportar' - Crear reporte
• O di: "hab 305 fuga de agua"

🔍 VER:
• 'tareas' - Ver mis tareas
• 'M' - Volver al menú"""


def texto_saludo_dia() -> str:
    """
    Saludo del día.
    
    Returns:
        Texto de saludo
    """
    return """👋 Hola, soy el asistente de operaciones de Hestia.
Te ayudo a gestionar tus tareas del día."""

def texto_saludo_con_turno(turno_activo: bool) -> str:
    """
    Saludo del día con estado de turno.
    
    Args:
        turno_activo: Si el turno está activo
    
    Returns:
        Texto de saludo
    """
    if turno_activo:
        return """👋 Hola, tu turno está activo ✅

🏨 Menú de Operaciones

1. 📋 Ver mis tareas
2. ➕ Reportar problema
3. 🔴 Terminar turno
4. ❓ Ayuda

💡 O escribe:
- 'tomar' - Tomar tarea
- 'fin' - Finalizar
- 'pausar' - Pausar"""
    else:
        return """👋 Hola, tu turno está inactivo ⏸️

💡 Opciones:

1. 🟢 Iniciar turno
2. ❓ Ayuda

Para comenzar a trabajar, inicia tu turno."""

def texto_ticket_asignado(ticket: dict) -> str:
    prioridad_emoji = {
        "ALTA": "🔴",
        "MEDIA": "🟡",
        "BAJA": "🟢"
    }.get(ticket.get("prioridad", "MEDIA"), "🟡")

    hab = ticket.get("habitacion") or ticket.get("ubicacion") or ticket.get("room") or "?"

    return f"""🔔 Nueva tarea asignada

{prioridad_emoji} #{ticket['id']} · Hab. {hab}
{ticket.get('detalle', '')}

💡 Di 'tomar' para empezar"""


def texto_ticket_en_progreso(ticket: dict) -> str:
    hab = ticket.get("habitacion") or ticket.get("ubicacion") or ticket.get("room") or "?"
    return f"""✅ #{ticket['id']} en progreso
📋 Hab. {hab} · {ticket.get('detalle', '')}

💡 'fin' cuando termines"""


def texto_ticket_completado(ticket: dict, tiempo_mins: int) -> str:
    """
    Confirmación de ticket completado.
    
    Args:
        ticket: Datos del ticket
        tiempo_mins: Tiempo que tomó
    
    Returns:
        Texto formateado
    """
    return f"""✅ #{ticket['id']} completado
⏱️ Tiempo: {tiempo_mins} min

¡Buen trabajo! 🎉"""


def texto_ticket_pausado(ticket: dict) -> str:
    """
    Confirmación de pausa.
    
    Args:
        ticket: Datos del ticket
    
    Returns:
        Texto formateado
    """
    return f"""⏸️ #{ticket['id']} pausado

💡 'reanudar' para continuar"""


def texto_ticket_reanudado(ticket: dict) -> str:
    """
    Confirmación de reanudación.
    
    Args:
        ticket: Datos del ticket
    
    Returns:
        Texto formateado
    """
    return f"""▶️ #{ticket['id']} reanudado"""


def texto_lista_tickets(tickets: list) -> str:
    if not tickets:
        return "✅ No tienes tareas pendientes"

    lineas = [f"📋 {len(tickets)} tarea(s):\n"]

    for ticket in tickets[:5]:
        prioridad_emoji = {
            "ALTA": "🔴",
            "MEDIA": "🟡",
            "BAJA": "🟢"
        }.get(ticket.get("prioridad", "MEDIA"), "🟡")

        hab = ticket.get("habitacion") or ticket.get("ubicacion") or ticket.get("room") or "?"
        detalle = (ticket.get("detalle") or "")[:30]

        lineas.append(f"{prioridad_emoji} #{ticket['id']} · Hab. {hab} · {detalle}")

    if len(tickets) > 5:
        lineas.append(f"\n... y {len(tickets) - 5} más")

    lineas.append("\n💡 Di 'tomar' o el #")

    return "\n".join(lineas)


def texto_ticket_creado(ticket_id: int, habitacion: str, prioridad: str) -> str:
    """
    Confirmación de reporte creado.
    
    Args:
        ticket_id: ID del reporte
        habitacion: Número de habitación
        prioridad: Prioridad detectada
    
    Returns:
        Texto formateado
    """
    prioridad_emoji = {
        "ALTA": "🔴",
        "MEDIA": "🟡",
        "BAJA": "🟢"
    }.get(prioridad, "🟡")
    
    return f"""✅ Reporte #{ticket_id} creado
{prioridad_emoji} Hab. {habitacion}

Notificado a operaciones ✓"""


def texto_pedir_habitacion() -> str:
    """
    Solicita número de habitación.
    
    Returns:
        Texto de solicitud
    """
    return "🛏️ ¿Qué habitación?\n(ej: 305)"


def texto_pedir_detalle() -> str:
    """
    Solicita detalle del problema.
    
    Returns:
        Texto de solicitud
    """
    return "📝 ¿Qué pasó?\n(texto o audio)"


def texto_confirmar_reporte(habitacion: str, detalle: str, prioridad: str) -> str:
    prioridad_emoji = {
        "ALTA": "🔴",
        "MEDIA": "🟡",
        "BAJA": "🟢"
    }.get(prioridad, "🟡")
    
    return f"""📋 Confirma el reporte:

🛏️ Habitación: {habitacion}
📝 Problema: {detalle}
{prioridad_emoji} Prioridad: {prioridad}

✅ Escribe 'sí' para confirmar
✏️ O 'editar' para cambiar
❌ O 'no' para cancelar
🏨 O 'M' para volver al Menú"""

def texto_confirmar_reporte_adaptado(ubicacion: str, detalle: str, prioridad: str, area_worker: str) -> str:
    """
    Texto de confirmación adaptado al área del worker.
    
    Args:
        ubicacion: Habitación o área
        detalle: Descripción del problema
        prioridad: ALTA, MEDIA o BAJA
        area_worker: Área del worker
    
    Returns:
        Mensaje de confirmación
    """
    from .areas_comunes_helpers import get_texto_por_area
    
    prioridad_emoji = {"ALTA": "🔴", "MEDIA": "🟡", "BAJA": "🟢"}.get(prioridad, "🟡")
    ubicacion_label = get_texto_por_area(area_worker, "ubicacion_label")
    
    return (
        f"✅ Confirma el reporte:\n\n"
        f"{ubicacion_label}: {ubicacion}\n"
        f"📝 Problema: {detalle}\n"
        f"{prioridad_emoji} Prioridad: {prioridad}\n\n"
        f"💡 Responde:\n"
        f"• 'sí' para confirmar\n"
        f"• 'editar' para cambiar\n"
        f"• 'cancelar' para abortar"
    )