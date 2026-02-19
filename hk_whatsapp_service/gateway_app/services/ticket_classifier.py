"""
ticket_classifier.py
====================
Clasificación inteligente de tickets usando OpenAI con fallback heurístico.

Responsabilidad única: dado un texto de descripción + ubicación,
devolver área, prioridad, razón y confianza.

Uso:
    from gateway_app.services.ticket_classifier import clasificar_ticket

    resultado = clasificar_ticket(
        detalle="Se rompió el grifo del baño y hay agua en el suelo",
        ubicacion="204"
    )
    # → {"area": "MANTENIMIENTO", "prioridad": "ALTA",
    #    "routing_reason": "Fuga de agua activa requiere atención inmediata",
    #    "routing_confidence": 0.95, "routing_source": "llm_v1"}
"""

import json
import logging
import os
import re

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────
# Constantes del dominio
# ─────────────────────────────────────────────

AREAS_VALIDAS = {"HOUSEKEEPING", "AREAS_COMUNES", "MANTENIMIENTO", "RECEPCION", "ROOMSERVICE"}
PRIORIDADES_VALIDAS = {"BAJA", "MEDIA", "ALTA", "URGENTE"}

AREA_DEFAULT = "HOUSEKEEPING"
PRIORIDAD_DEFAULT = "MEDIA"

ROUTING_VERSION = "llm_v1"

# ─────────────────────────────────────────────
# Prompt del clasificador
# ─────────────────────────────────────────────

SYSTEM_PROMPT = """Eres un clasificador de incidencias para hoteles.
Tu tarea es analizar la descripción de un problema reportado por un trabajador o supervisor
y devolver exactamente un objeto JSON con estos 4 campos:

{
  "area": <string>,
  "prioridad": <string>,
  "razon": <string de máximo 100 caracteres explicando el criterio>,
  "confianza": <número entre 0.0 y 1.0>
}

ÁREAS VÁLIDAS y cuándo usarlas:
- HOUSEKEEPING: limpieza de habitaciones, cambio de sábanas/toallas, amenidades faltantes,
  habitación sucia, cama sin hacer, basura en habitación.
- MANTENIMIENTO: cualquier cosa rota, fuga de agua, instalaciones eléctricas, 
  aire acondicionado, calefacción, cerraduras, ascensores, plomería, fugas, goteras,
  luces fundidas, TV rota, caja fuerte bloqueada, problemas técnicos de equipamiento.
- AREAS_COMUNES: limpieza o incidencias en lobby, pasillos, elevadores, piscina,
  gimnasio, restaurante, estacionamiento, jardín, áreas exteriores.
- RECEPCION: solicitudes del huésped que requieren gestión administrativa: extensión
  de checkout, cambio de habitación, cobros, facturas, quejas formales, solicitud de información.
- ROOMSERVICE: pedidos de comida o bebida a la habitación, minibar, servicio a cuartos.

PRIORIDADES y cuándo usarlas:
- URGENTE: riesgo de seguridad o salud inmediata: incendio, inundación activa, 
  accidente, gas, huésped atrapado, fuga de agua con daño activo, emergencia médica.
- ALTA: el huésped no puede usar la habitación o servicio principal: 
  no hay agua caliente, AC roto en clima extremo, cerradura sin funcionar,
  TV principal sin funcionar, limpieza urgente antes de nuevo check-in.
- MEDIA: molestia significativa pero no bloquea el servicio: ruido, olor,
  amenidad faltante, solicitud pendiente hace tiempo.
- BAJA: solicitud cosmética o de bajo impacto: lámpara de ambiente fundida, 
  solicitud de almohada extra, detalle menor estético.

REGLAS:
1. Devuelve SOLO el JSON, sin texto adicional, sin markdown, sin explicaciones.
2. Si la descripción es ambigua, elige el área más probable y baja la confianza.
3. La razón debe ser concisa y en español.
4. Si el trabajador que reporta pertenece a HOUSEKEEPING pero el problema es una fuga,
   el área debe ser MANTENIMIENTO de todas formas — clasifica el PROBLEMA, no al trabajador."""

USER_TEMPLATE = """Descripción del problema: "{detalle}"
Ubicación: "{ubicacion}"
Área del trabajador que reporta: "{area_worker}" """


# ─────────────────────────────────────────────
# Función principal
# ─────────────────────────────────────────────

