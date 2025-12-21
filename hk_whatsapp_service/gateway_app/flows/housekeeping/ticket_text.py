from typing import Dict, Any
import re

from .outgoing import send_whatsapp
from .ui import texto_menu_principal

# =========================
#   CREACIÓN DE TICKETS
# =========================

def crear_ticket_desde_mucama(phone: str, texto: str, state: Dict[str, Any]):
    """
    Crea un ticket nuevo a partir de texto libre de la mucama.
    Aquí se puede parsear habitación, tipo de problema, etc.
    En producción, esto llamaría a la API real de creación de tickets.
    """
    texto = (texto or "").strip()
    if not texto:
        send_whatsapp(
            phone,
            "No entendí el problema. Describe brevemente qué sucede en la habitación o área."
        )
        return

    # Mini intento de extraer un número de habitación (cualquier grupo de dígitos).
    room = None
    for token in texto.split():
        digits = "".join(ch for ch in token if ch.isdigit())
        if digits:
            room = digits
            break

    if room:
        send_whatsapp(
            phone,
            f"✅ Ticket creado (demo) para la habitación {room}:\n“{texto}”.\n\n"
            "El supervisor y recepción lo verán en el sistema."
        )
    else:
        send_whatsapp(
            phone,
            f"✅ Ticket creado (demo):\n“{texto}”.\n\n"
            "El supervisor y recepción lo verán en el sistema."
        )

    # Después de crear, volvemos al menú principal
    state["menu_state"] = "M1" if state["turno_activo"] else "M0"

def crear_ticket_adicional(phone: str, texto: str, state: Dict[str, Any]):
    """
    Crea un ticket adicional mientras hay otro ticket en ejecución (S1),
    por ejemplo: "la habitación 313 también quiere una toalla".
    """
    crear_ticket_desde_mucama(phone, texto, state)
# =========================
#   INTERPRETACIÓN DE TEXTO DE TICKET
# =========================

TICKET_STOPWORDS = {
    "en", "la", "el", "los", "las", "de", "del", "al", "a",
    "y", "para", "por", "con", "hab", "habitacion", "habitación",
    "pieza", "cuarto", "no", "hay"
}

ISSUE_KEYWORDS = [
    "toalla", "toallas",
    "sucio", "sucia", "sucias", "sucios",
    "suciedad", "limpiar", "limpieza",
    "papel", "higienico", "higiénico",
    "falta", "faltan", "no hay",
    "ruido", "ruidoso", "ruidosa",
    "roto", "rota", "rotas", "rotos",
    "cambiar", "arreglar", "averia", "avería",
    "mantencion", "mantención",
    "aire", "calefaccion", "calefacción",
    "cama", "almohada", "almohadas"
]
# Palabras de problema “débiles” que por sí solas NO bastan
WEAK_ISSUE_KEYWORDS = {"falta", "faltan", "no hay"}


def analizar_texto_ticket(texto: str):
    """
    Devuelve (tiene_habitacion, tiene_problema) usando reglas simples.
    - tiene_habitacion: si hay algún dígito en el texto.
    - tiene_problema: si detectamos un problema “suficientemente completo”.
    """
    texto_l = texto.lower()
    tokens = [tok.strip(".,;:!¿?") for tok in texto_l.split() if tok.strip(".,;:!¿?")]

    # ¿Hay algún dígito? → asumimos que es número de habitación
    tiene_habitacion = any(ch.isdigit() for ch in texto_l)

    # Palabras con letras (sin contar números puros)
    tokens_letras = [tok for tok in tokens if any(ch.isalpha() for ch in tok)]
    # Quitamos conectores muy básicos
    contenido = [tok for tok in tokens_letras if tok not in TICKET_STOPWORDS]
    # Quitamos además las “palabras débiles” tipo 'falta', 'faltan', 'no hay'
    contenido_sin_weak = [tok for tok in contenido if tok not in WEAK_ISSUE_KEYWORDS]

    # ¿Hay keywords fuertes o débiles?
    has_strong_kw = any(
        kw in texto_l
        for kw in ISSUE_KEYWORDS
        if kw not in WEAK_ISSUE_KEYWORDS
    )
    has_weak_kw = any(kw in texto_l for kw in WEAK_ISSUE_KEYWORDS)

    # Palabras de contenido “largas” sin contar las débiles
    palabras_largas = [tok for tok in contenido_sin_weak if len(tok) >= 4]

    # Criterio de “problema completo”:
    #  - keyword fuerte (ej: toallas, sucio, papel, etc.), O
    #  - al menos 2 palabras de contenido, O
    #  - keyword débil + al menos 1 palabra de contenido adicional (ej: "faltan toallas")
    tiene_problema = bool(
        has_strong_kw
        or len(palabras_largas) >= 2
        or (has_weak_kw and len(palabras_largas) >= 1)
    )

    return tiene_habitacion, tiene_problema

