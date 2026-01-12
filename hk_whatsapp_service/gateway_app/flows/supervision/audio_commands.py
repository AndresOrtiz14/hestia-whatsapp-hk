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


def extract_worker_name(text: str) -> Optional[str]:
    """
    Extrae nombre de worker del texto.
    Detecta patrones: "a María", "para Pedro", nombres sueltos
    
    Args:
        text: Texto transcrito
    
    Returns:
        Nombre de la worker o None
    """
    # Nombres comunes (expandir según tus trabajadores)
    nombres = [
        'maría', 'maria', 
        'pedro', 
        'ana', 
        'daniela',
        'carlos',
        'josé', 'jose',
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
        'ricardo',
        'roberto',
        'beto'
    ]
    
    text_lower = text.lower()
    
    # NUEVO: Detectar múltiples patrones de asignación
    patrones = [
        r'\b(?:a|para)\s+(\w+)',                    # "a María", "para Pedro"
        r'que\s+lo\s+(?:resuelva|haga|vea)\s+(\w+)', # "que lo resuelva María"
        r'que\s+la\s+(?:resuelva|haga|vea)\s+(\w+)', # "que la resuelva María"
        r'(?:encarga|delega)(?:le)?\s+a\s+(\w+)',   # "encargale a Pedro"
    ]
    
    for patron in patrones:
        match = re.search(patron, text_lower)
        if match:
            posible_nombre = match.group(1)
            if posible_nombre in nombres:
                return posible_nombre.capitalize()
            # Buscar en texto original (capitalizado)
            for palabra in text.split():
                if palabra.lower() == posible_nombre and len(palabra) >= 3:
                    return palabra
    
    # Buscar nombre completo como palabra
    for nombre in nombres:
        # Buscar palabra completa (evitar "maría" en "mariano")
        if re.search(r'\b' + re.escape(nombre) + r'\b', text_lower):
            # Retornar capitalizado
            return nombre.capitalize()
    
    # Fallback: buscar cualquier palabra que parezca nombre (>=3 letras, capitalizada en original)
    # Útil para nombres no en la lista
    palabras = text.split()
    for palabra in palabras:
        # Si la palabra original estaba capitalizada y tiene >=3 letras
        if palabra and len(palabra) >= 3 and palabra[0].isupper():
            # Verificar que no sea una palabra común
            palabras_comunes = ['Hab', 'Habitación', 'Cuarto', 'Ticket', 'El', 'La', 'Un', 'Una', 'Pieza']
            if palabra not in palabras_comunes:
                return palabra
    
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
        - "ver_estado": Ver tickets o workers
        - "unknown": No se detectó intención clara
    """
    text_lower = text.lower()
    
    # Extraer componentes
    ticket_id = extract_ticket_id(text)
    worker = extract_worker_name(text)
    habitacion = extract_habitacion(text)
    prioridad = detect_priority(text)
    
    # Detectar verbos de acción (con tolerancia a errores de transcripción)
    es_asignar = any(word in text_lower for word in [
        'asignar', 'asigna', 'asina',  # ← typo común de Whisper
        'derivar', 'deriva', 
        'mandar', 'manda',
        'enviar', 'envia',
        'encargar', 'encarga', 'encargale', 'encárgale',  # NUEVO
        'delegar', 'delega', 'delegale', 'delégale',      # NUEVO
        'que lo resuelva', 'que lo haga', 'que lo vea',   # NUEVO
        'que la resuelva', 'que la haga', 'que la vea'    # NUEVO
    ])
    es_reasignar = any(word in text_lower for word in [
        'reasignar', 'reasigna',
        'cambiar', 'cambia',
        'mover', 'mueve'
    ])
    es_crear = any(word in text_lower for word in ['crear', 'nuevo', 'generar', 'registrar'])
    
    # Patrón 0: "Reasignar ticket 1503 a María" (NUEVO)
    if es_reasignar and ticket_id and worker:
        return {
            "intent": "reasignar_ticket",
            "ticket_id": ticket_id,
            "worker": worker,
            "text": text
        }
    
    # Patrón 1: "Asignar ticket 1503 a María"
    # IMPORTANTE: Solo si NO hay contexto de habitación
    if es_asignar and ticket_id and worker:
        # Verificar si es habitación (tiene palabras como "la", "hab", "habitación")
        tiene_contexto_habitacion = any(word in text.lower() for word in [
            'la ', 'el ', 'hab ', 'habitacion', 'habitación', 'cuarto', 'pieza'
        ])
        
        if tiene_contexto_habitacion:
            # Es habitación, no ticket ID - continuar a siguiente patrón
            pass
        else:
            # Es ticket ID real
            return {
                "intent": "asignar_ticket",
                "ticket_id": ticket_id,
                "worker": worker,
                "text": text
            }
    
    # Patrón 2: "Habitación 420 limpieza urgente asignar a Pedro"
    if habitacion and es_asignar and worker:
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
            "worker": worker,
            "text": text
        }
    
    # Patrón 3: "Habitación 305 necesita toallas" o "Hab 1302 faltan toallas. A Daniela"
    if habitacion:
        # Extraer detalle limpiando la habitación y comandos
        detalle = text_lower
        detalle = re.sub(r'habitación\s*\d+', '', detalle)
        detalle = re.sub(r'cuarto\s*\d+', '', detalle)
        detalle = re.sub(r'pieza\s*\d+', '', detalle)
        detalle = re.sub(r'hab\s*\d+', '', detalle)
        
        # Si hay nombre después de "a [nombre]", extraerlo y limpiar
        if worker:
            # Limpiar el nombre del detalle
            detalle = re.sub(r'\s*\.?\s*a\s+\w+\s*$', '', detalle, flags=re.IGNORECASE)
            detalle = re.sub(r'\s*para\s+\w+\s*$', '', detalle, flags=re.IGNORECASE)
            detalle = re.sub(r'\s*\.?\s*que\s+lo\s+(?:resuelva|haga|vea)\s+\w+\s*$', '', detalle, flags=re.IGNORECASE)
            detalle = re.sub(r'\s*\.?\s*que\s+la\s+(?:resuelva|haga|vea)\s+\w+\s*$', '', detalle, flags=re.IGNORECASE)
            detalle = re.sub(r'\s*\.?\s*(?:encarga|delega)(?:le)?\s+a\s+\w+\s*$', '', detalle, flags=re.IGNORECASE)
            detalle = re.sub(r'\s*\.?\s*(?:encárgale|delégale)\s+a\s+\w+\s*$', '', detalle, flags=re.IGNORECASE)
            
            # Si hay "asignar" o similar, es crear_y_asignar
            if es_asignar or es_reasignar:
                detalle = re.sub(r'asignar.*', '', detalle)
                detalle = re.sub(r'derivar.*', '', detalle)
                detalle = re.sub(r'cambiar.*', '', detalle)
                detalle = detalle.strip()
                
                return {
                    "intent": "crear_y_asignar",
                    "habitacion": habitacion,
                    "detalle": detalle if detalle else "Solicitud de operaciones",
                    "prioridad": prioridad,
                    "worker": worker,
                    "text": text
                }
            else:
                # No hay verbo explícito pero hay "a [nombre]" → crear_y_asignar
                detalle = detalle.strip()
                return {
                    "intent": "crear_y_asignar",
                    "habitacion": habitacion,
                    "detalle": detalle if detalle else "Solicitud de operaciones",
                    "prioridad": prioridad,
                    "worker": worker,
                    "text": text
                }
        else:
            # No hay nombre: solo crear ticket
            detalle = detalle.strip()
            return {
                "intent": "crear_ticket",
                "habitacion": habitacion,
                "detalle": detalle if detalle else "Solicitud de operaciones",
                "prioridad": prioridad,
                "text": text
            }
    
    # Patrón 4: Solo asignar (sin especificar ticket)
    if es_asignar and worker and not ticket_id:
        return {
            "intent": "asignar_sin_ticket",
            "worker": worker,
            "text": text
        }
    
    # Patrón 5: Ver estado
    if any(word in text_lower for word in ['ver', 'muestra', 'mostrar', 'estado', 'cómo van']):
        if 'pendiente' in text_lower:
            return {"intent": "ver_pendientes", "text": text}
        if 'progreso' in text_lower:
            return {"intent": "ver_progreso", "text": text}
        if 'worker' in text_lower:
            return {"intent": "ver_workers", "text": text}
    
    # No se detectó intención clara
    return {
        "intent": "unknown",
        "text": text,
        "components": {
            "ticket_id": ticket_id,
            "worker": worker,
            "habitacion": habitacion,
            "prioridad": prioridad
        }
    }