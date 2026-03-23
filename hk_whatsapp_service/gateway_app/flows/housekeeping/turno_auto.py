# gateway_app/flows/housekeeping/turno_auto.py
"""
Módulo para activación automática de turno.

REGLA: Si el worker tiene turno inactivo y envía CUALQUIER mensaje,
el turno se activa automáticamente. No depende del recordatorio matutino.
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)

TIMEZONE = ZoneInfo("America/Santiago")


def verificar_y_activar_turno_auto(from_phone: str, state: dict, tenant=None) -> Optional[str]:
    """
    Verifica si el worker debe activar turno automáticamente y lo hace.

    Condiciones (simplificadas):
    1. El turno NO está activo
    2. El worker existe en BD y está activo

    Ya NO depende de recordatorio matutino. Cualquier mensaje con turno
    inactivo dispara la activación.

    Args:
        from_phone: Teléfono del worker
        state: Estado actual del usuario (se modifica in-place)

    Returns:
        Mensaje de confirmación si se activó, None si no aplica
    """
    from gateway_app.services.workers_db import (
        buscar_worker_por_telefono,
        activar_turno_por_telefono,
    )

    logger.info(f"🔍 TURNO_AUTO check para {from_phone}")
    logger.info(f"🔍 TURNO_AUTO turno_activo={state.get('turno_activo')}")

    # 1. Ya tiene turno activo → nada que hacer
    if state.get("turno_activo", False):
        logger.info("🔍 TURNO_AUTO: Ya tiene turno activo → skip")
        return None

    # 2. Verificar que sea un worker registrado y activo
    _property_id = tenant.property_id if tenant else ""
    worker = buscar_worker_por_telefono(from_phone, property_id=_property_id)
    if not worker:
        logger.warning("⚠️ TURNO_AUTO: Worker no encontrado → skip")
        return None

    # ✅ ACTIVAR TURNO AUTOMÁTICAMENTE
    logger.info(f"🟢 TURNO_AUTO: Activando turno para {from_phone}")

    try:
        ok = activar_turno_por_telefono(from_phone, property_id=_property_id)
        if not ok:
            logger.error("❌ TURNO_AUTO: activar_turno_por_telefono retornó False")
            return None
        logger.info("✅ TURNO_AUTO: BD actualizada")
    except Exception as e:
        logger.exception(f"❌ TURNO_AUTO: Error BD: {e}")
        return None

    # Actualizar estado local (in-place para que el orquestador lo vea)
    state["turno_activo"] = True
    state["turno_inicio"] = datetime.now(TIMEZONE).isoformat()
    state["turno_auto_activado"] = True

    # Limpiar flags de recordatorio (ya no son necesarios para la lógica,
    # pero los limpiamos para no acumular basura en el state)
    state.pop("recordatorio_matutino_fecha", None)
    state.pop("respondio_recordatorio_hoy", None)

    logger.info(f"✅ TURNO_AUTO: Turno activado exitosamente para {from_phone}")

    # Construir mensaje
    nombre = worker.get("nombre_completo", worker.get("nombre", ""))
    primer_nombre = nombre.split()[0] if nombre else ""

    mensaje = (
        f"🟢 ¡Turno activado{', ' + primer_nombre if primer_nombre else ''}!\n\n"
        "✅ Ya puedes recibir y gestionar tareas.\n\n"
        "💡 Escribe 'M' para ver el menú\n"
        "💡 Escribe 'terminar turno' al finalizar"
    )

    return mensaje