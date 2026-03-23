"""
Funciones auxiliares para soporte de Áreas Comunes en bot HK.
Permite que el bot funcione tanto para Housekeeping como para Áreas Comunes.
"""
import re
from typing import Optional, Dict

# Configuración de textos por área
TEXTOS_POR_AREA = {
    "HOUSEKEEPING": {
        "ubicacion_label": "🏠 Habitación",
        "ubicacion_pregunta": "🏠 ¿Qué habitación?\n\nEj: 305, 1503",
        "ubicacion_ejemplo": "305",
    },
    "AREAS_COMUNES": {
        "ubicacion_label": "📍 Área",
        "ubicacion_pregunta": (
            "📍 ¿Qué área?\n\n"
            "Ejemplos:\n"
            "• ascensor piso 3\n"
            "• cafetería\n"
            "• lobby\n"
            "• pasillo piso 2"
        ),
        "ubicacion_ejemplo": "Cafetería",
    },
    "MANTENIMIENTO": {
        "ubicacion_label": "📍 Ubicación",
        "ubicacion_pregunta": "📍 ¿Dónde está el problema?\n\nEj: calderas, roof, sistema eléctrico",
        "ubicacion_ejemplo": "Calderas",
    }
}


def obtener_area_worker(from_phone: str, tenant=None) -> str:
    """
    Obtiene el área del worker desde la BD.

    Args:
        from_phone: Teléfono del worker

    Returns:
        'HOUSEKEEPING', 'AREAS_COMUNES', 'MANTENIMIENTO', etc.
        Default: 'HOUSEKEEPING' si no se encuentra
    """
    from gateway_app.services.workers_db import buscar_worker_por_telefono

    worker = buscar_worker_por_telefono(from_phone, property_id=tenant.property_id if tenant else "")
    
    if not worker:
        return "HOUSEKEEPING"  # Default
    
    area = worker.get("area", "HOUSEKEEPING")
    
    # Normalizar área
    area_normalized = area.upper().replace(" ", "_")
    
    return area_normalized


