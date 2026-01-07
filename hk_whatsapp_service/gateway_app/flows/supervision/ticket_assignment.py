"""
Módulo de asignación de tickets a mucamas (versión simplificada).
"""

from typing import Dict, Any
from .demo_data import (
    DEMO_MUCAMAS,
    get_ticket_by_id,
    get_mucama_by_nombre
)
from .state import get_supervisor_state
from .ui_simple import texto_ticket_asignado_simple
from .outgoing import send_whatsapp


def calcular_score_mucama(mucama: Dict[str, Any]) -> int:
    """
    Calcula el score de recomendación para una mucama.
    
    Args:
        mucama: Datos de la mucama
    
    Returns:
        Score de 0 a 100
    """
    score = 100
    
    # Penalizar si está ocupada
    if mucama.get("estado") == "ocupada" or mucama.get("ticket_activo"):
        score -= 50
    
    # Penalizar si está en pausa
    if mucama.get("estado") == "en_pausa":
        score -= 30
    
    # Bonus si ha completado pocos tickets hoy (balanceo)
    tickets_hoy = mucama.get("tickets_completados_hoy", 0)
    score += (10 - tickets_hoy) * 5
    
    # Bonus si tiene buen promedio de tiempo
    promedio = mucama.get("promedio_tiempo_resolucion", 20)
    if promedio < 15:
        score += 20
    
    return max(0, min(100, score))


def confirmar_asignacion(
    from_phone: str,
    ticket_id: int,
    mucama: Dict[str, Any]
) -> None:
    """
    Confirma la asignación del ticket a la mucama.
    
    Args:
        from_phone: Número de teléfono del supervisor
        ticket_id: ID del ticket
        mucama: Datos de la mucama
    """
    state = get_supervisor_state(from_phone)
    
    # Guardar mucama seleccionada
    state["mucama_seleccionada"] = mucama["phone"]
    
    # En un sistema real, aquí se actualizaría la base de datos
    # y se enviaría notificación a la mucama
    
    # TODO: Actualizar ticket en BD
    # ticket.asignado_a = mucama["phone"]
    # ticket.asignado_a_nombre = mucama["nombre"]
    # ticket.estado = "asignado"
    # db.save(ticket)
    
    # TODO: Notificar a mucama
    # notify_mucama_new_ticket(mucama["phone"], ticket)
    
    # Confirmar al supervisor (versión simple)
    mensaje = texto_ticket_asignado_simple(ticket_id, mucama["nombre"])
    send_whatsapp(from_phone, mensaje)
    
    # Limpiar estado
    state["ticket_seleccionado"] = None
    state["mucama_seleccionada"] = None
    state["esperando_asignacion"] = False