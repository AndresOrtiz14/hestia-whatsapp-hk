from typing import Dict, Any
from datetime import datetime
import re

from .outgoing import send_whatsapp
from .ui import texto_menu_principal, recordatorio_menu
from .demo_tickets import DEMO_TICKETS, elegir_mejor_ticket
from .ticket_text import manejar_ticket_libre

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

def norm(s: str) -> str:
    s = (s or "").strip().lower()
    s = re.sub(r"\s+", " ", s)
    return s

def corregir_typo_comando(text: str) -> str:
    """
    Corrige typos comunes en comandos.
    Retorna el comando corregido o el texto original si no es un typo conocido.
    """
    t = norm(text)
    
    # Mapeo de typos comunes → comando correcto
    typos_map = {
        # Variaciones de "terminar"
        "termianr": "terminar",
        "termirar": "terminar",
        "terminra": "terminar",
        "temrinar": "terminar",
        "termniar": "terminar",
        
        # Variaciones de "pausar"
        "psusar": "pausar",
        "pauar": "pausar",
        "pausr": "pausar",
        
        # Variaciones de "reanudar"
        "reanudra": "reanudar",
        "reanuadr": "reanudar",
        "renaudar": "reanudar",
        
        # Variaciones de "finalizar"
        "finalizra": "finalizar",
        "finalizr": "finalizar",
        "finalziar": "finalizar",
    }
    
    return typos_map.get(t, text)

def match_frase(text: str, frases: set[str]) -> bool:
    t = norm(text)
    return any(frase in t for frase in frases)

def es_aceptacion_ticket(text: str) -> bool:
    t = norm(text)
    # Evita falsos positivos tipo "no acepto", "no lo tomo"
    if ("no acept" in t) or ("no lo tomo" in t) or ("no tomar" in t) or ("no tomo" in t):
        return False
    return match_frase(t, ACCEPT_PHRASES)

def es_rechazo_ticket(text: str) -> bool:
    return match_frase(text, REJECT_PHRASES)

def extraer_id_ticket_en_texto(text: str) -> int | None:
    """
    Permite escribir: '#1011' o '1011' para elegir ticket específico.
    """
    t = norm(text)
    m = re.search(r"#?\b(\d{3,6})\b", t)
    if not m:
        return None
    try:
        return int(m.group(1))
    except:
        return None

# =========================
#   FLUJO DE TICKETS S0/S1/S2
# =========================

