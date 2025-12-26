from typing import Dict, Any
from datetime import date, datetime, timedelta
import re
import time

from hk_whatsapp_service.gateway_app.flows.housekeeping.ticket_flow import _handle_ticket_flow
from hk_whatsapp_service.gateway_app.flows.housekeeping.ui import texto_menu_principal
from .reminders import maybe_send_recordatorio_pendientes


# =========================
#   ESTADO EN MEMORIA
# =========================

USER_STATE: Dict[str, Dict[str, Any]] = {}


def get_user_state(phone: str) -> Dict[str, Any]:
    """Obtiene o inicializa el estado de una mucama."""
    if phone not in USER_STATE:
        USER_STATE[phone] = {
            # Turno
            "turno_activo": False,        # False = M0, True = M1
            "menu_state": "M0",           # "M0", "M1", "M2", "M3"
            # Flujo de tickets
            "ticket_state": None,         # None, "S0", "S1", "S2"
            "ticket_activo": None,        # dict con datos de ticket actual
            # Saludos
            "last_greet_date": None,      # str ISO con la fecha del último saludo
            # Recordatorios automáticos
            "last_reminder_ts": None,     # timestamp (float) del último recordatorio
            # Borrador de ticket en lenguaje natural
            "ticket_draft_text": None,    # str con el texto acumulado
        }
    return USER_STATE[phone]


def send_whatsapp(to: str, body: str):
    """
    En producción esto enviaría un WhatsApp.
    En el simulador, hk_cli_simulator.py sobreescribe esta función.
    """
    print(f"[FAKE SEND] → {to}: {body}")

def maybe_route_ticket_command_anywhere(phone: str, text: str, state: dict) -> bool:
    """
    Permite manejar comandos del ticket activo desde cualquier parte (menú, M0/M1/M2/M3, etc).
    Si hay ticket_activo, y llega un comando tipo 'fin/pausar/reanudar/supervisor',
    forzamos ticket_state = 'S1' y delegamos en handle_ticket_flow.
    """
    if state.get("ticket_activo") is None:
        return False

    t = (text or "").strip().lower()
    if t in {"fin", "terminar", "cerrar", "pausar", "reanudar", "supervisor"}:
        # Aseguramos que el ticket_flow lo procese como ejecución (S1)
        state["ticket_state"] = "S1"
        handle_ticket_flow(phone, text, state)
        return True

    return False

# =========================
#   HELPERS DE TEXTO
# =========================

def _texto_menu_principal(state: Dict[str, Any]) -> str:
    """Construye el texto del menú según si el turno está activo o no."""
    linea_turno = "🟢 Turno ACTIVO" if state["turno_activo"] else "⚪️ Sin turno activo"
    # Texto dinámico para la opción 1
    opcion_turno = "1) Iniciar turno" if not state["turno_activo"] else "1) Finalizar turno"

    return (
        f"{linea_turno}\n\n"
        "🏨 Menú Housekeeping\n"
        f"{opcion_turno}\n"
        "2) Tickets por resolver\n"
        "3) Crear ticket / reportar problema\n"
        "4) Ayuda / contactar supervisor\n\n"
        "Escribe el número de opción o 'M' para ver este menú de nuevo."
    )


# =========================
#   DEMO TICKETS
# =========================

DEMO_TICKETS = [
    {
        "id": 1010,
        "room": "312",
        "detalle": "Toallas adicionales",
        "prioridad": "MEDIA",
        "created_at": datetime.now() - timedelta(minutes=35),
        "esfuerzo": "FACIL",   # FACIL | MEDIO | DIFICIL
    },
    {
        "id": 1011,
        "room": "221",
        "detalle": "Limpieza rápida",
        "prioridad": "ALTA",
        "created_at": datetime.now() - timedelta(minutes=10),
        "esfuerzo": "MEDIO",
    },
]

# Cada cuánto tiempo podemos mandar un recordatorio (en segundos)
REMINDER_INTERVAL_SECONDS = 5 * 60  # 5 minutos


def _hay_tickets_pendientes(state: Dict[str, Any]) -> bool:
    """
    DEMO: consideramos que hay tickets pendientes si existe al menos
    un ticket en DEMO_TICKETS.

    En producción, aquí se debería consultar la base de datos para ver si
    la mucama tiene tickets asignados o disponibles.
    """
    return bool(DEMO_TICKETS)

