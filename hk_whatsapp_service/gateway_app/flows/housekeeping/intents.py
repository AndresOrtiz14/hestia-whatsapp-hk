"""
Detección de intenciones en texto/audio para housekeeping.
"""

import re
from typing import Dict, Any, Optional


def detectar_prioridad(text: str) -> str:
    """
    Detecta prioridad automáticamente por palabras clave.
    
    Args:
        text: Texto del problema
    
    Returns:
        "ALTA", "MEDIA" o "BAJA"
    """
    text_lower = text.lower()
    
    # Palabras que indican ALTA prioridad
    alta_keywords = [
        'urgente', 'ya', 'ahora', 'inmediato', 'emergencia',
        'fuga', 'inundación', 'agua', 'goteo', 'mojado',
        'roto', 'no funciona', 'dañado', 'quebrado',
        'olor', 'mal olor', 'huele',
        'bloqueado', 'tapado', 'atascado'
    ]
    
    if any(keyword in text_lower for keyword in alta_keywords):
        return "ALTA"
    
    # Palabras que indican BAJA prioridad
    baja_keywords = [
        'cuando puedas', 'después', 'más tarde', 'no urgente',
        'cuando termines', 'si puedes'
    ]
    
    if any(keyword in text_lower for keyword in baja_keywords):
        return "BAJA"
    
    # Por defecto: MEDIA
    return "MEDIA"


def extraer_habitacion(text: str) -> Optional[str]:
    """
    Extrae número de habitación del texto.
    
    Args:
        text: Texto
    
    Returns:
        Número de habitación o None
    """
    # Patrones: "hab 305", "habitación 420", "cuarto 210", "la 305"
    patterns = [
        r'hab(?:itación)?\s*(\d{3,4})',
        r'cuarto\s*(\d{3,4})',
        r'pieza\s*(\d{3,4})',
        r'la\s+(\d{3,4})',
        r'el\s+(\d{3,4})',
        r'\b(\d{3,4})\b'  # 3-4 dígitos solos
    ]
    
    text_lower = text.lower()
    
    for pattern in patterns:
        match = re.search(pattern, text_lower)
        if match:
            return match.group(1)
    
    return None


def detectar_reporte_directo(text: str) -> Optional[Dict[str, Any]]:
    """
    Detecta si el texto es un reporte directo de problema.
    
    Args:
        text: Texto del mensaje
    
    Returns:
        Dict con {habitacion, detalle, prioridad} o None
    
    Ejemplos:
        "hab 305 fuga de agua" -> {habitacion: "305", detalle: "fuga de agua", prioridad: "ALTA"}
        "habitación 210 falta toallas" -> {habitacion: "210", detalle: "falta toallas", prioridad: "MEDIA"}
    """
    habitacion = extraer_habitacion(text)
    
    if not habitacion:
        return None
    
    # Extraer detalle (quitar la mención de habitación)
    text_lower = text.lower()
    detalle = text_lower
    
    # Remover patrones de habitación
    detalle = re.sub(r'hab(?:itación)?\s*\d{3,4}', '', detalle)
    detalle = re.sub(r'cuarto\s*\d{3,4}', '', detalle)
    detalle = re.sub(r'pieza\s*\d{3,4}', '', detalle)
    detalle = re.sub(r'la\s+\d{3,4}', '', detalle)
    detalle = re.sub(r'el\s+\d{3,4}', '', detalle)
    
    detalle = detalle.strip()
    
    # Si no hay detalle, no es reporte directo
    if not detalle or len(detalle) < 3:
        return None
    
    # Detectar prioridad
    prioridad = detectar_prioridad(text)
    
    return {
        "habitacion": habitacion,
        "detalle": detalle,
        "prioridad": prioridad
    }


def es_comando_tomar(text: str) -> bool:
    """
    Detecta si quiere tomar un ticket.
    
    Args:
        text: Texto
    
    Returns:
        True si es comando de tomar
    """
    text_lower = text.lower().strip()
    
    comandos = [
        'tomar', 'tomo', 'tómalo',
        'aceptar', 'acepto', 'aceptado',
        'lo tomo', 'me lo llevo',
        'ok', 'okey', 'dale', 'listo'
    ]
    
    return any(cmd in text_lower for cmd in comandos)


def es_comando_finalizar(text: str) -> bool:
    """
    Detecta si quiere finalizar ticket.
    
    Args:
        text: Texto
    
    Returns:
        True si es comando de finalizar
    """
    text_lower = text.lower().strip()
    
    comandos = [
        'fin', 'finalizar', 'finalizr', 'finalzar',  # con typos
        'terminar', 'termianr', 'termirar',  # con typos
        'listo', 'hecho', 'completar', 'cerrar'
    ]
    
    return any(cmd in text_lower for cmd in comandos)


def es_comando_pausar(text: str) -> bool:
    """
    Detecta si quiere pausar.
    
    Args:
        text: Texto
    
    Returns:
        True si es comando de pausar
    """
    text_lower = text.lower().strip()
    return 'pausar' in text_lower or 'pausa' in text_lower


def es_comando_reanudar(text: str) -> bool:
    """
    Detecta si quiere reanudar.
    
    Args:
        text: Texto
    
    Returns:
        True si es comando de reanudar
    """
    text_lower = text.lower().strip()
    return 'reanudar' in text_lower or 'continuar' in text_lower or 'seguir' in text_lower


def es_comando_reportar(text: str) -> bool:
    """
    Detecta si quiere reportar problema.
    
    Args:
        text: Texto
    
    Returns:
        True si es comando de reportar
    """
    text_lower = text.lower().strip()
    
    comandos = [
        'reportar', 'reporte', 'reporto',
        'crear ticket', 'nuevo ticket',
        'hay un problema', 'tengo un problema'
    ]
    
    return any(cmd in text_lower for cmd in comandos)