def clasificar_ticket(
    detalle: str,
    ubicacion: str = "",
    area_worker: str = "",
) -> dict:
    """
    Clasifica un ticket usando OpenAI.
    Si la llamada falla, hace fallback a heurística.

    Args:
        detalle:     Texto libre que describió el trabajador.
        ubicacion:   Número de habitación o nombre de área ("204", "lobby").
        area_worker: Área del usuario que reporta (hint contextual, no determinante).

    Returns:
        dict con claves:
            area              (str)   — una de AREAS_VALIDAS
            prioridad         (str)   — una de PRIORIDADES_VALIDAS
            routing_reason    (str)   — explicación corta
            routing_confidence(float) — 0.0 a 1.0
            routing_source    (str)   — "llm_v1" o "heuristic_v1"
    """
    try:
        resultado = _clasificar_con_llm(detalle, ubicacion, area_worker)
        logger.info(
            "🧠 Clasificación LLM | area=%s | prioridad=%s | confianza=%.2f | razon=%s",
            resultado["area"], resultado["prioridad"],
            resultado["routing_confidence"], resultado["routing_reason"]
        )
        return resultado
    except Exception as exc:
        logger.warning("⚠️ Clasificación LLM falló (%s), usando heurística", exc)
        resultado = _clasificar_heuristico(detalle, ubicacion, area_worker)
        logger.info(
            "🔧 Clasificación heurística | area=%s | prioridad=%s",
            resultado["area"], resultado["prioridad"]
        )
        return resultado


# ─────────────────────────────────────────────
# Clasificador LLM
# ─────────────────────────────────────────────

