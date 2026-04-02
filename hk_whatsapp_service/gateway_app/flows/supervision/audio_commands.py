"""
Procesamiento de comandos de audio para supervisión.
Detecta intenciones en transcripciones de voz.
VERSIÓN CON SOPORTE PARA ÁREAS COMUNES.
"""

import re
import logging
from typing import Dict, Any, Optional, Tuple
from gateway_app.flows.housekeeping.intents import detectar_prioridad
from gateway_app.flows.supervision.ubicacion_helpers import (
    _AREA_SYNONYMS,
    _strip_accents,
    AREA_HOUSEKEEPING,
    AREA_MANTENIMIENTO,
    AREA_AREAS_COMUNES,
)

logger = logging.getLogger(__name__)

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
        r'#\s*(\d+)',
        r'\b(\d+)\b',  # 3-4 dígitos solos
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
        r'\b(?:a|para)\s+(.+)$',                    # ✅ Captura todo después de "a" o "para"
        r'que\s+lo\s+(?:resuelva|haga|vea)\s+(.+)$', # ✅ Captura todo después
        r'que\s+la\s+(?:resuelva|haga|vea)\s+(.+)$', # ✅ Captura todo después
        r'(?:encarga|delega)(?:le)?\s+a\s+(.+)$',    # ✅ Captura todo después
        r'\basignar\s+a\s+(.+)$'                     # ✅ Ya estaba correcto
    ]
    
    for patron in patrones:
        match = re.search(patron, text_lower)
        if match:
            posible_nombre = match.group(1).strip()
            
            # ✅ NUEVO: Limpiar sufijos comunes
            cleanup_words = ['por favor', 'porfavor', 'porfa', 'gracias']
            for cleanup in cleanup_words:
                if posible_nombre.endswith(cleanup):
                    posible_nombre = posible_nombre[:-len(cleanup)].strip()

            # Limpiar puntuación al final (ej: "Pedro." → "Pedro")
            posible_nombre = re.sub(r'[.,!?;:]+$', '', posible_nombre).strip()

            # ✅ NUEVO: Si tiene más de una palabra, capitalizar y retornar directo
            if ' ' in posible_nombre:
                # Nombres compuestos: "chef cocina" → "Chef Cocina"
                return ' '.join(word.capitalize() for word in posible_nombre.split())
            
            # ✅ MANTENER: Lógica original para nombres simples
            if posible_nombre in nombres:
                return posible_nombre.capitalize()
            for palabra in text.split():
                if palabra.lower() == posible_nombre and len(palabra) >= 3:
                    return palabra
    
    for nombre in nombres:
        if re.search(r'\b' + re.escape(nombre) + r'\b', text_lower):
            return nombre.capitalize()
    
    palabras = text.split()
    for i, palabra in enumerate(palabras):
        if palabra and len(palabra) >= 3 and palabra[0].isupper():
            # ✅ FIX: Saltar la primera palabra de oraciones multi-palabra.
            # En español la primera palabra siempre va con mayúscula
            # y no indica que sea nombre propio.
            # Ej: "Gancho caído..." → "Gancho" NO es worker.
            # Si alguien escribe solo "Pedro" (1 palabra), SÍ lo detecta.
            if i == 0 and len(palabras) > 1:
                continue

            palabras_comunes = [
                'Hab', 'Habitación', 'Habitacion', 'Cuarto', 'Ticket',
                'El', 'La', 'Los', 'Las', 'Un', 'Una', 'Pieza',
                'Asignar', 'Derivar', 'Mandar', 'Enviar', 'Reasignar',
                'Finalizar', 'Completar', 'Terminar', 'Cerrar',
                'Pendientes', 'Urgentes', 'Menu', 'Menú', 'Ayuda', 'Help',
                'Ver', 'Mostrar', 'Crear', 'Nuevo', 'Nueva',
                'Necesita', 'Necesitan', 'Falta', 'Faltan',
                'Problema', 'Revisar', 'Cambiar', 'Roto', 'Rota',
            ]
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
    r'habitaci[oó]n\s*(\d{1,4})',
    r'habt?\s*\.?\s*(\d{1,4})',    # "habt 1013", "hab. 205", "hab 12"
    r'cuarto\s*(\d{1,4})',
    r'pieza\s*(\d{1,4})',
    r'la\s+(\d{3,4})',             # genérico: mantener 3-4 dígitos
    r'número\s+(\d{3,4})',         # genérico: mantener 3-4 dígitos
    r'\ben\s+(\d{3,4})\b',        # genérico: mantener 3-4 dígitos
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

        # Piso (standalone, sin área asociada)
        r'\bpiso\s+(\d{1,2})\b':
            lambda m: f"Piso {m.group(1)}",
        
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


