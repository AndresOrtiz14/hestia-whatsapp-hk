from typing import Dict, Any
import time

from .outgoing import send_whatsapp
from .demo_tickets import DEMO_TICKETS

# Cada cuánto tiempo podemos mandar un recordatorio (en segundos)
REMINDER_INTERVAL_SECONDS = 5 * 60 # 5 minutos

def hay_tickets_pendientes(state: Dict[str, Any]) -> bool:
        
    """
    DEMO: consideramos que hay tickets pendientes si existe al menos
    un ticket en DEMO_TICKETS.

    En producción, aquí se debería consultar la base de datos para ver si
    la mucama tiene tickets asignados o disponibles.
    """
    return bool(DEMO_TICKETS)

# =========================
#   RECORDATORIOS
# =========================

def _maybe_send_recordatorio_pendientes(phone: str, state: Dict[str, Any]):
    """
    Envía un recordatorio cada 5 minutos *solo si*:
    - La persona tiene turno activo
    - NO está trabajando en ningún ticket (ticket_state es None)
    - Hay tickets pendientes por resolver
    - Ya pasaron al menos 5 minutos desde el último recordatorio
    """
    # 1) Debe tener turno activo
    if not state.get("turno_activo"):
        return

    # 2) No puede estar en un flujo de ticket
    if state.get("ticket_state") is not None:
        return

    # 3) Debe haber tickets pendientes / disponibles
    if not hay_tickets_pendientes(state):
        return

    # 4) Intervalo mínimo entre recordatorios
    now = time.time()
    last_ts = state.get("last_reminder_ts")

    if last_ts is not None and (now - last_ts) < REMINDER_INTERVAL_SECONDS:
        return

    # Actualizamos timestamp y enviamos recordatorio
    state["last_reminder_ts"] = now

    send_whatsapp(
        phone,
        "Tienes casos pendientes por resolver.\n"
        "Para verlos, escribe *2* (Tickets por resolver) o *M* para ver el menú."
    )