def _clasificar_con_llm(detalle: str, ubicacion: str, area_worker: str) -> dict:
    """Llama a OpenAI y parsea la respuesta."""
    import openai  # import local para no romper si no está instalado

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY no configurada")

    client = openai.OpenAI(api_key=api_key)

    user_msg = USER_TEMPLATE.format(
        detalle=detalle.strip(),
        ubicacion=ubicacion or "no especificada",
        area_worker=area_worker or "no especificada",
    )

    response = client.chat.completions.create(
        model="gpt-4o-mini",          # Rápido y barato — ideal para clasificación
        temperature=0,                 # Queremos determinismo, no creatividad
        max_tokens=200,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user",   "content": user_msg},
        ],
    )

    raw = response.choices[0].message.content.strip()

    # Limpiar markdown si el modelo los incluyó (defensivo)
    raw = re.sub(r"^```json\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw)

    datos = json.loads(raw)

    # Validar y normalizar los valores devueltos
    area = datos.get("area", "").upper()
    if area not in AREAS_VALIDAS:
        logger.warning("LLM devolvió área inválida '%s', usando heurística de fallback", area)
        area = _inferir_area_heuristica(detalle, ubicacion, area_worker)

    prioridad = datos.get("prioridad", "").upper()
    if prioridad not in PRIORIDADES_VALIDAS:
        logger.warning("LLM devolvió prioridad inválida '%s', usando MEDIA", prioridad)
        prioridad = PRIORIDAD_DEFAULT

    confianza = float(datos.get("confianza", 0.8))
    confianza = max(0.0, min(1.0, confianza))  # clamp a [0, 1]

    razon = str(datos.get("razon", ""))[:200]  # truncar por seguridad

    return {
        "area": area,
        "prioridad": prioridad,
        "routing_reason": razon,
        "routing_confidence": confianza,
        "routing_source": ROUTING_VERSION,
    }


# ─────────────────────────────────────────────
# Clasificador heurístico (fallback)
# ─────────────────────────────────────────────

def _clasificar_heuristico(detalle: str, ubicacion: str, area_worker: str) -> dict:
    """
    Clasificación basada en reglas keyword.
    Se usa cuando OpenAI no está disponible o falla.
    Mucho más completo que la lógica original (que solo miraba si ubicacion era dígito).
    """
    area = _inferir_area_heuristica(detalle, ubicacion, area_worker)
    prioridad = _inferir_prioridad_heuristica(detalle)

    return {
        "area": area,
        "prioridad": prioridad,
        "routing_reason": "Clasificación automática por reglas de keywords",
        "routing_confidence": 0.55,  # confianza baja — indica que fue heurística
        "routing_source": "heuristic_v1",
    }


def _inferir_area_heuristica(detalle: str, ubicacion: str, area_worker: str) -> str:
    """Infiere el área a partir de keywords en el texto."""
    texto = (detalle + " " + ubicacion).lower()

    # MANTENIMIENTO — tiene prioridad alta: si hay un problema físico/técnico,
    # es mantenimiento aunque el trabajador sea de housekeeping
    keywords_mantenimiento = [
        "roto", "rota", "rotos", "rotas",
        "fuga", "fuge", "gotera", "gotea", "inundación", "inundado",
        "no funciona", "no enciende", "no prende", "no enfría", "no calienta",
        "cerradura", "llave", "puerta", "cerrojo", "trancada",
        "ascensor", "elevador",
        "luz", "foco", "bombilla", "interruptor", "electricidad",
        "aire", "ac", "calefacción", "calefactor", "temperatura",
        "tv", "televisión", "televisor", "control remoto",
        "caja fuerte", "safe",
        "ducha", "grifo", "llave de agua", "wc", "inodoro", "desagüe",
        "plomería", "tubería", "cañería",
        "colchón", "cama rota", "silla rota", "mesa rota",
        "ventana", "persiana", "cortina atascada",
        "wifi", "internet", "teléfono fijo",
        "gas",
    ]

    keywords_roomservice = [
        "comida", "comer", "almuerzo", "desayuno", "cena", "pizza",
        "bebida", "café", "agua mineral", "vino", "cerveza",
        "minibar", "room service", "menú", "pedido",
        "hambre", "servicio a la habitación",
    ]

    keywords_recepcion = [
        "checkout", "check out", "check-out", "factura", "cobro", "cargo",
        "cambio de habitación", "queja", "reclamación", "reembolso",
        "extensión", "late checkout", "documento", "llave nueva",
        "registro", "check in", "check-in",
    ]

    keywords_areas_comunes = [
        "lobby", "pasillo", "recepción", "escalera", "escaleras",
        "piscina", "alberca", "jacuzzi", "spa", "gimnasio", "gym",
        "restaurante", "bar", "terraza", "jardín", "jardines",
        "estacionamiento", "parking", "garaje",
        "sala de reuniones", "conference", "sala",
        "área común", "zona común",
    ]

    keywords_housekeeping = [
        "sábanas", "toallas", "limpieza", "limpiar",
        "basura", "suciedad", "sucio", "sucia",
        "amenidades", "shampoo", "jabón", "papel higiénico",
        "cama", "almohada", "cobija", "frazada", "manta",
        "habitación sucia", "hacer la habitación", "turn down",
    ]

    if any(k in texto for k in keywords_mantenimiento):
        return "MANTENIMIENTO"
    if any(k in texto for k in keywords_roomservice):
        return "ROOMSERVICE"
    if any(k in texto for k in keywords_recepcion):
        return "RECEPCION"
    if any(k in texto for k in keywords_areas_comunes):
        return "AREAS_COMUNES"
    if any(k in texto for k in keywords_housekeeping):
        return "HOUSEKEEPING"

    # Fallback por área del trabajador (solo si no encontramos nada más)
    if area_worker:
        area_norm = area_worker.upper()
        if area_norm in AREAS_VALIDAS:
            return area_norm

    # Último recurso: si la ubicación parece número de habitación → HOUSEKEEPING
    if ubicacion and str(ubicacion).isdigit():
        return "HOUSEKEEPING"

    return AREA_DEFAULT


def _inferir_prioridad_heuristica(detalle: str) -> str:
    """Infiere prioridad por keywords. Mucho más completo que la versión original."""
    texto = detalle.lower()

    keywords_urgente = [
        "incendio", "fuego", "humo",
        "inundación", "inundado", "desbordó",
        "gas", "olor a gas",
        "accidente", "herido", "herida", "sangre",
        "emergencia", "atrapado", "atrapada",
        "no respira", "desmayo",
        "fuga activa", "agua por todos lados",
    ]

    keywords_alta = [
        "urgente", "urgente!",
        "sin agua caliente", "no hay agua caliente",
        "cerradura rota", "no puedo entrar", "no abre",
        "ac roto", "no enfría", "no calienta", "hace mucho calor", "hace mucho frío",
        "no hay agua", "sin agua",
        "check in", "llega en", "llega a las", "check-in en",  # limpieza urgente
        "ya", "ahora mismo", "inmediatamente",
        "cliente esperando", "huésped esperando",
        "grave", "serio",
    ]

    keywords_baja = [
        "cuando puedas", "cuando tengas tiempo",
        "no urgente", "sin prisa", "con calma",
        "después", "mañana si puedes",
        "menor", "detalle pequeño", "cosita",
        "bombilla decorativa", "lámpara de ambiente",
    ]

    if any(k in texto for k in keywords_urgente):
        return "URGENTE"
    if any(k in texto for k in keywords_alta):
        return "ALTA"
    if any(k in texto for k in keywords_baja):
        return "BAJA"
    return "MEDIA"