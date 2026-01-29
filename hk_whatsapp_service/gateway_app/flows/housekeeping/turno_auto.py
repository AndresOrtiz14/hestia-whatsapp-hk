# gateway_app/flows/housekeeping/turno_auto.py
"""
Módulo para activación automática de turno.

Se activa cuando el worker responde al recordatorio matutino (7:30 AM).
Cualquier mensaje activa el turno sin necesidad de comandos específicos.
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
    
    Se activa cuando:
    1. El turno NO está activo actualmente
    2. Se envió recordatorio matutino HOY (recordatorio_matutino_fecha == hoy)
    3. No ha respondido aún (respondio_recordatorio_hoy == False)
    
    Args:
        from_phone: Teléfono del worker
        state: Estado actual del usuario (se modifica in-place)
    
    Returns:
        Mensaje de confirmación si se activó, None si no era necesario
    """
    from gateway_app.services.workers_db import (
        obtener_worker_por_telefono,
        actualizar_turno_worker
    )
    
    logger.info(f"🔍 TURNO_AUTO: Verificando para {from_phone}")
    logger.info(f"🔍 TURNO_AUTO: State actual = {state}")
    
    # 1. Ya tiene turno activo?
    if state.get("turno_activo", False):
        logger.info(f"🔍 TURNO_AUTO: Ya tiene turno activo, skip")
        return None
    
    # 2. Verificar si recibió recordatorio matutino HOY
    fecha_recordatorio = state.get("recordatorio_matutino_fecha")
    hoy = datetime.now(TIMEZONE).date().isoformat()
    
    logger.info(f"🔍 TURNO_AUTO: fecha_recordatorio={fecha_recordatorio}, hoy={hoy}")
    
    if fecha_recordatorio != hoy:
        logger.info(f"🔍 TURNO_AUTO: No recibió recordatorio hoy, skip")
        return None
    
    # 3. Verificar si ya respondió hoy
    if state.get("respondio_recordatorio_hoy", False):
        logger.info(f"🔍 TURNO_AUTO: Ya respondió hoy, skip")
        return None
    
    # 4. Verificar que sea un worker registrado
    worker = obtener_worker_por_telefono(from_phone)
    if not worker:
        logger.warning(f"⚠️ TURNO_AUTO: Worker no encontrado para {from_phone}")
        return None
    
    # ✅ ACTIVAR TURNO AUTOMÁTICAMENTE
    logger.info(f"🟢 TURNO_AUTO: Activando turno para {from_phone}")
    
    try:
        # Actualizar en BD
        actualizar_turno_worker(from_phone, True)
    except Exception as e:
        logger.error(f"❌ TURNO_AUTO: Error actualizando BD: {e}")
        return None
    
    # Actualizar estado local (se persistirá al final del handler)
    state["turno_activo"] = True
    state["turno_inicio"] = datetime.now(TIMEZONE).isoformat()
    state["respondio_recordatorio_hoy"] = True
    state["turno_auto_activado"] = True  # Flag para evitar mensajes duplicados
    
    # Limpiar flag de recordatorio
    if "recordatorio_matutino_fecha" in state:
        del state["recordatorio_matutino_fecha"]
    
    logger.info(f"✅ TURNO_AUTO: Turno activado para {from_phone}")
    
    # Construir mensaje de confirmación
    nombre = worker.get("nombre_completo", worker.get("nombre", ""))
    primer_nombre = nombre.split()[0] if nombre else ""
    
    mensaje = (
        f"🟢 ¡Turno activado{', ' + primer_nombre if primer_nombre else ''}!\n\n"
        "✅ Ya puedes recibir y gestionar tareas.\n\n"
        "💡 Escribe 'M' para ver el menú completo\n"
        "💡 Escribe 'terminar turno' al finalizar tu jornada"
    )
    
    return mensaje