"""
Utilidad para verificar horario laboral de supervisión.
"""
from datetime import datetime, time
from zoneinfo import ZoneInfo
import logging

logger = logging.getLogger(__name__)

# Zona horaria de Chile
TIMEZONE = ZoneInfo("America/Santiago")

# Horario laboral (para testing: 4:30 PM - 11:30 PM)
HORARIO_INICIO = time(7, 30)
HORARIO_FIN = time(23, 30)


def esta_en_horario_laboral() -> bool:
    """Verifica si está en horario laboral (hora de Chile)."""
    # ✅ USAR TIMEZONE
    ahora_local = datetime.now(TIMEZONE)
    hora_actual = ahora_local.time()
    
    en_horario = HORARIO_INICIO <= hora_actual <= HORARIO_FIN
    
    logger.info(
        f"⏰ Check: {hora_actual.strftime('%H:%M')} Chile | "
        f"Rango: {HORARIO_INICIO.strftime('%H:%M')}-{HORARIO_FIN.strftime('%H:%M')} | "
        f"{'✅ EN' if en_horario else '🌙 FUERA'}"
    )
    
    return en_horario


def obtener_mensaje_fuera_horario() -> str:
    """Mensaje informativo fuera de horario."""
    return (
        "🌙 Registro recibido fuera de horario laboral\n\n"
        "⏰ Horario de atención: 7:30 AM - 11:30 PM\n\n"
        "✅ Tu solicitud ha sido guardada y será atendida "
        "a primera hora del día siguiente.\n\n"
        "🚨 Si es una emergencia, contacta recepción."
    )