def extraer_habitacion(texto: str) -> str | None:
    """
    Busca el primer grupo de dígitos en el texto para mostrarlo en mensajes.
    """
    for token in texto.split():
        digits = "".join(ch for ch in token if ch.isdigit())
        if digits:
            return digits
    return None

def _manejar_ticket_libre(
    phone: str,
    texto: str,
    state: Dict[str, Any],
    *,
    adicional: bool = False
) -> bool:
    """
    Maneja creación de tickets en lenguaje natural desde CUALQUIER parte del flujo.

    Lógica:
      - Acumula texto en state["ticket_draft_text"].
      - Solo crea ticket cuando detecta habitación Y problema.
      - Si solo ve habitación → pregunta qué pasa.
      - Si solo ve problema → pide la habitación.

    Retorna True si se trató como parte del flujo de ticket (para que
    quien llama no haga nada más con ese mensaje).
    """
    texto = (texto or "").strip()
    if not texto:
        return False

    # Permitir cancelar explícitamente el borrador
    if texto.upper() in {"CANCELAR TICKET", "CANCELAR PROBLEMA"}:
        if state.get("ticket_draft_text"):
            state["ticket_draft_text"] = None
            send_whatsapp(
                phone,
                "Listo, descarté el problema que estabas describiendo."
            )
            return True
        return False

    draft = state.get("ticket_draft_text") or ""
    combined = (draft + " " + texto).strip() if draft else texto

    tiene_hab, tiene_prob = analizar_texto_ticket(combined)

    # 1) No tenemos ni habitación ni problema claro → solo acumulamos
    if not tiene_hab and not tiene_prob:
        state["ticket_draft_text"] = combined
        if not draft:
            send_whatsapp(
                phone,
                "Entendí que quieres reportar algo.\n"
                "Cuéntame qué pasa y en qué habitación."
            )
        return True

    # 2) Solo problema (falta la habitación)
    if tiene_prob and not tiene_hab:
        state["ticket_draft_text"] = combined
        if not draft:
            send_whatsapp(
                phone,
                "Entendí el problema. ¿En qué habitación es?"
            )
        return True

    # 3) Solo habitación (falta el problema)
    if tiene_hab and not tiene_prob:
        state["ticket_draft_text"] = combined
        if not draft:
            hab = extraer_habitacion(combined)
            if hab:
                send_whatsapp(
                    phone,
                    f"Anoté la habitación {hab}. ¿Qué sucede ahí?"
                )
            else:
                send_whatsapp(
                    phone,
                    "Anoté la habitación. ¿Qué sucede ahí?"
                )
        return True

    # 4) Tenemos habitación + problema → ahora sí creamos ticket
    if adicional:
        crear_ticket_adicional(phone, combined, state)
    else:
        crear_ticket_desde_mucama(phone, combined, state)
        send_whatsapp(
            phone,
            "\nVolviendo al menú principal.\n\n" + texto_menu_principal(state)
        )

    state["ticket_draft_text"] = None
    return True
