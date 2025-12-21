from typing import Dict, Any

from .outgoing import send_whatsapp
from .ui import texto_menu_principal
from .demo_tickets import DEMO_TICKETS, elegir_mejor_ticket, mock_listado_tickets_por_resolver
from .ticket_text import manejar_ticket_libre

# =========================
#   MENÚ M0/M1/M2/M3
# =========================

def handle_menu(phone: str, text: str, state: Dict[str, Any]):
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
        send_whatsapp(phone, 
        texto_menu_principal(state))
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
                    "✅ Has INICIADO tu turno.\n\n" + texto_menu_principal(state)
                )
            else:
                state["turno_activo"] = False
                state["menu_state"] = "M0"
                send_whatsapp(
                    phone,
                    "✅ Has FINALIZADO tu turno.\n\n" + texto_menu_principal(state)
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
            demo_ticket = elegir_mejor_ticket(DEMO_TICKETS)
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
                "📋 Tickets por resolver (S0)\n\n" + mock_listado_tickets_por_resolver()
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
        if manejar_ticket_libre(phone, text, state):
            return

        send_whatsapp(
            phone,
            "No entendí esa opción.\n\n" + texto_menu_principal(state)
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
            handle_menu(phone, t, state)
            return

        if t.upper() in {"CANCELAR", "M", "MENU"}:
            state["menu_state"] = "M1" if state["turno_activo"] else "M0"
            send_whatsapp(
                phone,
                "❌ Creación de ticket cancelada.\n\n" + texto_menu_principal(state)
            )
            return

        # Cualquier otro texto aquí se maneja como ticket en lenguaje natural
        if manejar_ticket_libre(phone, text, state, adicional=False):
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
            handle_menu(phone, t, state)
            return

        if t.upper() in {"CANCELAR", "M", "MENU"}:
            state["menu_state"] = "M1" if state["turno_activo"] else "M0"
            send_whatsapp(
                phone,
                "👌 Cancelada la solicitud de ayuda.\n\n" + texto_menu_principal(state)
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
            + texto_menu_principal(state)
        )
        state["menu_state"] = "M1" if state["turno_activo"] else "M0"
        return
