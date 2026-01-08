"""
UI simplificada para supervisión - Sin menú, solo comandos.
"""

def texto_saludo_supervisor() -> str:
    """
    Saludo simple y directo sin menú.
    
    Returns:
        Texto del saludo
    """
    return """👋 Hola,aaaaaaaaaaaaa soy el asistente de Supervisión de Hestia.

💬 Puedes decirme (texto o audio):

📋 ASIGNAR:
• "asignar 1503 a María"
• "más urgente" (te muestro el más importante)
• "pendientes" (lista completa)

➕ CREAR:
• "hab 420 limpieza urgente"
• "crear hab 305 toallas"

⚠️ VER URGENTES:
• "urgente" (solo los importantes)
• "retrasados" (>10 min sin resolver)

🔄 REASIGNAR:
• "reasignar 1501 a Pedro"

💡 Todo funciona con audio también."""


def texto_tickets_pendientes_simple(tickets: list) -> str:
    """
    Muestra tickets pendientes de forma simple.
    
    Args:
        tickets: Lista de tickets
    
    Returns:
        Texto formateado
    """
    if not tickets:
        return "✅ No hay tickets pendientes"
    
    lineas = [f"📋 {len(tickets)} tickets pendientes:\n"]
    
    for ticket in tickets[:5]:  # Máximo 5
        prioridad = {"ALTA": "🔴", "MEDIA": "🟡", "BAJA": "🟢"}.get(
            ticket.get("prioridad", "MEDIA"), "🟡"
        )
        lineas.append(
            f"{prioridad} #{ticket['id']} · Hab. {ticket['habitacion']} · "
            f"{ticket['detalle'][:30]}"
        )
    
    if len(tickets) > 5:
        lineas.append(f"\n... y {len(tickets) - 5} más")
    
    lineas.append("\n💡 Di: 'asignar [#] a [nombre]' o 'más urgente'")
    
    return "\n".join(lineas)


def texto_ticket_asignado_simple(ticket_id: int, worker_nombre: str) -> str:
    """
    Confirmación simple de asignación.
    
    Args:
        ticket_id: ID del ticket
        worker_nombre: Nombre del trabajador
    
    Returns:
        Texto formateado
    """
    return f"✅ #{ticket_id} → {worker_nombre}"


def texto_recomendaciones_simple(workers_con_score: list) -> str:
    """
    Recomendaciones compactas.
    
    Args:
        workers_con_score: Lista de workers con scores
    
    Returns:
        Texto formateado
    """
    lineas = ["🎯 ¿A quién?\n"]
    
    for i, worker in enumerate(workers_con_score[:3], 1):  # Top 3
        estado_emoji = {
            "disponible": "✅",
            "ocupada": "🔴",
            "en_pausa": "⏸️"
        }.get(mucama.get("estado"), "❓")
        
        lineas.append(f"{i}. {estado_emoji} {worker['nombre']}")
    
    lineas.append("\n💡 Di el nombre o número")
    
    return "\n".join(lineas)


def texto_ticket_creado_simple(ticket_id: int, habitacion: str, prioridad: str) -> str:
    """
    Confirmación simple de creación.
    
    Args:
        ticket_id: ID del ticket
        habitacion: Número de habitación
        prioridad: Prioridad del ticket
    
    Returns:
        Texto formateado
    """
    prioridad_emoji = {"ALTA": "🔴", "MEDIA": "🟡", "BAJA": "🟢"}.get(prioridad, "🟡")
    
    return f"""✅ Ticket #{ticket_id} creado
{prioridad_emoji} Hab. {habitacion}

💡 Di: 'asignar a [nombre]' o 'más urgente'"""


def texto_urgentes(pendientes_urgentes: list, retrasados: list) -> str:
    """
    Muestra solo lo urgente.
    
    Args:
        pendientes_urgentes: Tickets pendientes hace >5 min
        retrasados: Tickets en progreso hace >10 min
    
    Returns:
        Texto formateado
    """
    lineas = ["⚠️ URGENTE:\n"]
    
    if pendientes_urgentes:
        lineas.append(f"📋 {len(pendientes_urgentes)} pendientes hace >5 min:")
        for t in pendientes_urgentes[:3]:
            lineas.append(f"  🔴 #{t['id']} · Hab. {t['habitacion']} · {t['tiempo_sin_resolver_mins']} min")
        lineas.append("")
    
    if retrasados:
        lineas.append(f"⏰ {len(retrasados)} retrasados (>10 min):")
        for t in retrasados[:3]:
            lineas.append(f"  ⚠️ #{t['id']} · {t['asignado_a_nombre']} · {t['tiempo_sin_resolver_mins']} min")
    
    if not pendientes_urgentes and not retrasados:
        return "✅ Todo bien, nada urgente"
    
    lineas.append("\n💡 Di: 'asignar [#] a [nombre]'")
    
    return "\n".join(lineas)