def _handle_ticket_flow(phone: str, text: str, state: Dict[str, Any]):
    """
    Implementa el sub-diagrama 'Flujo de Tickets (PUSH)'.
    Estados:
      - S0: llegada / decisión sobre ticket por resolver
      - S1: ejecución (en curso o pausado)
      - S2: cierre / salida
    """
    if state["ticket_state"] is None:
        return  # No hay flujo de tickets activo

    raw = (text or "").strip()
    
    # Corregir typos comunes antes de procesar
    raw = corregir_typo_comando(raw)
    
    t = raw.lower()
    s = state["ticket_state"]

    # Atajo global: 'M' / 'MENU' → salir del flujo de tickets y volver al menú
    if raw.upper() in {"M", "MENU"}:
        # NO cambiamos el estado del ticket a pausado.
        # Solo dejamos de estar “hablando” del flujo S0/S1/S2.
        state["ticket_state"] = None

        send_whatsapp(
            phone,
            "Te muestro el menú de Housekeeping.\n"
            "El ticket que aceptaste sigue en ejecución (demo).\n"
            "Si más adelante quieres gestionarlo (pausar o terminar), "
            "puedes volver a la opción 2 'Tickets por resolver'.\n\n"
            + texto_menu_principal(state)
        )
        return

    # NUEVO: navegación rápida por números 1–4
    # Si está en S0 o S1 y escribe 1,2,3,4 → salir del flujo de ticket
    # y mandar esa opción directamente al menú.
    if s in {"S0", "S1"} and t in {"1", "2", "3", "4"}:
        state["ticket_state"] = None  # dejamos de “hablar del ticket”
        # opcional: no tocamos ticket_activo, se mantiene en ejecución de fondo

        send_whatsapp(
            phone,
            "Cambio de opción. Salgo de este ticket y voy al menú.\n"
        )
        # Import local para evitar import circular
        from .menu_flow import handle_menu
        # Reutilizamos la lógica normal del menú con ese mismo número
        handle_menu(phone, raw, state)
        return

    # S0: nuevo ticket / decisión
    if s == "S0":
        # 1) Aceptación
        if es_aceptacion_ticket(raw):
            # Si la persona escribió un ID (#1011), lo usamos
            tid = extraer_id_ticket_en_texto(raw)

            if tid is not None:
                elegido = next((x for x in DEMO_TICKETS if x.get("id") == tid), None)
            else:
                elegido = elegir_mejor_ticket(DEMO_TICKETS)

            if not elegido:
                send_whatsapp(phone, "No encontré tickets pendientes para tomar (demo).")
                state["ticket_state"] = None
                state["ticket_activo"] = None
                return

            # DEMO: En modo demo, los tickets son infinitos (no se eliminan)
            # En producción, aquí se marcaría el ticket como "en progreso" en la BD
            # Para evitar que otro usuario lo tome al mismo tiempo

            state["ticket_state"] = "S1"
            state["ticket_activo"] = {
                "id": elegido["id"],
                "room": elegido["room"],
                "detalle": elegido["detalle"],
                "prioridad": elegido["prioridad"],
                "paused": False,
                "started_at": datetime.now(),
                # Tracking de tiempo real (excluyendo pausas)
                "paused_at": None,
                "total_paused_seconds": 0,
            }

            send_whatsapp(
                phone,
                "✅ Has ACEPTADO un ticket (S1 - Ejecución).\n"
                f"Ticket #{elegido['id']} · Hab. {elegido['room']} · Prioridad {elegido['prioridad']}\n"
                f"Detalle: {elegido['detalle']}\n\n"
                "Comandos disponibles:\n"
                "• 'pausar' - Pausar temporalmente\n"
                "• 'fin' / 'finalizar' / 'listo' - Completar ticket\n"
                "• 'supervisor' - Pedir ayuda\n\n"
                "También puedes escribir texto libre para crear tickets adicionales." + recordatorio_menu())
            return

        # 2) Rechazo / Derivación
        if es_rechazo_ticket(raw):
            state["ticket_state"] = "S2"
            send_whatsapp(
                phone,
                "🚫 Has RECHAZADO/DERIVADO el ticket (S2 - Cierre).\n"
                "Volviendo al menú.\n\n" + texto_menu_principal(state)
            )
            state["ticket_state"] = None
            state["ticket_activo"] = None
            return

        # 3) Timeout demo
        if t == "timeout":
            state["ticket_state"] = "S2"
            send_whatsapp(
                phone,
                "⌛ Timeout de ticket (S2 - Cierre por sistema).\n"
                "Volviendo al menú.\n\n" + texto_menu_principal(state)
            )
            state["ticket_state"] = None
            state["ticket_activo"] = None
            return

        # 4) Detectar comandos de ejecución (fin, pausar, etc.) y dar warning
        comandos_ejecucion = {"fin", "terminar", "cerrar", "finalizar", "completar", "listo", "hecho", "pausar", "reanudar"}
        if t in comandos_ejecucion:
            send_whatsapp(
                phone,
                f"⚠️ No puedes usar '{t}' todavía.\n\n"
                f"Primero debes ACEPTAR el ticket para poder gestionarlo.\n\n"
                f"Escribe:\n"
                f"• 'aceptar' / 'tomar ticket' - Para aceptar el ticket\n"
                f"• 'rechazar' / 'derivar' - Para rechazarlo\n"
                f"• '#1011' - Para elegir un ticket específico" + recordatorio_menu())
            return

        # 5) Fallback general
        send_whatsapp(
            phone,
            "No entendí. En tickets por resolver (S0) puedes escribir por ejemplo:\n"
            "- 'aceptar' / 'tomar ticket' / 'ok lo tomo'\n"
            "- 'rechazar' / 'derivar'\n"
            "- '#1011' para elegir uno\n"
            "- 'timeout' (demo)\n" + recordatorio_menu())
        return

    # S1: ejecución (EN_CURSO o PAUSADO)
    if s == "S1":
        ticket = state.get("ticket_activo") or {}
        paused = ticket.get("paused", False)

        # Comandos comunes
        if t in {"fin", "terminar", "cerrar", "finalizar", "completar", "listo", "hecho"}:
            # Datos básicos del ticket
            ticket_id = ticket.get("id", "—")
            room = ticket.get("room", "—")
            detalle = ticket.get("detalle", "")
            prioridad = ticket.get("prioridad", "—")

            # Calcular tiempos de resolución
            started_at = ticket.get("started_at")
            total_paused_sec = ticket.get("total_paused_seconds", 0)
            
            # Si está pausado al finalizar, incluir esa pausa también
            if ticket.get("paused") and ticket.get("paused_at"):
                final_pause = (datetime.now() - ticket["paused_at"]).total_seconds()
                total_paused_sec += final_pause
            
            if isinstance(started_at, datetime):
                # TIEMPO TOTAL: desde aceptación hasta cierre
                total_elapsed = datetime.now() - started_at
                total_seconds = int(total_elapsed.total_seconds())
                
                # TIEMPO REAL: tiempo total - tiempo pausado
                real_work_seconds = total_seconds - int(total_paused_sec)
                
                # Formatear tiempos
                def formato_tiempo(seg):
                    if seg < 60:
                        return "menos de 1 minuto"
                    minutos = seg // 60
                    if minutos == 1:
                        return "1 minuto"
                    return f"{minutos} minutos"
                
                tiempo_total_txt = formato_tiempo(total_seconds)
                tiempo_real_txt = formato_tiempo(real_work_seconds)
                tiempo_pausa_txt = formato_tiempo(int(total_paused_sec))
                
                # Mensaje de tiempo condicional
                if total_paused_sec > 60:  # Si hubo pausas significativas (>1 min)
                    tiempo_msg = (
                        f"⏱️ Tiempos de resolución:\n"
                        f"• Total: {tiempo_total_txt}\n"
                        f"• Trabajo efectivo: {tiempo_real_txt}\n"
                        f"• En pausa: {tiempo_pausa_txt}"
                    )
                else:
                    # Sin pausas significativas, mostrar solo tiempo real
                    tiempo_msg = f"Tiempo de resolución: {tiempo_real_txt}"
            else:
                tiempo_msg = "Tiempo de resolución: no disponible (demo)"

            # Marcamos cierre lógico del flujo
            state["ticket_state"] = "S2"

            # Mensaje de resumen + recordatorio genérico
            send_whatsapp(
                phone,
                "✅ Ticket FINALIZADO (S2 - Cierre).\n"
                f"Ticket #{ticket_id} · Hab. {room} · Prioridad {prioridad}\n"
                f"Detalle: {detalle}\n\n"
                f"{tiempo_msg}\n\n"
                "Si todavía tienes otros tickets pendientes, recuerda ir a "
                "'Tickets por resolver' (opción 2) para continuar." + recordatorio_menu()
            )

            # Limpiamos el ticket activo del flujo
            state["ticket_state"] = None
            state["ticket_activo"] = None
            
            # PUSH: Verificar si hay tickets pendientes en cola y asignar el siguiente
            from .orchestrator import check_and_assign_pending_tickets
            next_ticket_result = check_and_assign_pending_tickets(phone)
            
            # Si se asignó un ticket de la cola, ya se notificó en check_and_assign_pending_tickets
            # Si no hay más tickets pendientes, el flujo termina normalmente
            
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
                ticket["paused_at"] = datetime.now()  # Registrar cuando se pausó
                state["ticket_activo"] = ticket
                send_whatsapp(
                    phone,
                    "⏸ Has PAUSADO la ejecución (demo).\n"
                    "Comandos ahora: 'reanudar', 'fin', 'supervisor'.\n"
                    "También puedes escribir texto libre para crear tickets adicionales." + recordatorio_menu())
                return
            if t == "reanudar":
                send_whatsapp(
                    phone,
                    "Ya estabas en ejecución (no estabas pausada).\n"
                    "Comandos: 'pausar', 'fin', 'supervisor', "
                    "o texto libre para nuevos tickets indicando una habitación."
                )
                return

            # Texto libre en S1 EN CURSO: intentamos tratarlo como nuevo ticket
            if manejar_ticket_libre(phone, text, state, adicional=True):
                return

            # Si por alguna razón no se interpretó como ticket:
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
                # Acumular tiempo que estuvo pausado
                paused_at = ticket.get("paused_at")
                if paused_at and isinstance(paused_at, datetime):
                    pause_duration = (datetime.now() - paused_at).total_seconds()
                    ticket["total_paused_seconds"] = ticket.get("total_paused_seconds", 0) + pause_duration
                
                ticket["paused"] = False
                ticket["paused_at"] = None  # Limpiar
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

            # Texto libre con ticket PAUSADO: también puede ser un ticket nuevo
            if manejar_ticket_libre(phone, text, state, adicional=True):
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

    # S2: cierre / salida (por seguridad, limpiamos y volvemos a menú)
    if s == "S2":
        state["ticket_state"] = None
        state["ticket_activo"] = None
        send_whatsapp(
            phone,
            "🏁 TicketFlow finalizado. Volviendo al menú.\n\n" + texto_menu_principal(state)
        )
        return