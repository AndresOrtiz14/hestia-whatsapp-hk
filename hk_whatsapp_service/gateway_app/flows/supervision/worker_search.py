"""
Sistema de búsqueda inteligente de workers (trabajadores del hotel) con fuzzy matching.
Maneja nombres duplicados, apodos, typos y confirmaciones.

Soporta múltiples roles: housekeeping, mantenimiento, conserjería, etc.
"""

from typing import List, Dict, Any, Optional
from difflib import SequenceMatcher

from gateway_app.flows.supervision.ubicacion_helpers import get_area_emoji, get_area_tag
from gateway_app.services.workers_db import normalizar_area


def similarity(a: str, b: str) -> float:
    """
    Calcula similitud entre dos strings (0.0 a 1.0).
    
    Args:
        a: String 1
        b: String 2
    
    Returns:
        Similitud (0.0 = diferentes, 1.0 = iguales)
    """
    return SequenceMatcher(None, a.lower(), b.lower()).ratio()


def buscar_workers(nombre_query: str, workers: List[Dict[str, Any]], rol: str = None) -> List[Dict[str, Any]]:
    """
    Busca workers por nombre con tolerancia a errores.
    
    Args:
        nombre_query: Nombre a buscar (puede tener typos)
        workers: Lista de workers disponibles
        rol: Rol opcional para filtrar (ej: "housekeeping", "mantenimiento")
    
    Returns:
        Lista de workers encontrados, ordenados por relevancia
    
    Ejemplos:
        >>> buscar_workers("María", workers)
        [María González (Housekeeping), María López (Housekeeping)]
        
        >>> buscar_workers("Pedro", workers, rol="mantenimiento")
        [Pedro Ramírez (Mantención)]
    """
    nombre_query = nombre_query.lower().strip()
    
    # Filtrar por rol si se especifica
    workers_filtrados = workers
    if rol:
        workers_filtrados = [w for w in workers if w.get("rol") == rol]
    
    candidatos = []
    
    for worker in workers_filtrados:
        score = 0.0
        match_type = None
        
        # 1. Búsqueda exacta en nombre
        if worker.get("nombre", "").lower() == nombre_query:
            score = 1.0
            match_type = "exact_name"
        
        # 2. Búsqueda exacta en apellido
        elif worker.get("apellido", "").lower() == nombre_query:
            score = 1.0
            match_type = "exact_surname"
        
        # 3. Búsqueda en nombre completo
        elif nombre_query in worker.get("nombre_completo", "").lower():
            score = 0.95
            match_type = "contains"
        
        # 4. Búsqueda en apodos
        elif any(nombre_query == apodo.lower() for apodo in worker.get("apodos", [])):
            score = 0.95
            match_type = "nickname"
        
        # 5. Fuzzy matching en nombre (tolerancia a typos)
        else:
            nombre_sim = similarity(nombre_query, worker.get("nombre", ""))
            apellido_sim = similarity(nombre_query, worker.get("apellido", ""))
            completo_sim = similarity(nombre_query, worker.get("nombre_completo", ""))
            
            # Tomar la mejor similitud
            score = max(nombre_sim, apellido_sim, completo_sim)
            
            # Solo considerar si similitud >= 0.6 (60%)
            if score >= 0.6:
                match_type = "fuzzy"
        
        if score > 0:
            candidatos.append({
                **worker,
                "match_score": score,
                "match_type": match_type
            })
    
    # Ordenar por score (mayor primero)
    candidatos.sort(key=lambda x: x["match_score"], reverse=True)
    
    return candidatos

def _estado_emoji(worker: dict) -> str:
    # Fuente de verdad: turno_activo desde users
    if not worker.get("turno_activo"):
        return "⛔"  # fuera de turno
    # flags efímeros desde runtime
    if worker.get("pausada"):
        return "⏸️"
    if worker.get("ocupada") or worker.get("ticket_activo"):
        return "🔴"
    return "✅"


def _estado_emoji(w: dict) -> str:
    """
    Emoji de estado del worker:
    - ⛔ fuera de turno
    - ⏸️ en pausa
    - 🔴 ocupada (tiene ticket activo / ocupada)
    - ✅ disponible
    """
    turno = w.get("turno_activo")
    # Si no viene turno_activo, lo tratamos como False para no mostrar ❓
    # (ideal: que SI venga desde BD)
    if turno is not True:
        return "⛔"

    if w.get("pausada"):
        return "⏸️"

    if w.get("ocupada") or w.get("ticket_activo"):
        return "🔴"

    return "✅"


