"""
Helper para formatear ubicaciones con emoji apropiado.
Diferencia entre habitaciones y áreas comunes.
"""

def formatear_ubicacion_con_emoji(ubicacion: str) -> str:
    """
    Agrega emoji apropiado según tipo de ubicación.
    
    Args:
        ubicacion: "305" o "Ascensor Piso 2"
    
    Returns:
        "🏠 Habitación 305" o "📍 Ascensor Piso 2"
    
    Examples:
        >>> formatear_ubicacion_con_emoji("305")
        "🏠 Habitación 305"
        
        >>> formatear_ubicacion_con_emoji("1503")
        "🏠 Habitación 1503"
        
        >>> formatear_ubicacion_con_emoji("Ascensor Piso 2")
        "📍 Ascensor Piso 2"
        
        >>> formatear_ubicacion_con_emoji("Cafetería")
        "📍 Cafetería"
    """
    # Si es número de 3-4 dígitos, es habitación
    if ubicacion and ubicacion.strip().isdigit():
        num = int(ubicacion.strip())
        if 100 <= num <= 9999:
            return f"🏠 Habitación {ubicacion}"
    
    # Si no, es área común
    return f"📍 {ubicacion}"


def get_area_emoji(area: str) -> str:
    """
    Obtiene emoji según área del worker.
    
    Args:
        area: "HOUSEKEEPING", "AREAS_COMUNES", "MANTENIMIENTO"
    
    Returns:
        Emoji correspondiente
    """
    area_upper = (area or "HOUSEKEEPING").upper()
    
    return {
        "HOUSEKEEPING": "🏠",
        "AREAS_COMUNES": "📍",
        "ÁREAS_COMUNES": "📍",
        "MANTENIMIENTO": "🔧",
        "MANTENCIÓN": "🔧",
    }.get(area_upper, "👤")


def get_area_short(area: str) -> str:
    """
    Obtiene abreviación del área.
    
    Args:
        area: "HOUSEKEEPING", "AREAS_COMUNES", "MANTENIMIENTO"
    
    Returns:
        Abreviación (HK, AC, MT)
    """
    area_upper = (area or "HOUSEKEEPING").upper()
    
    return {
        "HOUSEKEEPING": "HK",
        "AREAS_COMUNES": "AC",
        "ÁREAS_COMUNES": "AC",
        "MANTENIMIENTO": "MT",
        "MANTENCIÓN": "MT",
    }.get(area_upper, area[:2].upper())