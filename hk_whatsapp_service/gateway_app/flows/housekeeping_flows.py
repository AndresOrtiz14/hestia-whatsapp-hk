# gateway_app/flows/housekeeping_flows.py
from __future__ import annotations

from typing import Dict, Any, Callable
from datetime import date
import time

# =========================
#   ESTADO EN MEMORIA
# =========================

USER_STATE: Dict[str, Dict[str, Any]] = {}

# Sender injection: the webhook (or simulator) passes a function that actually sends messages.
# Signature: send(to_phone: str, body: str) -> None
SenderFn = Callable[[str, str], None]


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
        }
    return USER_STATE[phone]


# =========================
#   HELPERS DE TEXTO
# =========================

def _texto_menu_principal(state: Dict[str, Any]) -> str:
    """Construye el texto del menú según si el turno está activo o no."""
    linea_turno = "🟢 Turno ACTIVO" if state["turno_activo"] else "⚪️ Sin turno activo"
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
    {"id": 1010, "room": "312", "detalle": "Toallas adicionales", "prioridad": "MEDIA"},
    {"id": 1011, "room": "221", "detalle": "Limpieza rápida", "prioridad": "ALTA"},
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


def _mock_listado_tickets_por_resolver() -> str:
    """
    Mock sencillo para 'tickets por resolver'.
    En producción aquí se listan:
    - tickets asignados a la mucama
    - y/o tickets disponibles para que los tome
    """
    lines = ["Tickets por resolver (demo):"]
    for t in DEMO_TICKETS:
        lines.append(
            f"- #{t['id']} / Hab. {t['room']} / {t['detalle']} / prioridad {t['prioridad']}"
        )
    lines.append(
        "\nResponde 'aceptar' para tomar el primer ticket,\n"
        "o 'rechazar' para simular rechazo/derivación."
    )
    return "\n".join(lines)


# =========================
#   CREACIÓN DE TICKETS
# =========================

