"""
Manejo de estado para el bot de Supervisión.
Similar a housekeeping/state.py pero con estados específicos de supervisor.
"""

from typing import Dict, Any, Optional

# Estado global en memoria (compartido entre requests)
SUPERVISOR_STATE: Dict[str, Dict[str, Any]] = {}


def get_supervisor_state(phone: str) -> Dict[str, Any]:
    """
    Obtiene o inicializa el estado de un supervisor.
    
    Args:
        phone: Número de teléfono del supervisor
    
    Returns:
        Estado del supervisor
    """
    if phone not in SUPERVISOR_STATE:
        SUPERVISOR_STATE[phone] = {
            "phone": phone,
            "nombre": None,  # Se puede cargar de BD
            "rol": "supervisor",
            
            # Estado del menú
            "menu_state": None,  # M0, M1, M2, etc.
            
            # Selección actual
            "ticket_seleccionado": None,  # ID del ticket
            "mucama_seleccionada": None,  # Teléfono de mucama
            
            # Creación de ticket
            "ticket_en_creacion": {
                "habitacion": None,
                "detalle": None,
                "prioridad": None
            },
            
            # Saludo
            "last_greet_date": None,
        }
    
    return SUPERVISOR_STATE[phone]


def reset_supervisor_selection(phone: str) -> None:
    """
    Limpia la selección actual (ticket y mucama).
    """
    state = get_supervisor_state(phone)
    state["ticket_seleccionado"] = None
    state["mucama_seleccionada"] = None


def reset_ticket_creation(phone: str) -> None:
    """
    Limpia el ticket en creación.
    """
    state = get_supervisor_state(phone)
    state["ticket_en_creacion"] = {
        "habitacion": None,
        "detalle": None,
        "prioridad": None
    }


def clear_supervisor_state(phone: str) -> None:
    """
    Limpia completamente el estado de un supervisor.
    Útil para testing o reset manual.
    """
    if phone in SUPERVISOR_STATE:
        del SUPERVISOR_STATE[phone]


# Estados del menú (M)
MENU_PRINCIPAL = "M0"
VER_PENDIENTES = "M1"
VER_EN_PROGRESO = "M2"
VER_MUCAMAS = "M3"
CREAR_TICKET = "M4"
ESTADISTICAS = "M5"

# Estados de asignación (A)
ASIGNAR_ELIGIENDO_TICKET = "A0"
ASIGNAR_ELIGIENDO_MUCAMA = "A1"
ASIGNAR_CONFIRMANDO = "A2"

# Estados de creación (C)
CREAR_INGRESANDO_DETALLE = "C0"
CREAR_CONFIRMANDO = "C1"
CREAR_ELIGIENDO_PRIORIDAD = "C2"
CREAR_ELIGIENDO_ASIGNACION = "C3"