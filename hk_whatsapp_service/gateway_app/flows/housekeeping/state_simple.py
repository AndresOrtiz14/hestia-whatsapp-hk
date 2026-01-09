"""
Estados simplificados para bot de Housekeeping.
"""

from typing import Dict, Any

# Estados principales
MENU = "MENU"
VIENDO_TICKETS = "VIENDO_TICKETS"
TRABAJANDO = "TRABAJANDO"
REPORTANDO_HAB = "REPORTANDO_HAB"
REPORTANDO_DETALLE = "REPORTANDO_DETALLE"
CONFIRMANDO_REPORTE = "CONFIRMANDO_REPORTE"  # NUEVO

# Estado en memoria
USER_STATE: Dict[str, Dict[str, Any]] = {}


def get_user_state(phone: str) -> Dict[str, Any]:
    """
    Obtiene o inicializa el estado de un worker (trabajador).
    
    Args:
        phone: Número de teléfono
    
    Returns:
        Estado del usuario
    """
    if phone not in USER_STATE:
        USER_STATE[phone] = {
            # Estado actual
            "state": MENU,
            
            # Ticket activo
            "ticket_activo": None,  # dict con datos del ticket
            
            # Creación de ticket
            "ticket_draft": {
                "habitacion": None,
                "detalle": None,
                "prioridad": None
            },
            
            # Saludos
            "last_greet_date": None,  # str ISO fecha
        }
    return USER_STATE[phone]


def reset_ticket_draft(phone: str) -> None:
    """
    Limpia el borrador de ticket.
    
    Args:
        phone: Número de teléfono
    """
    state = get_user_state(phone)
    state["ticket_draft"] = {
        "habitacion": None,
        "detalle": None,
        "prioridad": None
    }