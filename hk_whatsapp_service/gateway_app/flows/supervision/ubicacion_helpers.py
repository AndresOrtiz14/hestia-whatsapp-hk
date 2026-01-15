"""
Helper para formatear ubicaciones con emoji apropiado.
Diferencia entre habitaciones y áreas comunes.
"""
# gateway_app/flows/housekeeping/ubicacion_helpers.py
from __future__ import annotations

import re
import unicodedata
from typing import Optional

from hk_whatsapp_service.gateway_app.services.workers_db import normalizar_area

# Canonical areas (lo que tú quieres “como verdad”)
AREA_HOUSEKEEPING = "HOUSEKEEPING"
AREA_MANTENIMIENTO = "MANTENIMIENTO"
AREA_AREAS_COMUNES = "AREAS_COMUNES"

# Synonyms -> canonical
_AREA_SYNONYMS = {
    # Housekeeping
    "hk": AREA_HOUSEKEEPING,
    "housekeeping": AREA_HOUSEKEEPING,

    # Mantenimiento
    "mt": AREA_MANTENIMIENTO,
    "mantenimiento": AREA_MANTENIMIENTO,
    "mantencion": AREA_MANTENIMIENTO,   # sin tilde
    "mantencion ": AREA_MANTENIMIENTO,
    "mantencion.": AREA_MANTENIMIENTO,
    "mantencion,": AREA_MANTENIMIENTO,
    "mantencion/": AREA_MANTENIMIENTO,
    "mantencion-": AREA_MANTENIMIENTO,
    "mantencion_": AREA_MANTENIMIENTO,
    "mantencion;": AREA_MANTENIMIENTO,
    "mantencion:": AREA_MANTENIMIENTO,
    "mantencion)": AREA_MANTENIMIENTO,
    "mantencion(": AREA_MANTENIMIENTO,

    # Áreas comunes
    "ac": AREA_AREAS_COMUNES,
    "areas comunes": AREA_AREAS_COMUNES,
    "areas_comunes": AREA_AREAS_COMUNES,
    "areascomunes": AREA_AREAS_COMUNES,
}

_AREA_EMOJI = {
    AREA_HOUSEKEEPING: "🏠",
    AREA_MANTENIMIENTO: "🔧",
    AREA_AREAS_COMUNES: "📍",
}

_AREA_SHORT = {
    AREA_HOUSEKEEPING: "HK",
    AREA_MANTENIMIENTO: "MT",
    AREA_AREAS_COMUNES: "AC",
}


def _strip_accents(s: str) -> str:
    """Remueve tildes/diacríticos para comparar de forma estable."""
    return "".join(
        c for c in unicodedata.normalize("NFKD", s)
        if not unicodedata.combining(c)
    )


def _clean(s: str) -> str:
    """Normaliza texto: lower, sin tildes, espacios colapsados, sin ruido."""
    s = (s or "").strip()
    if not s:
        return ""
    s = _strip_accents(s).lower()

    # Reemplazos comunes
    s = s.replace("-", " ").replace("_", " ")
    s = re.sub(r"\s+", " ", s).strip()
    return s


def normalize_area(area: Optional[str], default: str = AREA_HOUSEKEEPING) -> str:
    """
    Devuelve el nombre canónico del área.
    - "Mantención" / "MANTENCION" -> "MANTENIMIENTO"
    - "Áreas comunes" / "AC" -> "AREAS_COMUNES"
    - None -> default
    """
    raw = _clean(area)
    if not raw:
        return default

    # Algunas entradas vienen como "MANTENCIÓN (turno)" o similares
    # Tomamos solo la parte principal si hay paréntesis
    raw = raw.split("(")[0].strip()

    # Mapeo directo
    if raw in _AREA_SYNONYMS:
        return _AREA_SYNONYMS[raw]

    # Casos más “sucios”: si contiene la palabra
    if "mantenc" in raw or "mantenim" in raw:
        return AREA_MANTENIMIENTO
    if "area comun" in raw or "areas comun" in raw:
        return AREA_AREAS_COMUNES
    if "house" in raw or raw == "hk":
        return AREA_HOUSEKEEPING

    return default

def get_area_emoji(area: str) -> str:
    a = normalizar_area(area or "")
    return {
        "HOUSEKEEPING": "🧹",
        "MANTENCION": "🔧",
        "MANTENIMIENTO": "🔧",
        "AREAS_COMUNES": "🏢",
    }.get(a, "👤")

def get_area_tag(area: str) -> str:
    a = normalizar_area(area or "")
    return {
        "HOUSEKEEPING": "HK",
        "MANTENCION": "MT",
        "MANTENIMIENTO": "MT",
        "AREAS_COMUNES": "AC",
    }.get(a, "?")

def get_area_short(area: Optional[str]) -> str:
    canon = normalize_area(area)
    return _AREA_SHORT.get(canon, canon[:2])


def formatear_ubicacion_con_emoji(ubicacion: Optional[str]) -> str:
    """
    - Si ubicacion es dígito: "🏠 Habitación 305"
    - Si no: "📍 Ascensor Piso 2"
    """
    if not ubicacion:
        return "📍 Sin ubicación"

    u = str(ubicacion).strip()
    if u.isdigit():
        num = int(u)
        if 100 <= num <= 9999:
            return f"🏠 Habitación {u}"

    return f"📍 {u}"