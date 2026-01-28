# gateway_app/flows/housekeeping/turno_auto.py
"""
Módulo para activación automática de turno.

Funcionalidad:
- Detecta si el worker debe activar turno automáticamente
- Se activa cuando el worker responde al recordatorio matutino (7:30 AM)
- Cualquier mensaje activa el turno sin necesidad de comandos específicos
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
    2. Se envió recordatorio matutino HOY
    3. Es la primera respuesta del día
    
    Args:
        from_phone: Teléfono del worker
        state: Estado actual del usuario
    
    Returns:
        Mensaje de confirmación si se activó, None si no era necesario
    """
    from gateway_app.services.workers_db import (
        activar_turno_por_telefono, 
        buscar_worker_por_telefono
    )
    
    # Ya tiene turno activo?
    if state.get("turno_activo", False):
        return None
    
    # Verificar que sea un worker registrado
    worker = buscar_worker_por_telefono(from_phone)
    if not worker:
        return None
    
    # Verificar si hubo recordatorio matutino hoy
    fecha_recordatorio = state.get("recordatorio_matutino_fecha")
    hoy = datetime.now(TIMEZONE).date().isoformat()
    
    # También activar si es la primera interacción del día (antes de las 7:30)
    # o si el último saludo fue de un día anterior
    last_greet = state.get("last_greet_date")
    es_primera_interaccion_dia = last_greet != hoy
    
    # Si no hubo recordatorio y no es primera interacción, no activar auto
    if fecha_recordatorio != hoy and not es_primera_interaccion_dia:
        return None
    
    # ACTIVAR TURNO AUTOMÁTICAMENTE
    ok = activar_turno_por_telefono(from_phone)
    
    if not ok:
        logger.warning(f"⚠️ No se pudo activar turno automático para {from_phone}")
        return None
    
    # Actualizar estado local
    state["turno_activo"] = True
    state["turno_inicio"] = datetime.now(TIMEZONE).isoformat()
    state["turno_auto_activado"] = True  # Flag para saber que fue automático
    
    # Limpiar flag de recordatorio
    if "recordatorio_matutino_fecha" in state:
        del state["recordatorio_matutino_fecha"]
    
    logger.info(f"✅ TURNO AUTO-ACTIVADO para {from_phone}")
    
    # Construir mensaje de confirmación
    nombre = worker.get("nombre_completo", "")
    primer_nombre = nombre.split()[0] if nombre else ""
    
    mensaje = (
        f"🟢 ¡Turno activado{', ' + primer_nombre if primer_nombre else ''}!\n\n"
        "✅ Ya puedes recibir y gestionar tareas.\n\n"
        "💡 Escribe 'M' para ver el menú completo\n"
        "💡 Escribe 'terminar turno' al finalizar tu jornada"
    )
    
    return mensaje


# ============================================================
# CÓDIGO A INTEGRAR EN orchestrator_hk_multiticket.py
# ============================================================
"""
INSTRUCCIONES DE INTEGRACIÓN:

1. Agregar al inicio de handle_hk_message_simple(), ANTES de procesar el mensaje:

```python
from gateway_app.flows.housekeeping.turno_auto import verificar_y_activar_turno_auto

def handle_hk_message_simple(from_phone: str, text: str) -> None:
    state = get_user_state(from_phone)
    
    # ✅ NUEVO: Verificar activación automática de turno
    mensaje_turno = verificar_y_activar_turno_auto(from_phone, state)
    if mensaje_turno:
        send_whatsapp(from_phone, mensaje_turno)
        # Continuar procesando el mensaje normalmente...
    
    # ... resto del código existente
```

2. Modificar verificar_turno_activo() para NO auto-iniciar si ya se hizo:

```python
def verificar_turno_activo(from_phone: str) -> bool:
    state = get_user_state(from_phone)
    
    # Si ya está activo, OK
    if state.get("turno_activo", False):
        return True
    
    # Si fue auto-activado recientemente, no mostrar mensaje duplicado
    if state.get("turno_auto_activado"):
        del state["turno_auto_activado"]  # Limpiar flag
        return True
    
    # Auto-iniciar turno (comportamiento existente)
    # ...
```
"""