"""
Utilidad para verificar horario laboral de supervisión.

Este módulo proporciona funciones simples para verificar si las notificaciones
a supervisores deben enviarse según el horario laboral establecido.
"""
from datetime import datetime, time
from zoneinfo import ZoneInfo
import logging

logger = logging.getLogger(__name__)

# ============================================================
# CONFIGURACIÓN DE ZONA HORARIA
# ============================================================
# Zona horaria del hotel (Chile usa "America/Santiago")
# Para otros países:
#   - Alemania: "Europe/Berlin"
#   - México: "America/Mexico_City"
#   - Argentina: "America/Argentina/Buenos_Aires"
#   - España: "Europe/Madrid"
TIMEZONE = ZoneInfo("America/Santiago")

# Horario laboral: 7:30 AM - 11:30 PM (en hora local del hotel)
HORARIO_INICIO = time(20, 30)
HORARIO_FIN = time(23, 30)


def esta_en_horario_laboral() -> bool:
    """
    Verifica si la hora actual está dentro del horario laboral.
    
    Usa la zona horaria configurada en TIMEZONE para determinar la hora local.
    
    Returns:
        bool: True si está en horario (7:30 AM - 11:30 PM hora local), False en caso contrario
    
    Example:
        >>> esta_en_horario_laboral()  # Si son las 10:00 AM en Chile
        True
        >>> esta_en_horario_laboral()  # Si son las 2:00 AM en Chile
        False
    """
    # Obtener hora actual en la zona horaria del hotel
    ahora_local = datetime.now(TIMEZONE)
    hora_actual = ahora_local.time()
    
    en_horario = HORARIO_INICIO <= hora_actual <= HORARIO_FIN
    
    logger.debug(
        f"⏰ Horario check: {hora_actual.strftime('%H:%M')} {TIMEZONE} | "
        f"Laboral: {HORARIO_INICIO.strftime('%H:%M')}-{HORARIO_FIN.strftime('%H:%M')} | "
        f"En horario: {en_horario}"
    )
    
    return en_horario


def obtener_mensaje_fuera_horario() -> str:
    """
    Retorna mensaje informativo cuando se crea un ticket fuera de horario.
    
    Returns:
        str: Mensaje explicativo para el usuario
    """
    return (
        "🌙 Registro recibido fuera de horario laboral\n\n"
        "⏰ Horario de atención: 7:30 AM - 11:30 PM\n\n"
        "✅ Tu solicitud ha sido guardada y será atendida "
        "a primera hora del día siguiente.\n\n"
        "🚨 Si es una emergencia, contacta recepción."
    )