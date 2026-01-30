# gateway_app/flows/housekeeping/turno_auto.py
"""
Módulo para activación automática de turno.
Se activa cuando el worker responde al recordatorio matutino.
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)

TIMEZONE = ZoneInfo("America/Santiago")


def verificar_y_activar_turno_auto(from_phone: str, state: dict) -> Optional[str]:
    """
    Verifica si el worker debe activar turno automáticamente y lo hace.
    
    Condiciones:
    1. El turno NO está activo
    2. Se envió recordatorio matutino HOY
    3. No ha respondido aún hoy
    
    Args:
        from_phone: Teléfono del worker
        state: Estado actual del usuario (se modifica in-place)
    
    Returns:
        Mensaje de confirmación si se activó, None si no
    """
    from gateway_app.services.workers_db import (
        buscar_worker_por_telefono,
        activar_turno_por_telefono
    )
    
    hoy = datetime.now(TIMEZONE).date().isoformat()
    
    # Log del state actual para debugging
    logger.info(f"🔍 TURNO_AUTO check para {from_phone}")
    logger.info(f"🔍 TURNO_AUTO state keys: {list(state.keys())}")
    logger.info(f"🔍 TURNO_AUTO turno_activo={state.get('turno_activo')}")
    logger.info(f"🔍 TURNO_AUTO recordatorio_fecha={state.get('recordatorio_matutino_fecha')}")
    logger.info(f"🔍 TURNO_AUTO respondio_hoy={state.get('respondio_recordatorio_hoy')}")
    logger.info(f"🔍 TURNO_AUTO hoy={hoy}")
    
    # 1. Ya tiene turno activo?
    if state.get("turno_activo", False):
        logger.info(f"🔍 TURNO_AUTO: Ya tiene turno activo → skip")
        return None
    
    # 2. Verificar si recibió recordatorio matutino HOY
    fecha_recordatorio = state.get("recordatorio_matutino_fecha")
    
    if fecha_recordatorio != hoy:
        logger.info(f"🔍 TURNO_AUTO: No recibió recordatorio hoy ({fecha_recordatorio} != {hoy}) → skip")
        return None
    
    # 3. Verificar si ya respondió hoy
    if state.get("respondio_recordatorio_hoy", False):
        logger.info(f"🔍 TURNO_AUTO: Ya respondió hoy → skip")
        return None
    
    # 4. Verificar que sea un worker registrado
    worker = buscar_worker_por_telefono(from_phone)
    if not worker:
        logger.warning(f"⚠️ TURNO_AUTO: Worker no encontrado → skip")
        return None
    
    # ✅ ACTIVAR TURNO AUTOMÁTICAMENTE
    logger.info(f"🟢 TURNO_AUTO: ¡Activando turno para {from_phone}!")
    
    try:
        ok = activar_turno_por_telefono(from_phone)
        if not ok:
            logger.error(f"❌ TURNO_AUTO: activar_turno_por_telefono retornó False")
            return None
        logger.info(f"✅ TURNO_AUTO: BD actualizada")
    except Exception as e:
        logger.exception(f"❌ TURNO_AUTO: Error BD: {e}")
        return None
    
    # Actualizar estado local
    state["turno_activo"] = True
    state["turno_inicio"] = datetime.now(TIMEZONE).isoformat()
    state["respondio_recordatorio_hoy"] = True
    state["turno_auto_activado"] = True
    
    # Limpiar flag de recordatorio
    state.pop("recordatorio_matutino_fecha", None)
    
    logger.info(f"✅ TURNO_AUTO: Turno activado exitosamente para {from_phone}")
    logger.info(f"✅ TURNO_AUTO: State actualizado: turno_activo={state.get('turno_activo')}")
    
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