def formato_lista_workers(workers, max_mostrar: int = 5):
    # Blindaje: a veces llega dict en vez de lista
    if not workers:
        return "❌ No encontré workers."
    if isinstance(workers, dict):
        workers = [workers]

    lines = ["📋 Encontré a:"]

    for idx, w in enumerate(workers[:max_mostrar], start=1):
        nombre = w.get("nombre_completo") or w.get("username") or "Sin nombre"

        # Normaliza área
        area_raw = w.get("area") or "HOUSEKEEPING"
        area_norm = normalizar_area(area_raw)

        area_emoji = get_area_emoji(area_norm)
        area_tag = get_area_tag(area_norm)

        estado_icon = _estado_emoji(w)

        # (opcional) info extra si quieres
        info_extra = ""
        if (w.get("ocupada") or w.get("ticket_activo")) and w.get("ticket_activo"):
            info_extra = f" (ticket #{w['ticket_activo']})"

        lines.append(f"{idx}. {estado_icon} {nombre} ({area_emoji} {area_tag}){info_extra}")

    if len(workers) > max_mostrar:
        lines.append(f"\n... y {len(workers) - max_mostrar} más")

    lines.append("\n💡 Responde con un número (1-{}), o 'cancelar'.".format(min(len(workers), max_mostrar)))
    return "\n".join(lines)


def manejar_seleccion_worker(
    texto: str,
    workers_disponibles: List[Dict[str, Any]]
) -> Optional[Dict[str, Any]]:
    """
    Maneja la selección de worker cuando hay múltiples opciones.
    
    Args:
        texto: Texto del supervisor (número o apellido)
        workers_disponibles: Lista de workers entre las que elegir
    
    Returns:
        Mucama seleccionada, None si no válido, o "CANCEL" si cancelar
    """
    texto_original = texto.strip()
    texto = texto_original.lower()
    
    # Caso especial: Cancelar
    if texto in ['cancelar', 'cancel', 'salir', 'no', 'nada']:
        return "CANCEL"
    
    # Caso especial: Comandos globales (bloquear para evitar confusión)
    if texto in ['m', 'menu', 'menú', 'pendientes', 'urgente', 'help', 'ayuda']:
        return "CANCEL"
    
    # Caso 1: Selección por número (SOLO números 1-5)
    if texto.isdigit():
        numero = int(texto)
        # Validar que esté en rango
        if 1 <= numero <= len(workers_disponibles):
            index = numero - 1
            return workers_disponibles[index]
        else:
            # Número fuera de rango
            return None
    
    # Caso 2: Selección por apellido (debe tener al menos 3 letras)
    if len(texto) >= 3:
        # Buscar por apellido exacto o parcial
        for worker in workers_disponibles:
            apellido = worker.get("apellido", "").lower()
            if texto in apellido or apellido in texto:
                return worker
        
        # No encontró por apellido, intentar fuzzy match
        resultados = buscar_workers(texto_original, workers_disponibles)
        if resultados and resultados[0]["match_score"] > 0.8:
            return resultados[0]
    
    # No válido
    return None


# Mapeo de apodos comunes (Chile)
APODOS_COMUNES = {
    "pepe": "josé",
    "panchito": "francisco",
    "pancho": "francisco",
    "chelo": "consuelo",
    "coni": "constanza",
    "nico": "nicolás",
    "seba": "sebastián",
    "cata": "catalina",
    "cami": "camila",
    "vero": "verónica",
    "pato": "patricio",
    "paty": "patricia",
    "fer": "fernando",
    "fran": "francisco",
    "lucho": "luis",
    "lalo": "eduardo",
    "memo": "guillermo",
    "beto": "roberto",
    "toño": "antonio",
    "chela": "graciela",
    "lola": "dolores",
    "nena": "eugenia"
}


def normalizar_nombre(nombre: str) -> str:
    """
    Normaliza nombre expandiendo apodos comunes.
    
    Args:
        nombre: Nombre o apodo
    
    Returns:
        Nombre normalizado
    
    Ejemplos:
        >>> normalizar_nombre("Pepe")
        "José"
        >>> normalizar_nombre("María")
        "María"
    """
    nombre_lower = nombre.lower().strip()
    
    # Buscar apodo en mapeo
    if nombre_lower in APODOS_COMUNES:
        return APODOS_COMUNES[nombre_lower].capitalize()
    
    return nombre.capitalize()


# ==========================================
# ALIASES PARA RETROCOMPATIBILIDAD
# ==========================================

def buscar_mucamas(nombre_query: str, mucamas: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Alias para buscar_workers. Mantenido para retrocompatibilidad."""
    return buscar_workers(nombre_query, mucamas)


def formato_lista_mucamas(mucamas: List[Dict[str, Any]], max_mostrar: int = 5) -> str:
    """Alias para formato_lista_workers. Mantenido para retrocompatibilidad."""
    return formato_lista_workers(mucamas, max_mostrar)


def manejar_seleccion_mucama(texto: str, mucamas_disponibles: List[Dict[str, Any]]):
    """Alias para manejar_seleccion_worker. Mantenido para retrocompatibilidad."""
    return manejar_seleccion_worker(texto, mucamas_disponibles)