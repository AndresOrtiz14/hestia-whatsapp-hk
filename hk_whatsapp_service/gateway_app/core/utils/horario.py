"""
Utilidad para verificar horario laboral de supervisión.

Este módulo proporciona funciones simples para verificar si las notificaciones
a supervisores deben enviarse según el horario laboral establecido.
"""
from datetime import datetime, time
import logging

logger = logging.getLogger(__name__)

# Horario laboral: 7:30 AM - 11:30 PM
HORARIO_INICIO = time(7, 30)
HORARIO_FIN = time(23, 30)


def esta_en_horario_laboral() -> bool:
    """
    Verifica si la hora actual está dentro del horario laboral.
    
    Returns:
        bool: True si está en horario (7:30 AM - 11:30 PM), False en caso contrario
    
    Example:
        >>> esta_en_horario_laboral()  # Si son las 10:00 AM
        True
        >>> esta_en_horario_laboral()  # Si son las 2:00 AM
        False
    """
    ahora = datetime.now()
    hora_actual = ahora.time()
    
    en_horario = HORARIO_INICIO <= hora_actual <= HORARIO_FIN
    
    logger.debug(
        f"⏰ Horario check: {hora_actual.strftime('%H:%M')} | "
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