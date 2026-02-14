# gateway_app/flows/housekeeping/state_simple.py
"""
Housekeeping runtime state.

Now persisted in DB (public.runtime_sessions) to survive multi-worker gunicorn and restarts.
"""

from __future__ import annotations

from typing import Any, Dict

from gateway_app.services.runtime_state import load_runtime_session, save_runtime_session

import logging
import json

logger = logging.getLogger(__name__)


# Estados principales
MENU = "MENU"
VIENDO_TICKETS = "VIENDO_TICKETS"
TRABAJANDO = "TRABAJANDO"
REPORTANDO_HAB = "REPORTANDO_HAB"
REPORTANDO_DETALLE = "REPORTANDO_DETALLE"
CONFIRMANDO_REPORTE = "CONFIRMANDO_REPORTE"

# Cache in-process (best-effort). Source of truth is DB.
_STATE_CACHE: Dict[str, Dict[str, Any]] = {}


def _default_state() -> Dict[str, Any]:
    return {
        "state": MENU,
        "ticket_activo": None,
        "ticket_draft": {
            "habitacion": None,
            "detalle": None,
            "prioridad": None,
        },
        "last_greet_date": None,
        # Sistema de turnos
        "turno_activo": False,
        "turno_inicio": None,
        "turno_fin": None,
    }

def _brief_state(state: Dict[str, Any]) -> str:
    ticket_activo = state.get("ticket_activo")
    ticket_activo_id = None
    if isinstance(ticket_activo, dict):
        ticket_activo_id = ticket_activo.get("id")

    draft = state.get("ticket_draft") or {}
    if not isinstance(draft, dict):
        draft = {}

    return json.dumps(
        {
            "state": state.get("state"),
            "ticket_activo_id": ticket_activo_id,
            "draft_habitacion": draft.get("habitacion"),
            "draft_prioridad": draft.get("prioridad"),
            "last_greet_date": state.get("last_greet_date"),
        },
        ensure_ascii=False,
    )


def get_user_state(phone: str) -> Dict[str, Any]:
    """
    Load state from cache -> DB -> default.
    """
    state = load_runtime_session(phone)
    logger.info("HK_STATE get_user_state(%s) cache=%s", phone, phone in _STATE_CACHE)

    if phone in _STATE_CACHE:
        logger.info("HK_STATE cache_hit(%s) %s", phone, _brief_state(_STATE_CACHE[phone]))
        return _STATE_CACHE[phone]

    state = load_runtime_session(phone)
    logger.info("HK_STATE loaded_from_db(%s) is_none=%s raw_type=%s", phone, state is None, type(state).__name__)

    base = _default_state()

    if isinstance(state, dict):
        # Merge loaded into defaults (keeps compatibility when schema/state evolves)
        base.update(state)

        # Ensure nested structures exist
        if not isinstance(base.get("ticket_draft"), dict):
            base["ticket_draft"] = _default_state()["ticket_draft"]

    _STATE_CACHE[phone] = base

    # If DB had no state, persist the default immediately
    if state is None:
        logger.info("HK_STATE no_db_state(%s) -> persisting default %s", phone, _brief_state(base))
        save_runtime_session(phone, base)

    logger.info("HK_STATE final(%s) %s", phone, _brief_state(base))
    return base


def persist_user_state(phone: str, state: Dict[str, Any]) -> None:
    """
    Save full state to DB.
    """
    _STATE_CACHE[phone] = state
    save_runtime_session(phone, state)


def reset_ticket_draft(phone: str) -> None:
    state = get_user_state(phone)
    state["ticket_draft"] = {
        "habitacion": None,
        "detalle": None,
        "prioridad": None,
    }
