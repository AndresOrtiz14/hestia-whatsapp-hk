"""
Sistema de asignación de tickets a workers con scoring inteligente.
VERSIÓN MEJORADA: Prioriza workers según área del ticket.
"""
from .ubicacion_helpers import normalize_area

def calcular_score_worker(worker: dict, ticket: dict = None) -> int:
    """
    Calcula score de un worker para asignar ticket.
    Mayor score = más apropiado.
    
    Args:
        worker: Datos del worker desde BD
        ticket: Datos del ticket (opcional, para match de área)
    
    Returns:
        Score total (0-500)
    
    Factores considerados:
    - Match de área (CRÍTICO): +200 si coincide, -100 si no
    - Estado disponible: +50
    - Ocupado: -30
    - En pausa: -100
    - Carga de trabajo: -10 por cada ticket asignado
    - Turno activo: +30
    """
    score = 100  # Base
    
    # ✅ NUEVO: Match de área (FACTOR MÁS IMPORTANTE)
    if ticket:
        ticket_ubicacion = ticket.get("habitacion") or ticket.get("ubicacion", "")
        worker_area = normalize_area(worker.get("area"))
        
        # Detectar si el ticket es de habitación o área común
        is_habitacion = False
        if ticket_ubicacion:
            # Limpiar y verificar
            ubicacion_str = str(ticket_ubicacion).strip()
            if ubicacion_str.isdigit():
                num = int(ubicacion_str)
                if 100 <= num <= 9999:
                    is_habitacion = True
        
        if is_habitacion:
            # ✅ Ticket de habitación → Priorizar HOUSEKEEPING
            if worker_area in ["HOUSEKEEPING", "HK"]:
                score += 200  # BONUS GRANDE
            else:
                score -= 50  # Penalización leve (puede ayudar pero no es ideal)
        else:
            # ✅ Ticket de área común → Priorizar AREAS_COMUNES o MANTENIMIENTO
            if worker_area in ["AREAS_COMUNES", "ÁREAS_COMUNES", "AC", "MANTENIMIENTO", "MANTENCIÓN", "MT"]:
                score += 200  # BONUS GRANDE
            elif worker_area in ["HOUSEKEEPING", "HK"]:
                score -= 100  # Penalización mayor (no es su especialidad)
    
    # Estado: Disponible (no ocupada, no pausada)
    if not worker.get("ocupada", False) and not worker.get("pausada", False):
        score += 50
    
    # Ocupada
    if worker.get("ocupada", False):
        score -= 30
    
    # En pausa
    if worker.get("pausada", False):
        score -= 100
    
    # Carga de trabajo (menos tickets = mejor)
    tickets_asignados = worker.get("tickets_asignados", 0)
    score -= tickets_asignados * 10
    
    # Turno activo
    if worker.get("turno_activo", False):
        score += 30
    else:
        score -= 50  # Penalización si no tiene turno activo
    
    return max(score, 0)  # No permitir scores negativos


def elegir_mejor_worker(workers: list, ticket: dict = None) -> dict:
    """
    Elige el mejor worker de una lista según scoring.
    
    Args:
        workers: Lista de workers
        ticket: Datos del ticket (opcional)
    
    Returns:
        Worker con mayor score
    """
    if not workers:
        return None
    
    workers_con_score = []
    for worker in workers:
        score = calcular_score_worker(worker, ticket)
        workers_con_score.append((worker, score))
    
    # Ordenar por score descendente
    workers_con_score.sort(key=lambda x: x[1], reverse=True)
    
    # Retornar el primero (mayor score)
    return workers_con_score[0][0]


def ordenar_workers_por_score(workers: list, ticket: dict = None) -> list:
    """
    Ordena workers por score.
    
    Args:
        workers: Lista de workers
        ticket: Datos del ticket (opcional)
    
    Returns:
        Lista de workers ordenados por score (mayor primero)
    """
    if not workers:
        return []
    
    workers_con_score = []
    for worker in workers:
        score = calcular_score_worker(worker, ticket)
        workers_con_score.append({**worker, "score": score})
    
    # Ordenar por score descendente
    workers_con_score.sort(key=lambda w: w["score"], reverse=True)
    
    return workers_con_score


def confirmar_asignacion(from_phone: str, ticket_id: int, worker: dict) -> None:
    """
    Confirma la asignación de un ticket a un worker.
    
    Args:
        from_phone: Teléfono del supervisor
        ticket_id: ID del ticket
        worker: Datos del worker
    """
    from gateway_app.flows.supervision.outgoing import send_whatsapp
    from gateway_app.services.tickets_db import obtener_ticket_por_id
    from .ubicacion_helpers import normalize_area
    
    # Obtener datos del ticket
    ticket = obtener_ticket_por_id(ticket_id)
    
    if not ticket:
        send_whatsapp(from_phone, f"❌ No encontré el ticket #{ticket_id}")
        return
    
    # Formatear ubicación con emoji apropiado
    ubicacion = ticket.get("ubicacion") or ticket.get("habitacion", "?")
    ubicacion_fmt = formatear_ubicacion_con_emoji(ubicacion)
    
    # Datos del worker
    worker_nombre = worker.get("nombre_completo", worker.get("nombre", "?"))
    worker_area = normalize_area(worker.get("area"))
    area_emoji = get_area_emoji(worker_area)
    area_short = get_area_short(worker_area)
    
    # Prioridad
    prioridad = ticket.get("prioridad", "MEDIA")
    prioridad_emoji = {"ALTA": "🔴", "MEDIA": "🟡", "BAJA": "🟢"}.get(prioridad, "🟡")
    
    # Mensaje al supervisor
    mensaje = (
        f"✅ Tarea #{ticket_id} asignada\n\n"
        f"{ubicacion_fmt}\n"
        f"📝 Problema: {ticket.get('detalle', 'Sin detalle')}\n"
        f"{prioridad_emoji} Prioridad: {prioridad}\n"
        f"👤 Asignado a: {worker_nombre} ({area_emoji} {area_short})"
    )
    
    send_whatsapp(from_phone, mensaje)