# =========================
#   INTERPRETACIÓN S0 (ACEPTAR/RECHAZAR) + PRIORIZACIÓN
# =========================

ACCEPT_PHRASES = {
    "aceptar", "acepto", "aceptado",
    "tomar ticket", "tomar el ticket", "tomar", "tomo",
    "agarrar", "agarro",
    "me lo llevo", "me hago cargo", "me encargo",
    "lo tomo", "lo hago", "voy con ese", "voy con ese ticket",
    "ok", "oka", "okey", "dale", "listo", "ya", "de acuerdo",
}

REJECT_PHRASES = {
    "rechazar", "rechazo", "rechazado",
    "derivar", "derivo", "derivado",
    "no puedo", "no alcanzo", "paso", "siguiente",
}

def _norm(s: str) -> str:
    s = (s or "").strip().lower()
    s = re.sub(r"\s+", " ", s)
    return s

def _match_frase(text: str, frases: set[str]) -> bool:
    t = _norm(text)
    return any(frase in t for frase in frases)

def _es_aceptacion_ticket(text: str) -> bool:
    t = _norm(text)
    # Evita falsos positivos tipo "no acepto", "no lo tomo"
    if ("no acept" in t) or ("no lo tomo" in t) or ("no tomar" in t) or ("no tomo" in t):
        return False
    return _match_frase(t, ACCEPT_PHRASES)

def _es_rechazo_ticket(text: str) -> bool:
    return _match_frase(text, REJECT_PHRASES)

def _extraer_id_ticket_en_texto(text: str) -> int | None:
    """
    Permite escribir: '#1011' o '1011' para elegir ticket específico.
    """
    t = _norm(text)
    m = re.search(r"#?\b(\d{3,6})\b", t)
    if not m:
        return None
    try:
        return int(m.group(1))
    except:
        return None

PRIORIDAD_PESO = {"ALTA": 100, "MEDIA": 60, "BAJA": 30}
ESFUERZO_PESO = {"FACIL": 25, "MEDIO": 10, "DIFICIL": 0}

def _score_ticket(t: Dict[str, Any]) -> float:
    p = PRIORIDAD_PESO.get((t.get("prioridad") or "").upper(), 0)

    created_at = t.get("created_at")
    if isinstance(created_at, datetime):
        age_min = (datetime.now() - created_at).total_seconds() / 60.0
    else:
        age_min = 0.0

    e = ESFUERZO_PESO.get((t.get("esfuerzo") or "MEDIO").upper(), 10)

    # Ajusta pesos a gusto:
    return (p * 1.0) + (age_min * 0.8) + (e * 1.0)

def _elegir_mejor_ticket(tickets: list[Dict[str, Any]]) -> Dict[str, Any] | None:
    if not tickets:
        return None
    return max(tickets, key=_score_ticket)

def _mock_listado_tickets_por_resolver() -> str:
    lines = ["Tickets por resolver (demo):"]

    ordered = sorted(DEMO_TICKETS, key=_score_ticket, reverse=True)

    for t in ordered:
        created_at = t.get("created_at")
        if isinstance(created_at, datetime):
            age_min = int((datetime.now() - created_at).total_seconds() / 60)
            age_txt = f"hace {age_min} min"
        else:
            age_txt = "sin hora"

        esfuerzo = t.get("esfuerzo", "MEDIO")
        lines.append(
            f"- #{t['id']} / Hab. {t['room']} / {t['detalle']} / prioridad {t['prioridad']} / {age_txt} / {esfuerzo}"
        )

    lines.append(
        "\nPuedes responder por ejemplo:\n"
        "- 'aceptar' / 'tomar ticket' / 'ok lo tomo'\n"
        "- 'rechazar' / 'derivar'\n"
        "O escribir el ID: '#1011' para elegir uno específico."
    )
    return "\n".join(lines)


# =========================
#   CREACIÓN DE TICKETS
# =========================

def _crear_ticket_desde_mucama(phone: str, texto: str, state: Dict[str, Any]):
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