def extract_area_departamento(text: str) -> Optional[str]:
    """
    Extrae el área de gestión (HOUSEKEEPING|MANTENIMIENTO|AREAS_COMUNES) del texto.
    Reutiliza _AREA_SYNONYMS de ubicacion_helpers.

    Ejemplos:
        "mantencion"    -> "MANTENIMIENTO"
        "hk"            -> "HOUSEKEEPING"
        "areas comunes" -> "AREAS_COMUNES"
        "ac"            -> "AREAS_COMUNES"
        "mt"            -> "MANTENIMIENTO"
    """
    text_n = _strip_accents(text.lower())

    # Multi-palabra primero para evitar match parcial (ej. "ac" antes de "areas comunes")
    for synonym in sorted(_AREA_SYNONYMS, key=len, reverse=True):
        pattern = r'\b' + re.escape(synonym.strip()) + r'\b'
        if re.search(pattern, text_n):
            return _AREA_SYNONYMS[synonym]

    # Fuzzy fallback
    if 'mantenc' in text_n or 'mantenim' in text_n:
        return AREA_MANTENIMIENTO
    if 'area comun' in text_n or 'areas comun' in text_n:
        return AREA_AREAS_COMUNES
    if 'housekeeping' in text_n:
        return AREA_HOUSEKEEPING

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

    logger.info(f"🔍 === INICIO detect_audio_intent ===")
    logger.info(f"🔍 text = '{text}'")
    
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

    logger.info(f"🔍 text_normalized = '{text_normalized}'")

    # PRIORIDAD: "habitación/hab/cuarto/pieza N tiene/hay/presenta ..." → crear_ticket
    # Evita que el número de habitación sea capturado como ticket_id
    _room_report_match = re.search(
        r'(?:habitaci[oó]n|hab\.?t?|cuarto|pieza)\s+(\d{1,4})\s+'
        r'(?:tiene|hay|presenta|reporta|con)\b(.+)',
        text,
        re.IGNORECASE,
    )
    if _room_report_match:
        _room_num = _room_report_match.group(1)
        _detalle = _room_report_match.group(2).strip()
        logger.info(f"✅ MATCH room-report: habitación {_room_num} | detalle='{_detalle}'")
        return {
            "intent": "crear_ticket",
            "ubicacion": f"habitación {_room_num}",
            "detalle": _detalle if _detalle else "Problema reportado",
            "prioridad": detect_priority(text),
            "ticket_id": None,
            "text": text,
        }

    # Extraer componentes
    ticket_id = extract_ticket_id(text)
    logger.info(f"🔍 ticket_id = {ticket_id}")
    
    # ✅ DETECCIÓN DE FINALIZAR (PRIORIDAD)
    palabras_finalizar = [
    'finalizar', 'finaliza', 'finalizalo', 'finalizala',
    'completar', 'completa', 'completalo', 'completala',
    'terminar', 'termina', 'terminalo', 'terminala',
    'marcar como completado', 'marcar completado',
    'dar por terminado', 'cerrar', 'cierra', 'reuslto', 'resuelto',
    ]

    es_finalizar = any(word in text_normalized for word in palabras_finalizar)
    logger.info(f"🔍 es_finalizar = {es_finalizar}")
    logger.info(f"🔍 palabras en texto: {[w for w in palabras_finalizar if w in text_normalized]}")
    
    # Patrón: "Finalizar ticket 15"
    if es_finalizar and ticket_id:
        logger.info(f"✅ MATCH: Finalizar ticket #{ticket_id}")
        return {
            "intent": "finalizar_ticket",
            "ticket_id": ticket_id,
            "text": text
        }
    
    logger.info(f"❌ NO es finalizar, continuando...")

    # ✅ NUEVO: Detectar cambiar_area ANTES de es_reasignar
    # (es_reasignar captura 'cambiar'/'cambia', por eso va primero)
    area_dept = extract_area_departamento(text)
    tiene_area_keyword = 'area' in text_normalized   # "área" → "area" tras quitar tildes
    es_reclasificar = any(w in text_normalized for w in [
        'reclasificar', 'reclasifica', 'reclasificacion', 'reclasificacion',
        'clasificar', 'clasifica',
    ])

    if (tiene_area_keyword or es_reclasificar) and ticket_id and area_dept:
        logger.info(f"✅ MATCH: cambiar_area ticket #{ticket_id} → {area_dept}")
        return {
            "intent": "cambiar_area",
            "ticket_id": ticket_id,
            "area": area_dept,
            "text": text,
        }

    # ✅ DESPUÉS: Extraer componentes para otros intents
    worker = extract_worker_name(text)
    logger.info(f"🔍 worker = '{worker}'")
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
    # Solo retorna asignar_ticket si NO hay ubicación detectada.
    # Si hay ubicación (piso, habitación, área común), caer a crear_y_asignar.
    if es_asignar and ticket_id and worker and not es_reasignar:
        if not ubicacion:
            return {
                "intent": "asignar_ticket",
                "ticket_id": ticket_id,
                "worker": worker,
                "text": text
            }
        
    # ✅ NUEVO: Patrón 1.5 - "Asignar ticket 6" SIN nombre de worker
    # Debe mostrar lista de workers disponibles
    if es_asignar and ticket_id and not worker:
        return {
            "intent": "asignar_ticket_sin_worker",
            "ticket_id": ticket_id,
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
    
    # Patrón ver_ticket: "ver 1503", "detalle 1503", "info 1503", "ticket 1503"
    es_ver_ticket = any(w in text_normalized for w in ['ver', 'detalle', 'info'])
    es_ticket_standalone = bool(re.match(r'^\s*ticket\s*#?\s*\d+\s*$', text_normalized))
    if ticket_id and (es_ver_ticket or es_ticket_standalone) and not es_asignar and not es_reasignar:
        return {"intent": "ver_ticket", "ticket_id": ticket_id, "text": text}

    # Patrón 5: Ver estado
    if any(word in text_lower for word in ['ver', 'muestra', 'mostrar', 'estado', 'cómo van']):
        if 'pendiente' in text_lower:
            return {"intent": "ver_pendientes", "text": text}
        if 'progreso' in text_lower:
            return {"intent": "ver_progreso", "text": text}
        if 'worker' in text_lower:
            return {"intent": "ver_workers", "text": text}
    
    # Patrón 6: Aviso general a todos los trabajadores
    palabras_aviso = ['aviso', 'avisar', 'comunicado', 'informar a todos', 'notificar a todos']
    es_aviso = any(w in text_normalized for w in palabras_aviso)
    if es_aviso:
        match_aviso = re.search(
            r'(?:aviso|avisar(?:\s+a\s+todos?)?|comunicado|informar\s+a\s+todos?|notificar\s+a\s+todos?)[,:]?\s*(.+)',
            text,
            re.IGNORECASE,
        )
        mensaje_aviso = match_aviso.group(1).strip() if match_aviso else text.strip()
        return {
            "intent": "aviso_general",
            "mensaje": mensaje_aviso,
            "text": text,
        }

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