def _crear_ticket_desde_mucama(phone: str, texto: str, state: Dict[str, Any], send: SenderFn):
    """
    Crea un ticket nuevo a partir de texto libre de la mucama.
    Aquí se puede parsear habitación, tipo de problema, etc.
    En producción, esto llamaría a la API real de creación de tickets.
    """
    texto = (texto or "").strip()
    if not texto:
        send(
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
        send(
            phone,
            f"✅ Ticket creado (demo) para la habitación {room}:\n“{texto}”.\n\n"
            "El supervisor y recepción lo verán en el sistema."
        )
    else:
        send(
            phone,
            f"✅ Ticket creado (demo):\n“{texto}”.\n\n"
            "El supervisor y recepción lo verán en el sistema."
        )

    # Después de crear, volvemos al menú principal
    state["menu_state"] = "M1" if state["turno_activo"] else "M0"


def _crear_ticket_adicional(phone: str, texto: str, state: Dict[str, Any], send: SenderFn):
    """
    Crea un ticket adicional mientras hay otro ticket en ejecución (S1),
    por ejemplo: "la habitación 313 también quiere una toalla".
    """
    _crear_ticket_desde_mucama(phone, texto, state, send)


# =========================
#   RECORDATORIOS
# =========================

def _maybe_send_recordatorio_pendientes(phone: str, state: Dict[str, Any], send: SenderFn):
    """
    Envía un recordatorio cada 5 minutos *solo si*:
    - La persona tiene turno activo
    - NO está trabajando en ningún ticket (ticket_state es None)
    - Hay tickets pendientes por resolver
    - Ya pasaron al menos 5 minutos desde el último recordatorio
    """
    # 1) Debe tener turno activo
    if not state.get("turno_activo"):
        return

    # 2) No puede estar en un flujo de ticket
    if state.get("ticket_state") is not None:
        return

    # 3) Debe haber tickets pendientes / disponibles
    if not _hay_tickets_pendientes(state):
        return

    # 4) Intervalo mínimo entre recordatorios
    now = time.time()
    last_ts = state.get("last_reminder_ts")

    if last_ts is not None and (now - last_ts) < REMINDER_INTERVAL_SECONDS:
        return

    # Actualizamos timestamp y enviamos recordatorio
    state["last_reminder_ts"] = now

    send(
        phone,
        "Tienes casos pendientes por resolver.\n"
        "Para verlos, escribe *2* (Tickets por resolver) o *M* para ver el menú."
    )


# =========================
#   FLUJO DE TICKETS S0/S1/S2
# =========================

def _handle_ticket_flow(phone: str, text: str, state: Dict[str, Any], send: SenderFn):
    """
    Implementa el sub-diagrama 'Flujo de Tickets (PUSH)'.
    Estados:
      - S0: llegada / decisión sobre ticket por resolver
      - S1: ejecución (en curso o pausado)
      - S2: cierre / salida
    """
    if state["ticket_state"] is None:
        return  # No hay flujo de tickets activo

    t = (text or "").strip().lower()
    s = state["ticket_state"]

    # Atajo global: 'M' / 'MENU' → salir del flujo de tickets y volver al menú
    if (text or "").strip().upper() in {"M", "MENU"}:
        # NO cambiamos el estado del ticket a pausado.
        # Solo dejamos de estar “hablando” del flujo S0/S1/S2.
        state["ticket_state"] = None

        send(
            phone,
            "Te muestro el menú de Housekeeping.\n"
            "El ticket que aceptaste sigue en ejecución (demo).\n"
            "Si más adelante quieres gestionarlo (pausar o terminar), "
            "puedes volver a la opción 2 'Tickets por resolver'.\n\n"
            + _texto_menu_principal(state)
        )
        return

    # S0: nuevo ticket / decisión
    if s == "S0":
        if t == "aceptar":
            # Pasamos a S1, ticket aceptado
            state["ticket_state"] = "S1"
            ticket = state.get("ticket_activo") or {}

            ticket_id = ticket.get("id", "—")
            room = ticket.get("room", "—")
            detalle = ticket.get("detalle", "")
            prioridad = ticket.get("prioridad", "—")

            ticket["paused"] = False
            state["ticket_activo"] = ticket

            send(
                phone,
                "✅ Has ACEPTADO un ticket (S1 - Ejecución).\n"
                f"Ticket #{ticket_id} · Hab. {room} · Prioridad {prioridad}\n"
                f"Detalle: {detalle}\n\n"
                "Comandos: 'pausar', 'fin', 'supervisor'.\n"
                "También puedes escribir texto libre para crear tickets adicionales."
            )
        elif t in {"rechazar", "derivar"}:
            # Cerramos flujo del ticket y volvemos a menú
            state["ticket_state"] = "S2"
            send(
                phone,
                "🚫 Has RECHAZADO/DERIVADO el ticket (S2 - Cierre).\n"
                "Volviendo al menú.\n\n" + _texto_menu_principal(state)
            )
            state["ticket_state"] = None
            state["ticket_activo"] = None
        elif t == "timeout":
            state["ticket_state"] = "S2"
            send(
                phone,
                "⌛ Timeout de ticket (S2 - Cierre por sistema).\n"
                "Volviendo al menú.\n\n" + _texto_menu_principal(state)
            )
            state["ticket_state"] = None
            state["ticket_activo"] = None
        else:
            send(
                phone,
                "No entendí. En tickets por resolver (S0) puedes escribir:\n"
                "- 'aceptar'\n"
                "- 'rechazar'\n"
                "- 'derivar'\n"
                "- 'timeout' (demo)\n"
            )
        return

    # S1: ejecución (EN_CURSO o PAUSADO)
    if s == "S1":
        ticket = state.get("ticket_activo") or {}
        paused = ticket.get("paused", False)

        # Comandos comunes
        if t in {"fin", "terminar", "cerrar"}:
            state["ticket_state"] = "S2"
            send(
                phone,
                "✅ Ticket marcado como FINALIZADO (S2 - Cierre).\n"
                "Volviendo al menú.\n\n" + _texto_menu_principal(state)
            )
            state["ticket_state"] = None
            state["ticket_activo"] = None
            return

        if t == "supervisor":
            send(
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
                send(
                    phone,
                    "⏸ Has PAUSADO la ejecución (demo).\n"
                    "Comandos ahora: 'reanudar', 'fin', 'supervisor'.\n"
                    "También puedes escribir texto libre para crear tickets adicionales."
                )
                return
            if t == "reanudar":
                send(
                    phone,
                    "Ya estabas en ejecución (no estabas pausada).\n"
                    "Comandos: 'pausar', 'fin', 'supervisor', "
                    "o texto libre para nuevos tickets indicando una habitación."
                )
                return

            # Texto libre en S1 EN CURSO:
            # solo creamos ticket adicional si hay algún número (habitación)
            if any(ch.isdigit() for ch in text or ""):
                _crear_ticket_adicional(phone, text, state, send)
            else:
                send(
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
                send(
                    phone,
                    "▶️ Has REANUDADO la ejecución (demo).\n"
                    "Comandos: 'pausar', 'fin', 'supervisor', "
                    "o texto libre para nuevos tickets."
                )
                return
            if t == "pausar":
                send(
                    phone,
                    "⏸ El ticket ya estaba PAUSADO (demo).\n"
                    "Usa 'reanudar', 'fin', 'supervisor', "
                    "o texto libre para nuevos tickets."
                )
                return

            # Texto libre en S1 PAUSADO:
            # solo creamos ticket adicional si hay algún número (habitación)
            if any(ch.isdigit() for ch in text or ""):
                _crear_ticket_adicional(phone, text, state, send)
            else:
                send(
                    phone,
                    "No reconocí ese comando.\n"
                    "Con el ticket PAUSADO puedes usar:\n"
                    "- 'reanudar', 'fin', 'supervisor'\n"
                    "o describir un nuevo problema indicando habitación, por ejemplo:\n"
                    "'la 415 necesita toallas'."
                )
            return

    # S2: cierre / salida (por seguridad, limpiamos y volvemos a menú)
    if s == "S2":
        state["ticket_state"] = None
        state["ticket_activo"] = None
        send(
            phone,
            "🏁 TicketFlow finalizado. Volviendo al menú.\n\n" + _texto_menu_principal(state)
        )
        return


# =========================
#   MENÚ M0/M1/M2/M3
# =========================

def _handle_menu(phone: str, text: str, state: Dict[str, Any], send: SenderFn):
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
        send(phone, _texto_menu_principal(state))
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
                send(
                    phone,
                    "✅ Has INICIADO tu turno.\n\n" + _texto_menu_principal(state)
                )
            else:
                state["turno_activo"] = False
                state["menu_state"] = "M0"
                send(
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
                send(
                    phone,
                    "🔄 No tenías turno activo, lo he iniciado automáticamente.\n"
                )

            # Para el demo usamos siempre el primer ticket de la lista
            demo_ticket = DEMO_TICKETS[0]

            state["ticket_state"] = "S0"
            state["ticket_activo"] = {
                "id": demo_ticket["id"],
                "room": demo_ticket["room"],
                "detalle": demo_ticket["detalle"],
                "prioridad": demo_ticket["prioridad"],
                "paused": False,
            }

            send(
                phone,
                "📋 Tickets por resolver (S0)\n\n" + _mock_listado_tickets_por_resolver()
            )
            return

        if tlower == "3":
            # Crear ticket / problema
            state["menu_state"] = "M2"
            send(
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
            send(
                phone,
                "🆘 Ayuda / supervisor (M3).\n"
                "Escribe el mensaje que quieras enviar al supervisor.\n\n"
                "Ejemplo: 'Tengo muchas habitaciones atrasadas, necesito apoyo'."
            )
            return

        # Fallback en menú principal
        send(
            phone,
            "No entendí esa opción.\n\n" + _texto_menu_principal(state)
        )
        return

    # M2: crear ticket / problema
    if menu_state == "M2":
        if t.upper() in {"CANCELAR", "M", "MENU"}:
            state["menu_state"] = "M1" if state["turno_activo"] else "M0"
            send(
                phone,
                "❌ Creación de ticket cancelada.\n\n" + _texto_menu_principal(state)
            )
            return

        # Cualquier texto aquí se interpreta como descripción del problema
        _crear_ticket_desde_mucama(phone, text, state, send)
        send(
            phone,
            "\nVolviendo al menú principal.\n\n" + _texto_menu_principal(state)
        )
        return

    # M3: ayuda / supervisor
    if menu_state == "M3":
        if t.upper() in {"CANCELAR", "M", "MENU"}:
            state["menu_state"] = "M1" if state["turno_activo"] else "M0"
            send(
                phone,
                "👌 Cancelada la solicitud de ayuda.\n\n" + _texto_menu_principal(state)
            )
            return

        # Cualquier texto aquí es un mensaje al supervisor
        mensaje = (text or "").strip()
        if not mensaje:
            send(
                phone,
                "No entendí tu mensaje. Escribe qué necesitas, "
                "o 'cancelar' para volver al menú."
            )
            return

        # En producción se enviaría por otro canal; aquí solo confirmamos.
        send(
            phone,
            "📨 He registrado tu mensaje para el supervisor (demo):\n"
            f"“{mensaje}”.\n\n"
            "El supervisor lo verá en el sistema o en el canal correspondiente.\n\n"
            + _texto_menu_principal(state)
        )
        state["menu_state"] = "M1" if state["turno_activo"] else "M0"
        return


# =========================
#   PUNTOS DE ENTRADA PÚBLICOS
# =========================

def _handle_hk_message(from_phone: str, text: str, send: SenderFn):
    """
    Punto de entrada único para el simulador y (en producción) para el webhook.
    Orquesta:
    - Menú Housekeeping (M0..M3)
    - Flujo de tickets (S0..S2)

    Además:
    - Envía un saludo amable SOLO en el primer mensaje de cada día,
      siempre que no haya un flujo de ticket activo.
    """
    state = get_user_state(from_phone)

    raw = (text or "").strip()
    today_str = date.today().isoformat()

    # 0) Saludo de bienvenida: solo primer mensaje del día y sin ticket activo
    if state.get("ticket_state") is None and state.get("last_greet_date") != today_str:
        state["last_greet_date"] = today_str

        send(
            from_phone,
            "Hola, soy el asistente de Housekeeping de Hestia.\n"
            "Te ayudaré a organizar y resolver tus tareas de hoy.\n\n"
            + _texto_menu_principal(state)
        )
        # Importante: NO interpretamos este primer mensaje como opción de menú.
        return

    # 1) Si hay un flujo de tickets activo, darle prioridad
    if state["ticket_state"] is not None:
        _handle_ticket_flow(from_phone, text, state, send)
        return

    # 2) Si no hay ticket activo, manejar menú M0/M1/M2/M3
    _handle_menu(from_phone, raw, state, send)

    # 3) (Opcional en el simulador) revisar si toca mandar recordatorio
    _maybe_send_recordatorio_pendientes(from_phone, state, send)


def hk_handle_incoming(*, from_phone: str, text: str, send: SenderFn) -> None:
    """
    Entry-point llamado por el webhook / infraestructura actual.
    """
    _handle_hk_message(from_phone, text, send)


def hk_check_reminder(*, from_phone: str, send: SenderFn) -> None:
    """
    Pensado para una tarea periódica (cron / scheduler) en producción.
    Se puede llamar cada minuto; internamente respetamos el intervalo
    real de 5 minutos entre recordatorios por persona.

    Nota: aquí también inyectamos 'send' para poder enviar por WhatsApp real.
    """
    state = get_user_state(from_phone)
    _maybe_send_recordatorio_pendientes(from_phone, state, send)
