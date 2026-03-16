"""
Detección de intenciones en texto/audio para housekeeping.
"""

import re
from typing import Dict, Any, Optional


def convertir_numeros_escritos_a_digitos(text: str) -> str:
    """
    Convierte palabras numéricas en español a dígitos.
    Maneja el rango de habitaciones de hotel (100-999).
    Ej: "habitación ochocientos diez" → "habitación 810"
    """
    CIENTOS = {
        'cien': 100, 'ciento': 100,
        'doscientos': 200, 'doscientas': 200,
        'trescientos': 300, 'trescientas': 300,
        'cuatrocientos': 400, 'cuatrocientas': 400,
        'quinientos': 500, 'quinientas': 500,
        'seiscientos': 600, 'seiscientas': 600,
        'setecientos': 700, 'setecientas': 700,
        'ochocientos': 800, 'ochocientas': 800,
        'novecientos': 900, 'novecientas': 900,
    }
    DECENAS = {
        'diez': 10, 'once': 11, 'doce': 12, 'trece': 13, 'catorce': 14,
        'quince': 15, 'dieciseis': 16, 'dieciséis': 16,
        'diecisiete': 17, 'dieciocho': 18, 'diecinueve': 19,
        'veinte': 20, 'veintiun': 21, 'veintiún': 21, 'veintiuno': 21,
        'veintidos': 22, 'veintidós': 22,
        'veintitres': 23, 'veintitrés': 23,
        'veinticuatro': 24, 'veinticinco': 25,
        'veintiseis': 26, 'veintiséis': 26,
        'veintisiete': 27, 'veintiocho': 28, 'veintinueve': 29,
        'treinta': 30, 'cuarenta': 40, 'cincuenta': 50,
        'sesenta': 60, 'setenta': 70, 'ochenta': 80, 'noventa': 90,
    }
    UNIDADES = {
        'uno': 1, 'un': 1, 'una': 1, 'dos': 2, 'tres': 3,
        'cuatro': 4, 'cinco': 5, 'seis': 6, 'siete': 7, 'ocho': 8, 'nueve': 9,
    }

    c_pat = '|'.join(sorted(CIENTOS, key=len, reverse=True))
    d_pat = '|'.join(sorted(DECENAS, key=len, reverse=True))
    u_pat = '|'.join(sorted(UNIDADES, key=len, reverse=True))

    # Patrón: CIENTOS (DECENAS (y UNIDADES)? | UNIDADES)?
    pattern = (
        rf'(?:{c_pat})'
        rf'(?:\s+(?:(?:{d_pat})(?:\s+y\s+(?:{u_pat}))?|(?:{u_pat})))?'
    )

    def compute(m_text: str) -> int:
        words = m_text.split()
        total, i = 0, 0
        if i < len(words) and words[i] in CIENTOS:
            total += CIENTOS[words[i]]
            i += 1
        if i < len(words) and words[i] in DECENAS:
            total += DECENAS[words[i]]
            i += 1
            if i + 1 < len(words) and words[i] == 'y' and words[i + 1] in UNIDADES:
                total += UNIDADES[words[i + 1]]
        elif i < len(words) and words[i] in UNIDADES:
            total += UNIDADES[words[i]]
        return total

    def replace_fn(m):
        n = compute(m.group(0))
        return str(n) if n >= 100 else m.group(0)

    return re.sub(pattern, replace_fn, text.lower(), flags=re.IGNORECASE)


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
    VALIDACIÓN: Solo acepta 3-4 dígitos para evitar confusión con opciones de menú (1, 2, 3)
    
    Args:
        text: Texto
    
    Returns:
        Número de habitación o None
    """
    text_lower = text.lower()
    text_stripped = text.strip()
    
    # Patrones con contexto (hab, habitación, cuarto, etc)
    patterns_con_contexto = [
        r'hab(?:itación)?\s*(\d{3,4})',
        r'cuarto\s*(\d{3,4})',
        r'pieza\s*(\d{3,4})',
        r'la\s+(\d{3,4})',
        r'el\s+(\d{3,4})',
    ]
    
    for pattern in patterns_con_contexto:
        match = re.search(pattern, text_lower)
        if match:
            return match.group(1)
    
    # Solo número: DEBE ser 3-4 dígitos (no 1-2 para evitar confusión con menú)
    if text_stripped.isdigit() and 3 <= len(text_stripped) <= 4:
        return text_stripped
    
    # Buscar número de 3-4 dígitos en el texto (sin contexto pero más seguro)
    match = re.search(r'\b(\d{3,4})\b', text_lower)
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

    # VALIDACIÓN MEJORADA: No es reporte directo si:
    # 1. No hay detalle
    # 2. Detalle es muy corto (< 3 caracteres)
    # 3. Detalle es SOLO números (mismo que la habitación)
    if not detalle or len(detalle) < 3:
        return None

    # Si el detalle es solo dígitos, no es un reporte válido
    # (ej: "305" → habitación=305, detalle=305 ❌)
    if detalle.isdigit():
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