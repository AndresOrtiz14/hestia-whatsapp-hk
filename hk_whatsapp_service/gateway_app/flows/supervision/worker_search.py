"""
Sistema de búsqueda inteligente de workers (trabajadores del hotel) con fuzzy matching.
Maneja nombres duplicados, apodos, typos y confirmaciones.

Soporta múltiples roles: housekeeping, mantenimiento, conserjería, etc.
"""

from typing import List, Dict, Any, Optional
from difflib import SequenceMatcher

from gateway_app.flows.supervision.ubicacion_helpers import get_area_emoji, get_area_tag

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


def formato_lista_workers(workers: List[Dict[str, Any]], max_mostrar: int = 5) -> str:
    """
    Formatea lista de workers para mostrar al supervisor.
    
    Args:
        workers: Lista de workers encontradas
        max_mostrar: Máximo número a mostrar
    
    Returns:
        Texto formateado
    """
    if not workers:
        return "❌ No encontré a nadie con ese nombre"
    
    if len(workers) == 1:
        # Solo una: confirmar directamente
        worker_area = worker.get("area")
        area_emoji = get_area_emoji(worker_area)
        area_tag = get_area_tag(worker_area)
        worker = workers[0]
        estado_emoji = {
            "disponible": "✅",
            "ocupada": "🔴",
            "en_pausa": "⏸️"
        }.get(worker.get("estado"), "❓")

        return f"""📋 Encontré a:
        {estado_emoji} 📋 Encontré a:\n{area_emoji} {worker['nombre_completo']} ({area_tag})\n\n"
        "💡 Escribe 'sí' para confirmar o 'no' para cancelar"""
    
    # Múltiples resultados
    lineas = [f"📋 Encontré {len(workers)} personas:\n"]
    
    for i, worker in enumerate(workers[:max_mostrar], 1):
        estado_emoji = {
            "disponible": "✅",
            "ocupada": "🔴",
            "en_pausa": "⏸️"
        }.get(worker.get("estado"), "❓")
        
        # Info adicional según estado
        info_extra = ""
        if worker.get("estado") == "ocupada" and worker.get("ticket_activo"):
            info_extra = f" (en ticket #{worker['ticket_activo']})"
        elif worker.get("promedio_tiempo_resolucion"):
            info_extra = f" ({worker['promedio_tiempo_resolucion']:.0f} min promedio)"
        
        lineas.append(
            f"{i}. {estado_emoji} {worker['nombre_completo']}{info_extra}"
        )
    
    if len(workers) > max_mostrar:
        lineas.append(f"\n... y {len(workers) - max_mostrar} más")
    
    lineas.append(f"\n💡 Escribe:")
    lineas.append(f"• Número (1-{min(len(workers), max_mostrar)})")
    lineas.append(f"• Apellido completo")
    lineas.append(f"• 'Cancelar' para abortar")
    
    return "\n".join(lineas)


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