def _crear_ticket_adicional(phone: str, texto: str, state: Dict[str, Any]):
    """
    Crea un ticket adicional mientras hay otro ticket en ejecución (S1),
    por ejemplo: "la habitación 313 también quiere una toalla".
    """
    _crear_ticket_desde_mucama(phone, texto, state)
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


def _analizar_texto_ticket(texto: str):
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

def _extraer_habitacion(texto: str) -> str | None:
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

    tiene_hab, tiene_prob = _analizar_texto_ticket(combined)

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
            hab = _extraer_habitacion(combined)
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
        _crear_ticket_adicional(phone, combined, state)
    else:
        _crear_ticket_desde_mucama(phone, combined, state)
        send_whatsapp(
            phone,
            "\nVolviendo al menú principal.\n\n" + _texto_menu_principal(state)
        )

    state["ticket_draft_text"] = None
    return True
# =========================
#   FLUJO DE TICKETS S0/S1/S2
# =========================
def handle_ticket_flow(phone: str, text: str, state: Dict[str, Any]) -> None:
    """
    Maneja el flujo de tickets (S0/S1/S2).
    Se llama SOLO cuando state["ticket_state"] no es None.
    """
    if state.get("ticket_state") is None:
        return

    raw = (text or "").strip()
    t = raw.lower()
    s = state.get("ticket_state")

    # Atajo: volver al menú sin alterar el ticket activo (solo sales de la "conversación" del ticket)
    if raw.upper() in {"M", "MENU"}:
        state["ticket_state"] = None
        send_whatsapp(
            phone,
            "Te muestro el menú de Housekeeping.\n"
            "El ticket que aceptaste sigue en ejecución (demo).\n"
            "Si más adelante quieres gestionarlo (pausar o terminar), "
            "puedes volver a la opción 2 'Tickets por resolver'.\n\n"
            + _texto_menu_principal(state)
        )
        return

    # Navegación rápida desde S0/S1: si escriben 1-4, salimos del ticket y vamos al menú
    if s in {"S0", "S1"} and t in {"1", "2", "3", "4"}:
        state["ticket_state"] = None
        send_whatsapp(phone, "Cambio de opción. Salgo de este ticket y voy al menú.\n")
        _handle_menu(phone, raw, state)
        return

    # =========================
    # S0: decisión (aceptar/rechazar/timeout)
    # =========================
    if s == "S0":
        if _es_aceptacion_ticket(raw):
            tid = _extraer_id_ticket_en_texto(raw)
            if tid is not None:
                elegido = next((x for x in DEMO_TICKETS if x.get("id") == tid), None)
            else:
                elegido = _elegir_mejor_ticket(DEMO_TICKETS)

            if not elegido:
                send_whatsapp(phone, "No encontré tickets pendientes para tomar (demo).")
                state["ticket_state"] = None
                state["ticket_activo"] = None
                return

            # (Opcional recomendado) sacar el ticket de la cola demo
            try:
                DEMO_TICKETS.remove(elegido)
            except ValueError:
                pass

            state["ticket_state"] = "S1"
            state["ticket_activo"] = {
                "id": elegido["id"],
                "room": elegido["room"],
                "detalle": elegido["detalle"],
                "prioridad": elegido["prioridad"],
                "paused": False,
                "started_at": datetime.now(),
            }

            send_whatsapp(
                phone,
                "✅ Has ACEPTADO un ticket (S1 - Ejecución).\n"
                f"Ticket #{elegido['id']} · Hab. {elegido['room']} · Prioridad {elegido['prioridad']}\n"
                f"Detalle: {elegido['detalle']}\n\n"
                "Comandos: 'pausar', 'fin', 'supervisor'.\n"
                "También puedes escribir texto libre para crear tickets adicionales."
            )
            return

        if _es_rechazo_ticket(raw):
            state["ticket_state"] = "S2"
            send_whatsapp(
                phone,
                "🚫 Has RECHAZADO/DERIVADO el ticket (S2 - Cierre).\n"
                "Volviendo al menú.\n\n" + _texto_menu_principal(state)
            )
            state["ticket_state"] = None
            state["ticket_activo"] = None
            return

        if t == "timeout":
            state["ticket_state"] = "S2"
            send_whatsapp(
                phone,
                "⌛ Timeout de ticket (S2 - Cierre por sistema).\n"
                "Volviendo al menú.\n\n" + _texto_menu_principal(state)
            )
            state["ticket_state"] = None
            state["ticket_activo"] = None
            return

        send_whatsapp(
            phone,
            "No entendí. En tickets por resolver (S0) puedes escribir por ejemplo:\n"
            "- 'aceptar' / 'tomar ticket' / 'ok lo tomo'\n"
            "- 'rechazar' / 'derivar'\n"
            "- '#1011' para elegir uno\n"
            "- 'timeout' (demo)\n"
        )
        return
    handle_ticket_flow = _handle_ticket_flow
    # =========================
    # S1: ejecución (EN_CURSO o PAUSADO)
    # =========================
    if s == "S1":
        ticket = state.get("ticket_activo") or {}
        paused = ticket.get("paused", False)

        # Comandos comunes
        if t in {"fin", "terminar", "cerrar"}:
            ticket_id = ticket.get("id", "—")
            room = ticket.get("room", "—")
            detalle = ticket.get("detalle", "")
            prioridad = ticket.get("prioridad", "—")

            started_at = ticket.get("started_at")
            if isinstance(started_at, datetime):
                elapsed = datetime.now() - started_at
                total_seconds = int(elapsed.total_seconds())
                minutes = total_seconds // 60
                if minutes <= 0:
                    tiempo_txt = "menos de 1 minuto"
                elif minutes == 1:
                    tiempo_txt = "1 minuto"
                else:
                    tiempo_txt = f"{minutes} minutos"
            else:
                tiempo_txt = "no disponible (demo)"

            state["ticket_state"] = "S2"

            send_whatsapp(
                phone,
                "✅ Ticket FINALIZADO (S2 - Cierre).\n"
                f"Ticket #{ticket_id} · Hab. {room} · Prioridad {prioridad}\n"
                f"Detalle: {detalle}\n"
                f"Tiempo de resolución (demo): {tiempo_txt}.\n\n"
                "Si todavía tienes otros tickets pendientes, recuerda ir a "
                "'Tickets por resolver' (opción 2) para continuar."
            )

            state["ticket_state"] = None
            state["ticket_activo"] = None
            return

        if t == "supervisor":
            send_whatsapp(
                phone,
                "🆘 Has pedido apoyo del supervisor (demo). "
                "El ticket sigue en el mismo estado."
            )
            return

        # Estado EN CURSO
        if not paused:
            if t == "pausar":
                ticket["paused"] = True
                state["ticket_activo"] = ticket
                send_whatsapp(
                    phone,
                    "⏸ Has PAUSADO la ejecución (demo).\n"
                    "Comandos ahora: 'reanudar', 'fin', 'supervisor'.\n"
                    "También puedes escribir texto libre para crear tickets adicionales."
                )
                return

            if t == "reanudar":
                send_whatsapp(
                    phone,
                    "Ya estabas en ejecución (no estabas pausada).\n"
                    "Comandos: 'pausar', 'fin', 'supervisor', "
                    "o texto libre para nuevos tickets indicando una habitación."
                )
                return

            if _manejar_ticket_libre(phone, text, state, adicional=True):
                return

            send_whatsapp(
                phone,
                "No reconocí ese comando.\n"
                "En ejecución (S1) puedes usar:\n"
                "- 'pausar', 'fin', 'supervisor'\n"
                "o describir un nuevo problema indicando habitación, por ejemplo:\n"
                "'la 415 necesita toallas'."
            )
            return

        # Estado PAUSADO
        if paused:
            if t == "reanudar":
                ticket["paused"] = False
                state["ticket_activo"] = ticket
                send_whatsapp(
                    phone,
                    "▶️ Has REANUDADO la ejecución (demo).\n"
                    "Comandos: 'pausar', 'fin', 'supervisor', "
                    "o texto libre para nuevos tickets."
                )
                return

            if t == "pausar":
                send_whatsapp(
                    phone,
                    "⏸ El ticket ya estaba PAUSADO (demo).\n"
                    "Usa 'reanudar', 'fin', 'supervisor', "
                    "o texto libre para nuevos tickets."
                )
                return

            if _manejar_ticket_libre(phone, text, state, adicional=True):
                return

            send_whatsapp(
                phone,
                "No reconocí ese comando.\n"
                "Con el ticket PAUSADO puedes usar:\n"
                "- 'reanudar', 'fin', 'supervisor'\n"
                "o describir un nuevo problema indicando habitación, por ejemplo:\n"
                "'la 415 necesita toallas'."
            )
            return

    # =========================
    # S2: cierre / salida (seguridad)
    # =========================
    if s == "S2":
        state["ticket_state"] = None
        state["ticket_activo"] = None
        send_whatsapp(
            phone,
            "🏁 TicketFlow finalizado. Volviendo al menú.\n\n" + _texto_menu_principal(state)
        )
        return


