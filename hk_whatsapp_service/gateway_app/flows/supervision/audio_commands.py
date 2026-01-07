"""
Procesamiento de comandos de audio para supervisión.
Detecta intenciones en transcripciones de voz.
"""

import re
from typing import Dict, Any, Optional, Tuple


def extract_ticket_id(text: str) -> Optional[int]:
    """
    Extrae ID de ticket del texto.
    
    Args:
        text: Texto transcrito
    
    Returns:
        ID del ticket o None
    
    Ejemplos:
        "ticket 1503" -> 1503
        "el 1504" -> 1504
        "número 1505" -> 1505
        "asignar el 1503" -> 1503
    """
    # Buscar patrones como "ticket 1503", "1503", "el 1503", "asignar el 1503"
    patterns = [
        r'ticket\s*#?\s*(\d+)',
        r'número\s*#?\s*(\d+)',
        r'el\s+#?(\d+)',
        r'la\s+#?(\d+)',
        r'asignar\s+(?:el\s+|la\s+)?#?(\d{3,4})',
        r'derivar\s+(?:el\s+|la\s+)?#?(\d{3,4})',
        r'mandar\s+(?:el\s+|la\s+)?#?(\d{3,4})',
        r'#(\d{3,4})',  # Solo #1503
        r'\b(\d{4})\b',  # 4 dígitos solos
    ]
    
    text_lower = text.lower()
    
    for pattern in patterns:
        match = re.search(pattern, text_lower)
        if match:
            return int(match.group(1))
    
    return None


def extract_mucama_name(text: str) -> Optional[str]:
    """
    Extrae nombre de mucama del texto.
    
    Args:
        text: Texto transcrito
    
    Returns:
        Nombre de la mucama o None
    """
    # Nombres comunes (expandir según tus mucamas)
    nombres = [
        'maría', 'maria', 
        'pedro', 
        'ana', 
        'daniela',
        'carlos',
        'juan', 
        'carmen', 
        'rosa', 
        'luis',
        'carla',
        'diego',
        'sofia', 'sofía',
        'fernando',
        'patricia',
        'jorge',
        'valeria',
        'gabriel',
        'camila',
        'ricardo'
    ]
    
    text_lower = text.lower()
    
    for nombre in nombres:
        # Buscar palabra completa (evitar "maría" en "mariano")
        if re.search(r'\b' + re.escape(nombre) + r'\b', text_lower):
            # Retornar capitalizado
            return nombre.capitalize()
    
    return None


def extract_habitacion(text: str) -> Optional[str]:
    """
    Extrae número de habitación del texto.
    
    Args:
        text: Texto transcrito
    
    Returns:
        Número de habitación o None
    
    Ejemplos:
        "habitación 305" -> "305"
        "cuarto 420" -> "420"
        "la 210" -> "210"
    """
    patterns = [
        r'habitación\s*(\d{3,4})',
        r'cuarto\s*(\d{3,4})',
        r'pieza\s*(\d{3,4})',
        r'la\s+(\d{3,4})',
        r'número\s+(\d{3,4})',
    ]
    
    text_lower = text.lower()
    
    for pattern in patterns:
        match = re.search(pattern, text_lower)
        if match:
            return match.group(1)
    
    return None


def detect_priority(text: str) -> str:
    """
    Detecta la prioridad en el texto.
    
    Args:
        text: Texto transcrito
    
    Returns:
        "ALTA", "MEDIA" o "BAJA"
    """
    text_lower = text.lower()
    
    # Palabras que indican alta prioridad
    alta = ['urgente', 'ya', 'ahora', 'rápido', 'inmediato', 'emergencia']
    if any(word in text_lower for word in alta):
        return "ALTA"
    
    # Palabras que indican baja prioridad
    baja = ['cuando puedas', 'no urgente', 'después', 'más tarde']
    if any(word in text_lower for word in baja):
        return "BAJA"
    
    return "MEDIA"


def detect_audio_intent(text: str) -> Dict[str, Any]:
    """
    Detecta la intención principal del audio.
    
    Args:
        text: Texto transcrito
    
    Returns:
        Dict con tipo de intención y parámetros extraídos
    
    Tipos de intención:
        - "asignar_ticket": Asignar ticket existente
        - "crear_ticket": Crear nuevo ticket
        - "crear_y_asignar": Crear y asignar en un solo comando
        - "ver_estado": Ver tickets o mucamas
        - "unknown": No se detectó intención clara
    """
    text_lower = text.lower()
    
    # Extraer componentes
    ticket_id = extract_ticket_id(text)
    mucama = extract_mucama_name(text)
    habitacion = extract_habitacion(text)
    prioridad = detect_priority(text)
    
    # Detectar verbos de acción
    es_asignar = any(word in text_lower for word in ['asignar', 'asigna', 'derivar', 'deriva', 'mandar', 'enviar'])
    es_crear = any(word in text_lower for word in ['crear', 'nuevo', 'generar', 'registrar'])
    
    # Patrón 1: "Asignar ticket 1503 a María"
    if es_asignar and ticket_id and mucama:
        return {
            "intent": "asignar_ticket",
            "ticket_id": ticket_id,
            "mucama": mucama,
            "text": text
        }
    
    # Patrón 2: "Habitación 420 limpieza urgente asignar a Pedro"
    if habitacion and es_asignar and mucama:
        # Extraer detalle (todo excepto habitación, asignar y nombre)
        detalle = text_lower
        detalle = re.sub(r'habitación\s*\d+', '', detalle)
        detalle = re.sub(r'cuarto\s*\d+', '', detalle)
        detalle = re.sub(r'asignar.*', '', detalle)
        detalle = re.sub(r'derivar.*', '', detalle)
        detalle = detalle.strip()
        
        return {
            "intent": "crear_y_asignar",
            "habitacion": habitacion,
            "detalle": detalle if detalle else "Solicitud de housekeeping",
            "prioridad": prioridad,
            "mucama": mucama,
            "text": text
        }
    
    # Patrón 3: "Habitación 305 necesita toallas" (solo crear)
    if habitacion and not es_asignar:
        detalle = text_lower
        detalle = re.sub(r'habitación\s*\d+', '', detalle)
        detalle = re.sub(r'cuarto\s*\d+', '', detalle)
        detalle = detalle.strip()
        
        return {
            "intent": "crear_ticket",
            "habitacion": habitacion,
            "detalle": detalle if detalle else "Solicitud de housekeeping",
            "prioridad": prioridad,
            "text": text
        }
    
    # Patrón 4: Solo asignar (sin especificar ticket)
    if es_asignar and mucama and not ticket_id:
        return {
            "intent": "asignar_sin_ticket",
            "mucama": mucama,
            "text": text
        }
    
    # Patrón 5: Ver estado
    if any(word in text_lower for word in ['ver', 'muestra', 'mostrar', 'estado', 'cómo van']):
        if 'pendiente' in text_lower:
            return {"intent": "ver_pendientes", "text": text}
        if 'progreso' in text_lower:
            return {"intent": "ver_progreso", "text": text}
        if 'mucama' in text_lower:
            return {"intent": "ver_mucamas", "text": text}
    
    # No se detectó intención clara
    return {
        "intent": "unknown",
        "text": text,
        "components": {
            "ticket_id": ticket_id,
            "mucama": mucama,
            "habitacion": habitacion,
            "prioridad": prioridad
        }
    }