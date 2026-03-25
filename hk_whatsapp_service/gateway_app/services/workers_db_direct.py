# gateway_app/services/workers_db_direct.py
"""
Acceso directo a Neon via psycopg para tablas de estado interno del bot.

Solo debe contener:
  - runtime_sessions  (estado de conversación por teléfono)
  - runtime_wamids    (deduplicación de mensajes WA)

No agregar queries de negocio aquí. Todo lo de negocio va via NestJS.
"""
from __future__ import annotations

import logging
from typing import Dict, List

logger = logging.getLogger(__name__)


def obtener_runtime_sessions_por_telefonos(
    phones: List[str],
) -> Dict[str, Dict]:
    """
    Devuelve phone -> {pausada, ocupada} desde el store in-memory.
    Nunca debe romper la app: si falla, devuelve {}.
    """
    phones = [str(p).strip() for p in (phones or []) if p]
    if not phones:
        return {}

    try:
        from gateway_app.services.runtime_state import _sessions
        return {
            phone: {
                "pausada": bool(_sessions[phone].get("pausada", False)),
                "ocupada": bool(_sessions[phone].get("ocupada", False)),
            }
            for phone in phones
            if phone in _sessions
        }
    except Exception:
        logger.exception("obtener_runtime_sessions_por_telefonos: falló, devolviendo {}")
        return {}
