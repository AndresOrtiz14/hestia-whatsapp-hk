"""
Módulo simplificado de asignación - solo scoring.
Para sistema sin menú complejo.
"""

from typing import Dict, Any


def calcular_score_worker(worker: Dict[str, Any]) -> int:
    """
    Calcula el score de recomendación para un worker.
    
    Args:
        worker: Datos del worker
    
    Returns:
        Score de 0 a 100
    """
    score = 100
    
    # Penalizar si está ocupado
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


def confirmar_asignacion(from_phone: str, ticket_id: int, worker: Dict[str, Any]) -> None:
    """
    Confirma asignación (versión simplificada).
    
    Args:
        from_phone: Teléfono del supervisor
        ticket_id: ID del ticket
        worker: Datos del worker
    """
    from .outgoing import send_whatsapp
    
    # TODO: Actualizar en BD
    # TODO: Notificar a worker
    
    worker_nombre = worker.get("nombre_completo", worker.get("nombre", "?"))
    mensaje = f"✅ Tarea #{ticket_id} → {worker_nombre}"
    mensaje += "\n\n💡 En producción: se notificaría al trabajador"
    
    send_whatsapp(from_phone, mensaje)


# Alias para retrocompatibilidad
calcular_score_mucama = calcular_score_worker