from datetime import date

# ======================================================
#   ORQUESTADOR (ENTRYPOINT) DEL FLUJO DE HOUSEKEEPING
# ======================================================

def handle_hk_message(from_phone: str, text: str) -> None:
    """
    Punto de entrada único para:
    - Simulador CLI
    - Webhook (producción)

    Orquesta:
    - Saludo 1 vez al día
    - Ticket flow (S0/S1/S2) si hay ticket activo
    - Menú (M0/M1/M2/M3) si no hay ticket activo
    - Recordatorios opcionales
    """
    state = get_user_state(from_phone)

    raw = (text or "").strip()

    # 0) Comandos globales del ticket activo (desde cualquier parte)
    if maybe_route_ticket_command_anywhere(from_phone, raw, state):
        return

    today_str = date.today().isoformat()

# Saludo solo si NO hay ticket activo (ni conversacional ni en ejecución)
    if (
        state.get("ticket_state") is None
        and state.get("ticket_activo") is None
        and state.get("last_greet_date") != today_str
    ):
        state["last_greet_date"] = today_str
        send_whatsapp(
            from_phone,
            "Hola, soy el asistente de Housekeeping de Hestia.\n"
            "Te ayudaré a organizar y resolver tus tareas de hoy.\n\n"
            + texto_menu_principal(state)
        )
        return


    # 1) Si hay un flujo de ticket activo, tiene prioridad
    if state.get("ticket_state") is not None:
        _handle_ticket_flow(from_phone, raw, state)
        return

    # 2) Si no hay ticket activo, manejamos menú
    _handle_menu(from_phone, raw, state)

    # 3) Recordatorio opcional (solo aplica si corresponde)
    maybe_send_recordatorio_pendientes(from_phone, state)


