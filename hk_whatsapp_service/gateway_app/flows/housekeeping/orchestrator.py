"""
Orquestador principal del flujo de Housekeeping.
Punto de entrada único para todos los mensajes entrantes.
"""

from datetime import date
from typing import Dict, Any

from .state import get_user_state
from .outgoing import send_whatsapp
from .ui import texto_menu_principal
from .menu_flow import handle_menu
from .ticket_flow import _handle_ticket_flow
from .reminders import maybe_send_recordatorio_pendientes

def maybe_route_ticket_command_anywhere(phone: str, text: str, state: Dict[str, Any]) -> bool:
    """
    Permite manejar comandos del ticket activo desde cualquier parte del flujo.
    
    Si hay ticket_activo, y llega un comando tipo 'fin/pausar/reanudar/supervisor',
    forzamos ticket_state = 'S1' y delegamos en _handle_ticket_flow.
    
    Returns:
        True si el comando fue manejado, False en caso contrario.
    """
    if state.get("ticket_activo") is None:
        return False

    t = (text or "").strip().lower()
    if t in {"fin", "terminar", "cerrar", "pausar", "reanudar", "supervisor"}:
        # Aseguramos que el ticket_flow lo procese como ejecución (S1)
        state["ticket_state"] = "S1"
        _handle_ticket_flow(phone, text, state)
        return True

    return False


def handle_hk_message(from_phone: str, text: str) -> None:
    """
    Punto de entrada único para:
    - Simulador CLI
    - Webhook (producción)

    Orquesta:
    - Saludo 1 vez al día
    - Ticket flow (S0/S1/S2) si hay ticket activo
    - Menú (M0/M1/M2/M3) si no hay ticket activo
    - Recordatorios opcionales
    
    Args:
        from_phone: Número de teléfono de la mucama
        text: Texto del mensaje recibido
    """
    state = get_user_state(from_phone)
    raw = (text or "").strip()

    # 0) Comandos globales del ticket activo (desde cualquier parte)
    if maybe_route_ticket_command_anywhere(from_phone, raw, state):
        return

    today_str = date.today().isoformat()

    # Saludo solo si NO hay ticket activo (ni conversacional ni en ejecución)
    if (
        state.get("ticket_state") is None
        and state.get("ticket_activo") is None
        and state.get("last_greet_date") != today_str
    ):
        state["last_greet_date"] = today_str
        send_whatsapp(
            from_phone,
            "Hola, soy el asistente de Housekeeping de Hestia.\n"
            "Te ayudaré a organizar y resolver tus tareas de hoy.\n\n"
            + texto_menu_principal(state)
        )
        return

    # 1) Si hay un flujo de ticket activo, tiene prioridad
    if state.get("ticket_state") is not None:
        _handle_ticket_flow(from_phone, raw, state)
        return

    # 2) Si no hay ticket activo, manejamos menú
    handle_menu(from_phone, raw, state)

    # 3) Recordatorio opcional (solo aplica si corresponde)
    # No enviar recordatorio si acabamos de iniciar turno
    if not state.get("_just_started_shift"):
        maybe_send_recordatorio_pendientes(from_phone, state)
    
    # Limpiar flag temporal después de usarlo
    if state.get("_just_started_shift"):
        state["_just_started_shift"] = False


# Alias por compatibilidad (por si algún módulo aún usa este nombre)
_handle_hk_message = handle_hk_message