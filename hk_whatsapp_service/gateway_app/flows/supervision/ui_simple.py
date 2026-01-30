"""
UI simplificada para supervisión - Sin menú, solo comandos.
"""
from typing import List, Dict, Any

def texto_saludo_supervisor() -> str:
    """
    Saludo/ayuda con todos los comandos disponibles para supervisores.
    """
    return """👋 ¡Hola! Soy tu asistente de operaciones.

📊 *VER TICKETS*
• `pendientes` → sin asignar
• `asignados` → en proceso  
• `urgentes` → prioridad alta
• `retrasados` → >10 min sin resolver
• `en curso` → trabajos activos
• `ticket 15` → info del #15

👥 *VER EQUIPO*
• `equipo` → estado de trabajadores

🎯 *ASIGNAR*
• `asignar 15 a María`
• `reasignar 12 a Pedro`
• `más urgente` → asigna el próximo

✅ *FINALIZAR*
• `finalizar 15`

📝 *CREAR TICKET*
• `hab 420 limpieza urgente`
• `crear 305 toallas`

❓ *OTROS*
• `ayuda` → ver este mensaje
• `cancelar` → abortar operación

🎤 Todo funciona con texto y audio."""

def texto_tickets_pendientes_simple(tickets: List[Dict]) -> str:
    if not tickets:
        return "✅ No hay tickets pendientes"

    shown = 10
    lineas = [f"📋 {len(tickets)} pendiente(s):\n"]

    for ticket in tickets[:shown]:
        prioridad = (ticket.get("prioridad") or "MEDIA").upper()
        prioridad_emoji = {"ALTA": "🔴", "MEDIA": "🟡", "BAJA": "🟢"}.get(prioridad, "🟡")

        hab = ticket.get("ubicacion") or ticket.get("habitacion") or "?"
        detalle = (ticket.get("detalle") or "")[:30]
        lineas.append(f"{prioridad_emoji} #{ticket['id']} · Hab. {hab} · {detalle}")

    if len(tickets) > shown:
        lineas.append(f"\n... y {len(tickets) - shown} más")

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
        }.get(worker.get("estado"), "❓")
        
        nombre = worker.get('nombre_completo') or worker.get('username') or worker.get('nombre', '?')
        lineas.append(f"{i}. {estado_emoji} {nombre}")
    
    lineas.append("\n💡 Di el nombre o número")
    lineas.append("O escribe 'cancelar'")
    
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
    
    return f"""✅ Tarea #{ticket_id} creado
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