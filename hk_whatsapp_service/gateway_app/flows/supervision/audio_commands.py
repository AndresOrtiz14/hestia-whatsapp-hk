"""
Procesamiento de comandos de audio para supervisión.
Detecta intenciones en transcripciones de voz.
VERSIÓN CON SOPORTE PARA ÁREAS COMUNES.
"""

import re
from typing import Dict, Any, Optional, Tuple
from gateway_app.flows.housekeeping.intents import detectar_prioridad

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
        "reasignar 12 a seba" -> 12
    """
    # Buscar patrones como "ticket 1503", "1503", "el 1503", "asignar el 1503", "reasignar 12"
    patterns = [
        r'reasignar\s+(?:el\s+|la\s+)?#?(\d{1,4})',
        r'ticket\s*#?\s*(\d+)',
        r'número\s*#?\s*(\d+)',
        r'el\s+#?(\d+)',
        r'la\s+#?(\d+)',
        r'asignar\s+(?:el\s+|la\s+)?#?(\d{1,4})',
        r'derivar\s+(?:el\s+|la\s+)?#?(\d{1,4})',
        r'mandar\s+(?:el\s+|la\s+)?#?(\d{1,4})',
        r'#(\d{1,4})',
        r'\b(\d{3,4})\b',  # 3-4 dígitos solos
    ]
    
    text_lower = text.lower()
    
    for pattern in patterns:
        match = re.search(pattern, text_lower)
        if match:
            ticket_id = int(match.group(1))
            if 1 <= ticket_id <= 9999:
                return ticket_id
    
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
        'beto',
        'seba',
        'javier',
        'andres', 'andrés'
    ]
    
    text_lower = text.lower()
    
    # Detectar múltiples patrones de asignación
    patrones = [
        r'\b(?:a|para)\s+(\w+)',
        r'que\s+lo\s+(?:resuelva|haga|vea)\s+(\w+)',
        r'que\s+la\s+(?:resuelva|haga|vea)\s+(\w+)',
        r'(?:encarga|delega)(?:le)?\s+a\s+(\w+)',
    ]
    
    for patron in patrones:
        match = re.search(patron, text_lower)
        if match:
            posible_nombre = match.group(1)
            if posible_nombre in nombres:
                return posible_nombre.capitalize()
            for palabra in text.split():
                if palabra.lower() == posible_nombre and len(palabra) >= 3:
                    return palabra
    
    for nombre in nombres:
        if re.search(r'\b' + re.escape(nombre) + r'\b', text_lower):
            return nombre.capitalize()
    
    palabras = text.split()
    for palabra in palabras:
        if palabra and len(palabra) >= 3 and palabra[0].isupper():
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
        r'hab\s+(\d{3,4})',
        r'la\s+(\d{3,4})',
        r'número\s+(\d{3,4})',
    ]
    
    text_lower = text.lower()
    
    for pattern in patterns:
        match = re.search(pattern, text_lower)
        if match:
            return match.group(1)
    
    return None


def extract_area_comun(text: str) -> Optional[str]:
    """
    ✅ NUEVA FUNCIÓN: Extrae área común del texto.
    
    Áreas soportadas:
    - Ascensor (con piso opcional)
    - Cafetería / Comedor
    - Lobby / Recepción
    - Pasillo (con piso)
    - Hub, Terraza, Estacionamiento, Escalera, etc.
    
    Args:
        text: Texto transcrito
    
    Returns:
        Área formateada o None
    
    Ejemplos:
        "ascensor piso 3" -> "Ascensor Piso 3"
        "ascensor 2" -> "Ascensor Piso 2"
        "el ascensor no funciona" -> "Ascensor"
        "cafeteria" -> "Cafetería"
        "lobby" -> "Lobby"
    """
    text_lower = text.lower()
    
    # Diccionario de áreas con sus patrones y formateadores
    areas = {
        # Ascensor (detecta "ascensor", "ascensor 2", "ascensor piso 3")
        r'ascensor(?:\s+(?:del\s+)?(?:piso\s+)?(\d+))?': 
            lambda m: f"Ascensor{f' Piso {m.group(1)}' if m.group(1) else ''}",
        
        # Cafetería / Comedor
        r'cafeteria|cafetería|comedor': 
            lambda m: "Cafetería",
        
        # Lobby / Recepción
        r'lobby|recepcion|recepción|entrada|hall': 
            lambda m: "Lobby",
        
        # Pasillo
        r'pasillo(?:\s+(?:del\s+)?(?:piso\s+)?(\d+))?': 
            lambda m: f"Pasillo{f' Piso {m.group(1)}' if m.group(1) else ''}",
        
        # Hub
        r'\bhub\b': 
            lambda m: "Hub",
        
        # Terraza
        r'terraza': 
            lambda m: "Terraza",
        
        # Estacionamiento
        r'estacionamiento|parking|garage|garaje': 
            lambda m: "Estacionamiento",
        
        # Escalera
        r'escalera(?:s)?(?:\s+(?:del\s+)?(?:piso\s+)?(\d+))?': 
            lambda m: f"Escalera{f' Piso {m.group(1)}' if m.group(1) else ''}",
        
        # Gimnasio
        r'gimnasio|gym': 
            lambda m: "Gimnasio",
        
        # Spa
        r'\bspa\b': 
            lambda m: "Spa",
        
        # Sala de reuniones
        r'sala\s+(?:de\s+)?reuniones?|sala\s+(?:de\s+)?juntas?': 
            lambda m: "Sala de Reuniones",
        
        # Baño público
        r'baño\s+público|baños?\s+públicos?|servicios?\s+higiénicos?': 
            lambda m: "Baño Público",
        
        # Piscina
        r'piscina|alberca': 
            lambda m: "Piscina",
        
        # Jardín
        r'jardin|jardín|patio': 
            lambda m: "Jardín",
        
        # Bar / Restaurant
        r'\bbar\b|restaurant|restaurante': 
            lambda m: "Bar/Restaurant",
        
        # Roof
        r'roof|azotea|techo': 
            lambda m: "Roof",
        
        # Lavandería
        r'lavanderia|lavandería|laundry': 
            lambda m: "Lavandería",
        
        # Bodega
        r'bodega|almacen|almacén|storage': 
            lambda m: "Bodega",
    }
    
    for pattern, formatter in areas.items():
        match = re.search(pattern, text_lower)
        if match:
            return formatter(match)
    
    return None


def extract_ubicacion_generica(text: str) -> Optional[str]:
    """
    ✅ NUEVA FUNCIÓN: Extrae ubicación genérica (habitación o área común).
    Intenta primero con habitación, luego con área común.
    
    Args:
        text: Texto del usuario
    
    Returns:
        Ubicación extraída o None
    """
    # Primero intentar con habitación
    habitacion = extract_habitacion(text)
    if habitacion:
        return habitacion
    
    # Si no es habitación, intentar con área común
    area = extract_area_comun(text)
    if area:
        return area
    
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
        - "reasignar_ticket": Reasignar ticket a otro worker
        - "crear_ticket": Crear nuevo ticket (habitación o área común)
        - "crear_y_asignar": Crear y asignar en un solo comando
        - "ver_estado": Ver tickets o workers
        - "unknown": No se detectó intención clara
    """
    text_lower = text.lower()
    
    # Detectar verbos de acción
    import unicodedata
    text_normalized = ''.join(
        c for c in unicodedata.normalize('NFD', text_lower)
        if unicodedata.category(c) != 'Mn'
    )

    # Extraer componentes
    ticket_id = extract_ticket_id(text)
    
    # ✅ DETECCIÓN DE FINALIZAR (PRIORIDAD)
    es_finalizar = any(word in text_normalized for word in [
        'finalizar', 'finaliza', 'finalizalo', 'finalizala',
        'completar', 'completa', 'completalo', 'completala',
        'terminar', 'termina', 'terminalo', 'terminala',
        'marcar como completado', 'marcar completado',
        'dar por terminado', 'cerrar', 'cierra'
    ])
    
    # Patrón: "Finalizar ticket 15"
    if es_finalizar and ticket_id:
        return {
            "intent": "finalizar_ticket",
            "ticket_id": ticket_id,
            "text": text
        }
    
    # ✅ DESPUÉS: Extraer componentes para otros intents
    worker = extract_worker_name(text)
    ubicacion = extract_ubicacion_generica(text)
    prioridad = detectar_prioridad(text)

    es_asignar = any(word in text_normalized for word in [
        'asignar', 'asigna', 'asina', 'asignalo', 'asignala',
        'derivar', 'deriva', 'derivalo', 'derivala',
        'mandar', 'manda', 'mandalo', 'mandala',
        'enviar', 'envia', 'envialo', 'enviala',
        'encargar', 'encarga', 'encargale',
        'delegar', 'delega', 'delegale',
        'que lo resuelva', 'que lo haga', 'que lo vea',
        'que la resuelva', 'que la haga', 'que la vea'
    ])
    
    es_reasignar = any(word in text_lower for word in [
        'reasignar', 'reasigna', 're asignar',
        'cambiar', 'cambia', 'cambiar a',
        'mover', 'mueve', 'mover a',
        'pasar', 'pasa', 'pasar a',
        'transferir', 'transfiere'
    ])
    
    es_crear = any(word in text_lower for word in ['crear', 'nuevo', 'generar', 'registrar'])
    
    # ✅ NUEVO: Detectar si es un reporte directo (área + problema)
    # Ej: "el ascensor no funciona", "cafetería derrame", "lobby luz fundida"
    tiene_problema = any(word in text_lower for word in [
        'no funciona', 'roto', 'rota', 'dañado', 'dañada', 'problema', 'falla',
        'derrame', 'sucia', 'sucio', 'fundida', 'fundido', 'descompuesto',
        'atascado', 'atorado', 'luz', 'agua', 'baño'
    ])

    # Patrón 0: "Reasignar ticket 12 a María" (PRIORIDAD MÁXIMA)
    if es_reasignar and ticket_id and worker:
        return {
            "intent": "reasignar_ticket",
            "ticket_id": ticket_id,
            "worker": worker,
            "text": text
        }
    
    # Patrón 1: "Asignar ticket 1503 a María"
    if es_asignar and ticket_id and worker and not es_reasignar:
        tiene_contexto_habitacion = any(word in text.lower() for word in [
            'la ', 'el ', 'hab ', 'habitacion', 'habitación', 'cuarto', 'pieza'
        ])
        
        if ticket_id and ticket_id < 100:
            tiene_contexto_habitacion = False
        
        if tiene_contexto_habitacion:
            pass
        else:
            return {
                "intent": "asignar_ticket",
                "ticket_id": ticket_id,
                "worker": worker,
                "text": text
            }
    
    # ✅ MODIFICADO: Patrón 2 - Crear ticket con ubicación genérica y asignar
    # "Habitación 420 limpieza urgente asignar a Pedro"
    # "Ascensor piso 3 no funciona asignar a Pedro"
    if ubicacion and es_asignar and worker:
        # Extraer detalle (todo excepto ubicación, asignar y nombre)
        detalle = text_lower
        
        # Limpiar habitación si la hay
        detalle = re.sub(r'habitación\s*\d+', '', detalle)
        detalle = re.sub(r'hab\s*\d+', '', detalle)
        detalle = re.sub(r'cuarto\s*\d+', '', detalle)
        
        # Limpiar área común si la hay
        if ubicacion:
            ubicacion_lower = ubicacion.lower()
            for word in ubicacion_lower.split():
                detalle = detalle.replace(word, '')
        
        # Limpiar comandos
        detalle = re.sub(r'asignar.*', '', detalle)
        detalle = re.sub(r'derivar.*', '', detalle)
        detalle = detalle.strip()
        
        return {
            "intent": "crear_y_asignar",
            "ubicacion": ubicacion,  # ✅ MODIFICADO: Genérico
            "detalle": detalle if detalle else "Solicitud de operaciones",
            "prioridad": prioridad,
            "worker": worker,
            "text": text
        }
    
    # ✅ MODIFICADO: Patrón 3 - Crear ticket con ubicación genérica
    # "Habitación 305 necesita toallas"
    # "El ascensor no funciona"
    # "Cafetería derrame urgente"
    if ubicacion:
        # Extraer detalle limpiando la ubicación y comandos
        detalle = text_lower
        
        # Limpiar habitaciones
        detalle = re.sub(r'habitación\s*\d+', '', detalle)
        detalle = re.sub(r'cuarto\s*\d+', '', detalle)
        detalle = re.sub(r'pieza\s*\d+', '', detalle)
        detalle = re.sub(r'hab\s*\d+', '', detalle)
        detalle = re.sub(r'^(la|el)\s+', '', detalle.strip())
        
        # Limpiar área común
        if ubicacion:
            ubicacion_lower = ubicacion.lower()
            for word in ubicacion_lower.split():
                detalle = detalle.replace(word, '')
        
        # Si hay nombre después de "a [nombre]", extraerlo y limpiar
        if worker:
            detalle = re.sub(r'\s*\.?\s*a\s+\w+\s*$', '', detalle, flags=re.IGNORECASE)
            detalle = re.sub(r'\s*para\s+\w+\s*$', '', detalle, flags=re.IGNORECASE)
            detalle = re.sub(r'\s*\.?\s*que\s+lo\s+(?:resuelva|haga|vea)\s+\w+\s*$', '', detalle, flags=re.IGNORECASE)
            detalle = re.sub(r'\s*\.?\s*que\s+la\s+(?:resuelva|haga|vea)\s+\w+\s*$', '', detalle, flags=re.IGNORECASE)
            detalle = re.sub(r'\s*\.?\s*(?:encarga|delega)(?:le)?\s+a\s+\w+\s*$', '', detalle, flags=re.IGNORECASE)
            detalle = re.sub(r'\s*\.?\s*(?:encárgale|delégale)\s+a\s+\w+\s*$', '', detalle, flags=re.IGNORECASE)
            
            if es_asignar or es_reasignar:
                detalle = re.sub(r'asignar.*', '', detalle)
                detalle = re.sub(r'derivar.*', '', detalle)
                detalle = re.sub(r'cambiar.*', '', detalle)
                detalle = detalle.strip()
                
                return {
                    "intent": "crear_y_asignar",
                    "ubicacion": ubicacion,  # ✅ MODIFICADO
                    "detalle": detalle if detalle else "Solicitud de operaciones",
                    "prioridad": prioridad,
                    "worker": worker,
                    "text": text
                }
            else:
                detalle = detalle.strip()
                return {
                    "intent": "crear_y_asignar",
                    "ubicacion": ubicacion,  # ✅ MODIFICADO
                    "detalle": detalle if detalle else "Solicitud de operaciones",
                    "prioridad": prioridad,
                    "worker": worker,
                    "text": text
                }
        else:
            # No hay nombre: solo crear ticket
            detalle = detalle.strip()
            
            # Si tiene detalle o palabras de problema, es crear ticket
            if detalle or tiene_problema:
                return {
                    "intent": "crear_ticket",
                    "ubicacion": ubicacion,  # ✅ MODIFICADO
                    "detalle": detalle if detalle else "Problema reportado",
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
            "ubicacion": ubicacion,  # ✅ MODIFICADO
            "prioridad": prioridad
        }
    }