"""
Módulo de asignación de tickets a workers.
"""

from typing import Dict, Any, Optional
from .demo_data import (
    DEMO_WORKERS,
    get_ticket_by_id,
    get_worker_by_nombre
)
from .state import (
    get_supervisor_state,
    ASIGNAR_ELIGIENDO_MUCAMA,
    ASIGNAR_CONFIRMANDO,
    MENU_PRINCIPAL
)
from .ui import (
    formato_recomendacion_worker,
    mensaje_ticket_asignado,
    recordatorio_menu
)
from .outgoing import send_whatsapp


def calcular_score_worker(worker: Dict[str, Any]) -> int:
    """
    Calcula el score de recomendación para una worker.
    
    Args:
        worker: Datos de la worker
    
    Returns:
        Score de 0 a 100
    """
    score = 100
    
    # Penalizar si está ocupada
    if worker.get("estado") == "ocupada" or worker.get("ticket_activo"):
        score -= 50
    
    # Penalizar si está en pausa
    if worker.get("estado") == "en_pausa":
        score -= 30
    
    # Bonus si ha completado pocos tickets hoy (balanceo)
    tickets_hoy = worker.get("tickets_completados_hoy", 0)
    score += (10 - tickets_hoy) * 5
    
    # Bonus si tiene buen promedio de tiempo
    promedio = worker.get("promedio_tiempo_resolucion", 20)
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
    mostrar_recomendaciones_workers(from_phone, ticket_id)


def mostrar_recomendaciones_workers(from_phone: str, ticket_id: int) -> None:
    """
    Muestra las workers disponibles con recomendaciones.
    
    Args:
        from_phone: Número de teléfono del supervisor
        ticket_id: ID del ticket
    """
    # Calcular scores
    workers_con_score = []
    for worker in DEMO_MUCAMAS:
        score = calcular_score_worker(worker)
        workers_con_score.append({
            **worker,
            "score": score
        })
    
    # Ordenar por score
    workers_con_score.sort(key=lambda m: m["score"], reverse=True)
    
    # Construir mensaje
    lineas = [f"🎯 Recomendaciones para Ticket #{ticket_id}\n"]
    
    for i, worker in enumerate(workers_con_score, 1):
        lineas.append(formato_recomendacion_worker(i, worker, worker["score"]))
        lineas.append("")  # Línea vacía
    
    lineas.append("¿A quién asignar?")
    lineas.append("• Escribe el número (1, 2, 3)")
    lineas.append("• O el nombre (María, Pedro, Ana)")
    
    mensaje = "\n".join(lineas) + recordatorio_menu()
    send_whatsapp(from_phone, mensaje)


def handle_seleccion_worker(from_phone: str, text: str) -> None:
    """
    Maneja la selección de worker por el supervisor.
    
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
    worker = None
    
    # Opción 1: Selección por número (1, 2, 3)
    if raw.isdigit():
        index = int(raw) - 1
        if 0 <= index < len(DEMO_MUCAMAS):
            # Ordenar igual que en recomendaciones
            workers_ordenadas = sorted(
                DEMO_MUCAMAS,
                key=lambda m: calcular_score_worker(m),
                reverse=True
            )
            worker = workers_ordenadas[index]
    
    # Opción 2: Selección por nombre
    else:
        worker = get_worker_by_nombre(raw)
    
    # Verificar que se encontró la worker
    if not worker:
        send_whatsapp(
            from_phone,
            "❌ No reconocí esa worker.\n"
            "Intenta con el número (1, 2, 3) o el nombre exacto."
        )
        # Volver a mostrar recomendaciones
        mostrar_recomendaciones_workers(from_phone, ticket_id)
        return
    
    # Confirmar asignación
    confirmar_asignacion(from_phone, ticket_id, worker)


def confirmar_asignacion(
    from_phone: str,
    ticket_id: int,
    worker: Dict[str, Any]
) -> None:
    """
    Confirma la asignación del ticket a la worker.
    
    Args:
        from_phone: Número de teléfono del supervisor
        ticket_id: ID del ticket
        worker: Datos de la worker
    """
    state = get_supervisor_state(from_phone)
    
    # Guardar worker seleccionada
    state["worker_seleccionada"] = worker["phone"]
    
    # En un sistema real, aquí se actualizaría la base de datos
    # y se enviaría notificación a la worker
    
    # TODO: Actualizar ticket en BD
    # ticket.asignado_a = worker["phone"]
    # ticket.asignado_a_nombre = worker["nombre"]
    # ticket.estado = "asignado"
    # db.save(ticket)
    
    # TODO: Notificar a worker
    # notify_worker_new_ticket(worker["phone"], ticket)
    
    # Confirmar al supervisor
    mensaje = mensaje_ticket_asignado(ticket_id, worker["nombre"])
    mensaje += "\n\n💡 En producción: se notificaría a la worker"
    mensaje += recordatorio_menu()
    
    send_whatsapp(from_phone, mensaje)
    
    # Limpiar estado y volver al menú
    state["ticket_seleccionado"] = None
    state["worker_seleccionada"] = None
    state["menu_state"] = MENU_PRINCIPAL