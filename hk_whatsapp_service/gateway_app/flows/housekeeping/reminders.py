from typing import Dict, Any
import time

from .outgoing import send_whatsapp
from .demo_tickets import DEMO_TICKETS

REMINDER_INTERVAL_SECONDS = 5 * 60  # 5 minutos


def hay_tickets_pendientes(state: Dict[str, Any]) -> bool:
    """
    DEMO: hay tickets si existe al menos uno en DEMO_TICKETS.
    """
    return bool(DEMO_TICKETS)


def maybe_send_recordatorio_pendientes(phone: str, state: Dict[str, Any]) -> None:
    """
    Envía un recordatorio cada 5 minutos *solo si*:
    - La persona tiene turno activo
    - NO hay ticket en ejecución (ticket_activo is None)
    - NO está en un flujo conversacional de ticket (ticket_state is None)
    - Hay tickets pendientes por resolver
    - Ya pasaron al menos 5 minutos desde el último recordatorio
    """
    # 0) Si hay un ticket activo (aunque estés en menú), NO mandar recordatorios
    if state.get("ticket_activo") is not None:
        return

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

    state["last_reminder_ts"] = now

    send_whatsapp(
        phone,
        "Tienes casos pendientes por resolver.\n"
        "Para verlos, escribe *2* (Tickets por resolver) o *M* para ver el menú."
    )


# Alias por compatibilidad (si en algún archivo antiguo aún importan el underscore)
_maybe_send_recordatorio_pendientes = maybe_send_recordatorio_pendientes


def hk_check_reminder(from_phone: str) -> None:
    """
    Para scheduler/cron en producción.
    """
    from .state_simple import get_user_state
    state = get_user_state(from_phone)
    maybe_send_recordatorio_pendientes(from_phone, state)
