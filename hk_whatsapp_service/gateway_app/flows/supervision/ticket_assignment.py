"""
Módulo de asignación de tickets a mucamas.
"""

from typing import Dict, Any, Optional
from .demo_data import (
    DEMO_MUCAMAS,
    get_ticket_by_id,
    get_mucama_by_nombre
)
from .state import (
    get_supervisor_state,
    ASIGNAR_ELIGIENDO_MUCAMA,
    ASIGNAR_CONFIRMANDO,
    MENU_PRINCIPAL
)
from .ui import (
    formato_recomendacion_mucama,
    mensaje_ticket_asignado,
    recordatorio_menu
)
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


def iniciar_asignacion(from_phone: str, ticket_id: int) -> None:
    """
    Inicia el proceso de asignación de un ticket.
    
    Args:
        from_phone: Número de teléfono del supervisor
        ticket_id: ID del ticket a asignar
    """
    state = get_supervisor_state(from_phone)
    
    # Verificar que el ticket existe
    ticket = get_ticket_by_id(ticket_id)
    if not ticket:
        send_whatsapp(
            from_phone,
            f"❌ No encontré el ticket #{ticket_id}" + recordatorio_menu()
        )
        return
    
    # Verificar que el ticket está pendiente
    if ticket.get("estado") != "pendiente":
        send_whatsapp(
            from_phone,
            f"❌ El ticket #{ticket_id} ya está {ticket.get('estado')}" +
            recordatorio_menu()
        )
        return
    
    # Guardar ticket seleccionado
    state["ticket_seleccionado"] = ticket_id
    state["menu_state"] = ASIGNAR_ELIGIENDO_MUCAMA
    
    # Mostrar recomendaciones
    mostrar_recomendaciones_mucamas(from_phone, ticket_id)


def mostrar_recomendaciones_mucamas(from_phone: str, ticket_id: int) -> None:
    """
    Muestra las mucamas disponibles con recomendaciones.
    
    Args:
        from_phone: Número de teléfono del supervisor
        ticket_id: ID del ticket
    """
    # Calcular scores
    mucamas_con_score = []
    for mucama in DEMO_MUCAMAS:
        score = calcular_score_mucama(mucama)
        mucamas_con_score.append({
            **mucama,
            "score": score
        })
    
    # Ordenar por score
    mucamas_con_score.sort(key=lambda m: m["score"], reverse=True)
    
    # Construir mensaje
    lineas = [f"🎯 Recomendaciones para Ticket #{ticket_id}\n"]
    
    for i, mucama in enumerate(mucamas_con_score, 1):
        lineas.append(formato_recomendacion_mucama(i, mucama, mucama["score"]))
        lineas.append("")  # Línea vacía
    
    lineas.append("¿A quién asignar?")
    lineas.append("• Escribe el número (1, 2, 3)")
    lineas.append("• O el nombre (María, Pedro, Ana)")
    
    mensaje = "\n".join(lineas) + recordatorio_menu()
    send_whatsapp(from_phone, mensaje)


def handle_seleccion_mucama(from_phone: str, text: str) -> None:
    """
    Maneja la selección de mucama por el supervisor.
    
    Args:
        from_phone: Número de teléfono del supervisor
        text: Texto del mensaje (número o nombre)
    """
    state = get_supervisor_state(from_phone)
    ticket_id = state.get("ticket_seleccionado")
    
    if not ticket_id:
        send_whatsapp(
            from_phone,
            "❌ No hay ticket seleccionado" + recordatorio_menu()
        )
        state["menu_state"] = MENU_PRINCIPAL
        return
    
    raw = text.strip().lower()
    mucama = None
    
    # Opción 1: Selección por número (1, 2, 3)
    if raw.isdigit():
        index = int(raw) - 1
        if 0 <= index < len(DEMO_MUCAMAS):
            # Ordenar igual que en recomendaciones
            mucamas_ordenadas = sorted(
                DEMO_MUCAMAS,
                key=lambda m: calcular_score_mucama(m),
                reverse=True
            )
            mucama = mucamas_ordenadas[index]
    
    # Opción 2: Selección por nombre
    else:
        mucama = get_mucama_by_nombre(raw)
    
    # Verificar que se encontró la mucama
    if not mucama:
        send_whatsapp(
            from_phone,
            "❌ No reconocí esa mucama.\n"
            "Intenta con el número (1, 2, 3) o el nombre exacto."
        )
        # Volver a mostrar recomendaciones
        mostrar_recomendaciones_mucamas(from_phone, ticket_id)
        return
    
    # Confirmar asignación
    confirmar_asignacion(from_phone, ticket_id, mucama)


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
    
    # Confirmar al supervisor
    mensaje = mensaje_ticket_asignado(ticket_id, mucama["nombre"])
    mensaje += "\n\n💡 En producción: se notificaría a la mucama"
    mensaje += recordatorio_menu()
    
    send_whatsapp(from_phone, mensaje)
    
    # Limpiar estado y volver al menú
    state["ticket_seleccionado"] = None
    state["mucama_seleccionada"] = None
    state["menu_state"] = MENU_PRINCIPAL