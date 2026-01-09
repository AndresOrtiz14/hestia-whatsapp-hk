# gateway_app/flows/supervision/state.py
"""
Supervisor runtime state.

Now persisted in DB (public.runtime_sessions) to survive multi-worker gunicorn and restarts.
"""

from __future__ import annotations

from typing import Any, Dict

from gateway_app.services.runtime_state import load_runtime_session, save_runtime_session

# Cache in-process (best-effort). Source of truth is DB.
_STATE_CACHE: Dict[str, Dict[str, Any]] = {}


def _default_supervisor_state(phone: str) -> Dict[str, Any]:
    return {
        "phone": phone,
        "nombre": None,
        "rol": "supervisor",

        # Menu / selection fields (legacy + simple orchestrator fields)
        "menu_state": None,
        "ticket_seleccionado": None,
        "mucama_seleccionada": None,

        # Simple orchestrator flags/objects used in your current code
        "esperando_asignacion": False,
        "confirmacion_pendiente": None,
        "seleccion_mucamas": None,

        # Ticket creation draft (if used later)
        "ticket_en_creacion": {
            "habitacion": None,
            "detalle": None,
            "prioridad": None,
        },

        "last_greet_date": None,
    }


def get_supervisor_state(phone: str) -> Dict[str, Any]:
    if phone in _STATE_CACHE:
        return _STATE_CACHE[phone]

    loaded = load_runtime_session(phone)
    base = _default_supervisor_state(phone)

    if isinstance(loaded, dict):
        base.update(loaded)
        if not isinstance(base.get("ticket_en_creacion"), dict):
            base["ticket_en_creacion"] = _default_supervisor_state(phone)["ticket_en_creacion"]

    _STATE_CACHE[phone] = base

    if loaded is None:
        save_runtime_session(phone, base)

    return base


def persist_supervisor_state(phone: str, state: Dict[str, Any]) -> None:
    _STATE_CACHE[phone] = state
    save_runtime_session(phone, state)


def reset_supervisor_selection(phone: str) -> None:
    state = get_supervisor_state(phone)
    state["ticket_seleccionado"] = None
    state["mucama_seleccionada"] = None


def reset_ticket_creation(phone: str) -> None:
    state = get_supervisor_state(phone)
    state["ticket_en_creacion"] = {
        "habitacion": None,
        "detalle": None,
        "prioridad": None,
    }


def clear_supervisor_state(phone: str) -> None:
    if phone in _STATE_CACHE:
        del _STATE_CACHE[phone]
    # Optional: if you need a DB delete later, add it explicitly when required.