def extraer_area_comun(text: str) -> Optional[str]:
    """
    Extrae área común del texto.
    
    Áreas soportadas:
    - Ascensor (con piso opcional)
    - Cafetería / Comedor
    - Lobby / Recepción
    - Pasillo (con piso)
    - Hub
    - Terraza
    - Estacionamiento
    - Escalera
    - Gimnasio / Gym
    - Spa
    - Sala de reuniones
    - Baño público
    - Piscina
    - Jardín
    - Bar / Restaurant
    
    Args:
        text: Texto del usuario
    
    Returns:
        Área formateada o None
    
    Ejemplos:
        "ascensor piso 3" → "Ascensor Piso 3"
        "cafeteria" → "Cafetería"
        "pasillo del piso 2" → "Pasillo Piso 2"
        "lobby" → "Lobby"
    """
    text_lower = text.lower()
    
    # Diccionario de áreas con sus patrones y formateadores
    areas = {
        # Ascensor
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
        
        # Roof / Azotea
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


def extraer_ubicacion_generica(text: str, area_worker: str) -> Optional[str]:
    """
    Extrae ubicación genérica según el tipo de worker.
    
    Args:
        text: Texto del usuario
        area_worker: Área del worker ('HOUSEKEEPING', 'AREAS_COMUNES', etc.)
    
    Returns:
        Ubicación extraída o None
    """
    if area_worker == "HOUSEKEEPING":
        # Buscar habitación (3-4 dígitos)
        from gateway_app.flows.housekeeping.intents import extraer_habitacion
        return extraer_habitacion(text)
    
    elif area_worker == "AREAS_COMUNES":
        # Buscar área común
        return extraer_area_comun(text)
    
    elif area_worker == "MANTENIMIENTO":
        # ✅ MODIFICADO: Mantenimiento puede trabajar en habitaciones, áreas comunes Y áreas técnicas
        
        # 1. Primero intentar con áreas comunes
        area = extraer_area_comun(text)
        if area:
            return area
        
        # 2. Luego áreas técnicas específicas
        areas_tecnicas = {
            r'calderas?|boiler': lambda m: "Calderas",
            r'roof|azotea': lambda m: "Roof",
            r'sistema\s+eléctrico|electricidad|tablero': lambda m: "Sistema Eléctrico",
            r'plomeria|plomería|cañeria|cañería|tuberias|tuberías': lambda m: "Plomería",
            r'hvac|aire\s+acondicionado|climatizacion|climatización': lambda m: "HVAC",
            r'elevador|montacargas': lambda m: "Elevador",
        }
        
        text_lower = text.lower()
        for pattern, formatter in areas_tecnicas.items():
            match = re.search(pattern, text_lower)
            if match:
                return formatter(match)
        
        # ✅ NUEVO: 3. Finalmente intentar con habitación (mantenimiento también trabaja en habitaciones)
        from gateway_app.flows.housekeeping.intents import extraer_habitacion
        habitacion = extraer_habitacion(text)
        if habitacion:
            return habitacion
        
        return None
    
    else:
        # Default: intentar con habitación primero, luego área
        from gateway_app.flows.housekeeping.intents import extraer_habitacion
        habitacion = extraer_habitacion(text)
        if habitacion:
            return habitacion
        
        return extraer_area_comun(text)


def detectar_reporte_directo_adaptado(text: str, area_worker: str) -> Optional[Dict]:
    """
    Detecta reporte directo adaptado al tipo de worker.
    
    Args:
        text: Texto del usuario
        area_worker: Área del worker
    
    Returns:
        dict con ubicacion, detalle, prioridad o None
    
    Ejemplos:
        # Housekeeping:
        "hab 305 ducha rota" → {ubicacion: "305", detalle: "ducha rota", ...}
        
        # Áreas Comunes:
        "ascensor piso 3 no funciona" → {ubicacion: "Ascensor Piso 3", ...}
    """
    from gateway_app.flows.housekeeping.intents import detectar_prioridad
    
    # Intentar extraer ubicación
    ubicacion = extraer_ubicacion_generica(text, area_worker)
    
    if not ubicacion:
        return None
    
    # Extraer detalle (remover la ubicación del texto)
    text_lower = text.lower()
    
    # Remover prefijos comunes
    text_lower = re.sub(r'^(hab|habitacion|habitación|cuarto|pieza|area|área)\s+', '', text_lower)
    
    # Si es housekeeping, remover el número
    if area_worker == "HOUSEKEEPING":
        text_lower = re.sub(r'\b\d{3,4}\b', '', text_lower)
    else:
        # Si es área común, remover el nombre del área
        if ubicacion:
            ubicacion_lower = ubicacion.lower()
            # Remover variaciones del área
            for word in ubicacion_lower.split():
                text_lower = text_lower.replace(word, '')
    
    detalle = text_lower.strip()
    
    if not detalle or len(detalle) < 3:
        return None
    
    prioridad = detectar_prioridad(text)
    
    return {
        "ubicacion": ubicacion,
        "detalle": detalle,
        "prioridad": prioridad
    }


def get_texto_por_area(area_worker: str, clave: str) -> str:
    """
    Obtiene texto adaptado según el área del worker.
    
    Args:
        area_worker: Área del worker
        clave: Clave del texto a obtener
    
    Returns:
        Texto adaptado
    """
    textos = TEXTOS_POR_AREA.get(area_worker, TEXTOS_POR_AREA["HOUSEKEEPING"])
    return textos.get(clave, "")


def formatear_ubicacion_para_mensaje(ubicacion: str, area_worker: str) -> str:
    """
    Formatea la ubicación para mostrar en mensajes.
    
    Args:
        ubicacion: Ubicación extraída
        area_worker: Área del worker
    
    Returns:
        Ubicación formateada con emoji
    
    Ejemplos:
        ("305", "HOUSEKEEPING") → "🏠 Habitación: 305"
        ("Ascensor Piso 3", "AREAS_COMUNES") → "📍 Área: Ascensor Piso 3"
    """
    label = get_texto_por_area(area_worker, "ubicacion_label")
    return f"{label}: {ubicacion}"