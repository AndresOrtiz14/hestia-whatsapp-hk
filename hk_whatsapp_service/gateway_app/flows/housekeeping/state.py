
from datetime import date, datetime, timedelta
import re
import time

# =========================
#   ESTADO EN MEMORIA
# =========================

from typing import Dict, Any

USER_STATE: Dict[str, Dict[str, Any]] = {}


def get_user_state(phone: str) -> Dict[str, Any]:
    """Obtiene o inicializa el estado de una mucama."""
    if phone not in USER_STATE:
        USER_STATE[phone] = {
            # Turno
            "turno_activo": False,        # False = M0, True = M1
            "menu_state": "M0",           # "M0", "M1", "M2", "M3"
            # Flujo de tickets
            "ticket_state": None,         # None, "S0", "S1", "S2"
            "ticket_activo": None,        # dict con datos de ticket actual
            # Saludos
            "last_greet_date": None,      # str ISO con la fecha del último saludo
            # Recordatorios automáticos
            "last_reminder_ts": None,     # timestamp (float) del último recordatorio
            # Borrador de ticket en lenguaje natural
            "ticket_draft_text": None,    # str con el texto acumulado
        }
    return USER_STATE[phone]

