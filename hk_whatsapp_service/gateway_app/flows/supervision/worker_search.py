"""
Sistema de búsqueda inteligente de mucamas con fuzzy matching.
Maneja nombres duplicados, apodos, typos y confirmaciones.
"""

from typing import List, Dict, Any, Optional
from difflib import SequenceMatcher


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


def buscar_mucamas(nombre_query: str, mucamas: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Busca mucamas por nombre con tolerancia a errores.
    
    Args:
        nombre_query: Nombre a buscar (puede tener typos)
        mucamas: Lista de mucamas disponibles
    
    Returns:
        Lista de mucamas encontradas, ordenadas por relevancia
    
    Ejemplos:
        >>> buscar_mucamas("María", mucamas)
        [María González, María López, María Pérez]
        
        >>> buscar_mucamas("Mria", mucamas)  # typo
        [María González, María López]
        
        >>> buscar_mucamas("Mari", mucamas)  # apodo
        [María González]
        
        >>> buscar_mucamas("González", mucamas)  # apellido
        [María González]
    """
    nombre_query = nombre_query.lower().strip()
    candidatos = []
    
    for mucama in mucamas:
        score = 0.0
        match_type = None
        
        # 1. Búsqueda exacta en nombre
        if mucama.get("nombre", "").lower() == nombre_query:
            score = 1.0
            match_type = "exact_name"
        
        # 2. Búsqueda exacta en apellido
        elif mucama.get("apellido", "").lower() == nombre_query:
            score = 1.0
            match_type = "exact_surname"
        
        # 3. Búsqueda en nombre completo
        elif nombre_query in mucama.get("nombre_completo", "").lower():
            score = 0.95
            match_type = "contains"
        
        # 4. Búsqueda en apodos
        elif any(nombre_query == apodo.lower() for apodo in mucama.get("apodos", [])):
            score = 0.95
            match_type = "nickname"
        
        # 5. Fuzzy matching en nombre (tolerancia a typos)
        else:
            nombre_sim = similarity(nombre_query, mucama.get("nombre", ""))
            apellido_sim = similarity(nombre_query, mucama.get("apellido", ""))
            completo_sim = similarity(nombre_query, mucama.get("nombre_completo", ""))
            
            # Tomar la mejor similitud
            score = max(nombre_sim, apellido_sim, completo_sim)
            
            # Solo considerar si similitud >= 0.6 (60%)
            if score >= 0.6:
                match_type = "fuzzy"
        
        if score > 0:
            candidatos.append({
                **mucama,
                "match_score": score,
                "match_type": match_type
            })
    
    # Ordenar por score (mayor primero)
    candidatos.sort(key=lambda x: x["match_score"], reverse=True)
    
    return candidatos


def formato_lista_mucamas(mucamas: List[Dict[str, Any]], max_mostrar: int = 5) -> str:
    """
    Formatea lista de mucamas para mostrar al supervisor.
    
    Args:
        mucamas: Lista de mucamas encontradas
        max_mostrar: Máximo número a mostrar
    
    Returns:
        Texto formateado
    """
    if not mucamas:
        return "❌ No encontré a nadie con ese nombre"
    
    if len(mucamas) == 1:
        # Solo una: confirmar directamente
        mucama = mucamas[0]
        estado_emoji = {
            "disponible": "✅",
            "ocupada": "🔴",
            "en_pausa": "⏸️"
        }.get(mucama.get("estado"), "❓")
        
        return f"""📋 Encontré a:
{estado_emoji} {mucama['nombre_completo']}

💡 Escribe 'sí' para confirmar o 'no' para cancelar"""
    
    # Múltiples resultados
    lineas = [f"📋 Encontré {len(mucamas)} personas:\n"]
    
    for i, mucama in enumerate(mucamas[:max_mostrar], 1):
        estado_emoji = {
            "disponible": "✅",
            "ocupada": "🔴",
            "en_pausa": "⏸️"
        }.get(mucama.get("estado"), "❓")
        
        # Info adicional según estado
        info_extra = ""
        if mucama.get("estado") == "ocupada" and mucama.get("ticket_activo"):
            info_extra = f" (en ticket #{mucama['ticket_activo']})"
        elif mucama.get("promedio_tiempo_resolucion"):
            info_extra = f" ({mucama['promedio_tiempo_resolucion']:.0f} min promedio)"
        
        lineas.append(
            f"{i}. {estado_emoji} {mucama['nombre_completo']}{info_extra}"
        )
    
    if len(mucamas) > max_mostrar:
        lineas.append(f"\n... y {len(mucamas) - max_mostrar} más")
    
    lineas.append("\n💡 Di el número (1, 2, 3...) o apellido")
    
    return "\n".join(lineas)


def manejar_seleccion_mucama(
    texto: str,
    mucamas_disponibles: List[Dict[str, Any]]
) -> Optional[Dict[str, Any]]:
    """
    Maneja la selección de mucama cuando hay múltiples opciones.
    
    Args:
        texto: Texto del supervisor (número o apellido)
        mucamas_disponibles: Lista de mucamas entre las que elegir
    
    Returns:
        Mucama seleccionada o None
    """
    texto = texto.strip().lower()
    
    # Caso 1: Selección por número
    if texto.isdigit():
        index = int(texto) - 1
        if 0 <= index < len(mucamas_disponibles):
            return mucamas_disponibles[index]
        return None
    
    # Caso 2: Selección por apellido
    for mucama in mucamas_disponibles:
        if texto in mucama.get("apellido", "").lower():
            return mucama
    
    # Caso 3: Búsqueda fuzzy entre las disponibles
    resultados = buscar_mucamas(texto, mucamas_disponibles)
    if resultados and resultados[0]["match_score"] > 0.8:
        return resultados[0]
    
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