def hk_check_reminder(from_phone: str) -> None:
    """
    Pensado para un scheduler (cron) en producción.
    Se puede llamar cada minuto; la función interna respeta el intervalo real.
    """
    state = get_user_state(from_phone)
    maybe_send_recordatorio_pendientes(from_phone, state)


# (Opcional) Alias por compatibilidad si en algún lugar aún llaman al underscore:
_handle_hk_message = handle_hk_message

# =========================
#   MENÚ M0/M1/M2/M3
# =========================

def _handle_menu(phone: str, text: str, state: Dict[str, Any]):
    """
    Implementa el sub-diagrama 'Menú Housekeeping (PULL)'.
    M0 = sin turno activo
    M1 = turno activo
    M2 = creando ticket
    M3 = ayuda / supervisor
    """
    t = (text or "").strip()

    # Atajo global: 'M' o 'MENU' muestran el menú principal
    if t.upper() in {"M", "MENU"}:
        state["menu_state"] = "M1" if state["turno_activo"] else "M0"
        send_whatsapp(phone, _texto_menu_principal(state))
        return

    menu_state = state["menu_state"]

    # M0 / M1: menú principal
    if menu_state in {"M0", "M1"}:
        tlower = t.lower()
        if tlower == "1":
            # Iniciar / Finalizar turno
            if not state["turno_activo"]:
                state["turno_activo"] = True
                state["menu_state"] = "M1"
                send_whatsapp(
                    phone,
                    "✅ Has INICIADO tu turno.\n\n" + _texto_menu_principal(state)
                )
            else:
                state["turno_activo"] = False
                state["menu_state"] = "M0"
                send_whatsapp(
                    phone,
                    "✅ Has FINALIZADO tu turno.\n\n" + _texto_menu_principal(state)
                )
            return

        if tlower == "2":
            # Tickets por resolver
            if not state["turno_activo"]:
                # Auto-inicio de turno
                state["turno_activo"] = True
                state["menu_state"] = "M1"
                send_whatsapp(
                    phone,
                    "🔄 No tenías turno activo, lo he iniciado automáticamente.\n"
                )

            # Para el demo usamos siempre el primer ticket de la lista
            demo_ticket = _elegir_mejor_ticket(DEMO_TICKETS)
            if not demo_ticket:
                send_whatsapp(phone, "No hay tickets pendientes (demo).")
                return

            state["ticket_state"] = "S0"
            state["ticket_activo"] = {
                "id": demo_ticket["id"],
                "room": demo_ticket["room"],
                "detalle": demo_ticket["detalle"],
                "prioridad": demo_ticket["prioridad"],
                "paused": False,
            }

            send_whatsapp(
                phone,
                "📋 Tickets por resolver (S0)\n\n" + _mock_listado_tickets_por_resolver()
            )
            return

        if tlower == "3":
            # Crear ticket / problema
            state["menu_state"] = "M2"
            send_whatsapp(
                phone,
                "🆕 Crear ticket / reportar problema (M2).\n"
                "Describe brevemente qué sucede y, si puedes, indica la habitación.\n\n"
                "Ejemplo: 'La 415 necesita toallas y papel higiénico'.\n\n"
                "Si al final no quieres crear nada, escribe *cancelar* o *M* para volver al menú."
            )
            return

        if tlower == "4":
            # Ayuda / supervisor
            state["menu_state"] = "M3"
            send_whatsapp(
                phone,
                "🆘 Ayuda / supervisor (M3).\n"
                "Escribe el mensaje que quieras enviar al supervisor.\n\n"
                "Ejemplo: 'Tengo muchas habitaciones atrasadas, necesito apoyo'."
            )
            return

        # Fallback en menú principal: probar si es un problema nuevo
        if _manejar_ticket_libre(phone, text, state):
            return

        send_whatsapp(
            phone,
            "No entendí esa opción.\n\n" + _texto_menu_principal(state)
        )
        return

    # M2: crear ticket / problema
    if menu_state == "M2":
        # Navegación rápida: si la mucama escribe 1,2,3,4 cambiamos de opción
        if t in {"1", "2", "3", "4"}:
            state["menu_state"] = "M1" if state["turno_activo"] else "M0"
            send_whatsapp(
                phone,
                "Cambio de opción. Salgo de crear ticket y voy al menú.\n"
            )
            _handle_menu(phone, t, state)
            return

        if t.upper() in {"CANCELAR", "M", "MENU"}:
            state["menu_state"] = "M1" if state["turno_activo"] else "M0"
            send_whatsapp(
                phone,
                "❌ Creación de ticket cancelada.\n\n" + _texto_menu_principal(state)
            )
            return

        # Cualquier otro texto aquí se maneja como ticket en lenguaje natural
        if _manejar_ticket_libre(phone, text, state, adicional=False):
            return

        return

    # M3: ayuda / supervisor
    if menu_state == "M3":
        # Navegación rápida: 1,2,3,4 cambian de opción
        if t in {"1", "2", "3", "4"}:
            state["menu_state"] = "M1" if state["turno_activo"] else "M0"
            send_whatsapp(
                phone,
                "Cambio de opción. Salgo de ayuda y voy al menú.\n"
            )
            _handle_menu(phone, t, state)
            return

        if t.upper() in {"CANCELAR", "M", "MENU"}:
            state["menu_state"] = "M1" if state["turno_activo"] else "M0"
            send_whatsapp(
                phone,
                "👌 Cancelada la solicitud de ayuda.\n\n" + _texto_menu_principal(state)
            )
            return

        # Cualquier texto aquí es un mensaje al supervisor
        mensaje = (text or "").strip()
        if not mensaje:
            send_whatsapp(
                phone,
                "No entendí tu mensaje. Escribe qué necesitas, "
                "o 'cancelar' para volver al menú."
            )
            return

        # En producción se enviaría por otro canal; aquí solo confirmamos.
        send_whatsapp(
            phone,
            "📨 He registrado tu mensaje para el supervisor (demo):\n"
            f"“{mensaje}”.\n\n"
            "El supervisor lo verá en el sistema o en el canal correspondiente.\n\n"
            + _texto_menu_principal(state)
        )
        state["menu_state"] = "M1" if state["turno_activo"] else "M0"
        return
