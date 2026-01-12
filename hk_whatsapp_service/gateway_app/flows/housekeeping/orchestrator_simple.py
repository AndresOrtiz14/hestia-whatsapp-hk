"""
Orquestador simplificado para bot de Housekeeping.
Sin menú complejo, flujo directo.
"""
import logging

logger = logging.getLogger(__name__)

from datetime import date, datetime
from .state_simple import (
    get_user_state,
    reset_ticket_draft,
    MENU,
    VIENDO_TICKETS,
    TRABAJANDO,
    REPORTANDO_HAB,
    REPORTANDO_DETALLE,
    CONFIRMANDO_REPORTE  # NUEVO
)
from .ui_simple import (
    texto_menu_simple,
    texto_saludo_dia,
    texto_ayuda,
    texto_lista_tickets,
    texto_ticket_en_progreso,
    texto_ticket_completado,
    texto_ticket_pausado,
    texto_ticket_reanudado,
    texto_pedir_habitacion,
    texto_pedir_detalle,
    texto_ticket_creado,
    texto_confirmar_reporte  # NUEVO
)
from .intents import (
    detectar_reporte_directo,
    es_comando_tomar,
    es_comando_finalizar,
    es_comando_pausar,
    es_comando_reanudar,
    es_comando_reportar,
    detectar_prioridad,
    extraer_habitacion
)
from .outgoing import send_whatsapp
from .demo_tickets import DEMO_TICKETS, elegir_mejor_ticket
from gateway_app.services.tickets_db import obtener_tickets_asignados_a


def handle_hk_message_simple(from_phone: str, text: str) -> None:

    state = get_user_state(from_phone)
    try:
        raw = (text or "").strip().lower()
        logger.info(f"🏨 HK | {from_phone} | Comando: '{raw[:30]}...'")

        # 1) Saludo inicial del día
        today_str = date.today().isoformat()
        if state.get("last_greet_date") != today_str:
            state["last_greet_date"] = today_str
            send_whatsapp(from_phone, texto_saludo_dia())
            send_whatsapp(from_phone, texto_menu_simple())
            state["state"] = MENU
            return

        
        # 2) Comando global: Menú
        if raw in ['m', 'menu', 'menú', 'volver']:
            reset_ticket_draft(from_phone)  # NUEVO: Limpiar draft al volver
            send_whatsapp(from_phone, texto_menu_simple())
            state["state"] = MENU
            return
        
        # 2.5) NUEVO: Navegación directa de menú (desde cualquier estado)
        # Permite escribir 1, 2, 3 para navegar sin volver al menú
        if raw in ['1', '2', '3'] and state.get("state") not in [REPORTANDO_HAB, REPORTANDO_DETALLE, CONFIRMANDO_REPORTE]:
            # Solo si NO está en medio de un reporte
            if raw == '1':
                mostrar_tickets(from_phone)
                return
            elif raw == '2':
                iniciar_reporte(from_phone)
                return
            elif raw == '3':
                send_whatsapp(from_phone, texto_ayuda())
                state["state"] = MENU
                return
        
        # 3) Si tiene ticket activo, priorizar comandos de trabajo
        if state.get("ticket_activo"):
            if handle_comandos_ticket_activo(from_phone, text):
                return
        
        # 4) Detectar reporte directo (ej: "hab 305 fuga de agua")
        # IMPORTANTE: Solo si NO está en flujo de reporte manual
        current_state = state.get("state")
        if current_state not in [REPORTANDO_HAB, REPORTANDO_DETALLE, CONFIRMANDO_REPORTE]:
            reporte = detectar_reporte_directo(text)
            if reporte:
                crear_ticket_directo(from_phone, reporte)
                return
        
        # 5) Comandos globales
        if es_comando_tomar(raw):
            tomar_ticket(from_phone)
            return
        
        if es_comando_reportar(raw):
            iniciar_reporte(from_phone)
            return
        
        if raw in ['tickets', 'ver tickets', 'mis tickets']:
            mostrar_tickets(from_phone)
            return
        
        # 6) Routing por estado
        current_state = state.get("state")
        
        if current_state == MENU:
            handle_menu(from_phone, raw)
            return
        
        if current_state == VIENDO_TICKETS:
            handle_viendo_tickets(from_phone, raw)
            return
        
        if current_state == REPORTANDO_HAB:
            handle_reportando_habitacion(from_phone, text)
            return
        
        if current_state == REPORTANDO_DETALLE:
            handle_reportando_detalle(from_phone, text)
            return
        
        if current_state == CONFIRMANDO_REPORTE:
            handle_confirmando_reporte(from_phone, raw)
            return
        
        # 7) No entendí
        send_whatsapp(
            from_phone,
            "🤔 No entendí.\n\n"
            "💡 Puedes decir:\n"
            "• 'tomar' - Tomar ticket\n"
            "• 'tickets' - Ver mis tickets\n"
            "• 'reportar' - Reportar problema\n"
            "• 'M' - Menú"
    )
    finally:
        # Persist full state at end of processing
        from .state_simple import persist_user_state
        persist_user_state(from_phone, state)


def handle_menu(from_phone: str, raw: str) -> None:
    """
    Maneja selección del menú.
    
    Args:
        from_phone: Número de teléfono
        raw: Texto normalizado
    """
    state = get_user_state(from_phone)
    
    # Opción 1: Ver tickets
    if raw in ['1', 'ver tickets', 'tickets']:
        mostrar_tickets(from_phone)
        return
    
    # Opción 2: Reportar problema
    if raw in ['2', 'reportar', 'reportar problema']:
        iniciar_reporte(from_phone)
        return
    
    # Opción 3: Ayuda
    if raw in ['3', 'ayuda', 'help']:
        send_whatsapp(from_phone, texto_ayuda())
        return
    
    # No reconocido
    send_whatsapp(
        from_phone,
        "❌ Opción no válida\n\n" + texto_menu_simple()
    )


def handle_viendo_tickets(from_phone: str, raw: str) -> None:
    """
    Maneja acciones cuando está viendo tickets.
    
    Args:
        from_phone: Número de teléfono
        raw: Texto normalizado
    """
    state = get_user_state(from_phone)
    
    # Comando: tomar
    if es_comando_tomar(raw):
        tomar_ticket(from_phone)
        return
    
    # TODO: Selección por número (#1011)
    
    # Volver
    send_whatsapp(from_phone, "💡 Di 'tomar' o 'M'")


def handle_comandos_ticket_activo(from_phone: str, text: str) -> bool:
    """
    Maneja comandos cuando hay ticket activo.
    
    Args:
        from_phone: Número de teléfono
        text: Texto del mensaje
    
    Returns:
        True si se manejó un comando
    """
    raw = text.lower().strip()
    state = get_user_state(from_phone)
    ticket = state["ticket_activo"]
    
    # Finalizar
    if es_comando_finalizar(raw):
        finalizar_ticket(from_phone)
        return True
    
    # Pausar
    if es_comando_pausar(raw):
        pausar_ticket(from_phone)
        return True
    
    # Reanudar
    if es_comando_reanudar(raw):
        reanudar_ticket(from_phone)
        return True
    
    return False


def mostrar_tickets(from_phone: str) -> None:
    """
    Muestra tickets (tareas) asignados al worker desde la BD real: public.tickets
    """
    state = get_user_state(from_phone)

    mis_tickets = obtener_tickets_asignados_a(from_phone)

    mensaje = texto_lista_tickets(mis_tickets)
    send_whatsapp(from_phone, mensaje)

    state["state"] = VIENDO_TICKETS



def tomar_ticket(from_phone: str) -> None:
    """
    Toma el ticket de mayor prioridad.
    
    Args:
        from_phone: Número de teléfono
    """
    state = get_user_state(from_phone)
    
    # Si ya tiene ticket activo
    if state.get("ticket_activo"):
        send_whatsapp(
            from_phone,
            f"⚠️ Ya tienes el ticket #{state['ticket_activo']['id']} en progreso\n\n"
            "💡 'fin' para terminarlo"
        )
        return
    
    # Buscar mejor ticket
    mis_tickets = [t for t in DEMO_TICKETS if t.get("asignado_a") == from_phone]
    ticket = elegir_mejor_ticket(mis_tickets)
    
    if not ticket:
        send_whatsapp(from_phone, "✅ No tienes tickets pendientes")
        return
    
    # Iniciar ticket
    ticket["started_at"] = datetime.now().isoformat()
    ticket["estado"] = "en_progreso"
    state["ticket_activo"] = ticket
    state["state"] = TRABAJANDO
    
    mensaje = texto_ticket_en_progreso(ticket)
    send_whatsapp(from_phone, mensaje)


# Continúa en la siguiente parte...


def finalizar_ticket(from_phone: str) -> None:
    """
    Finaliza el ticket activo.
    
    Args:
        from_phone: Número de teléfono
    """
    state = get_user_state(from_phone)
    ticket = state.get("ticket_activo")
    
    if not ticket:
        send_whatsapp(from_phone, "❌ No tienes ticket activo")
        return
    
    # Calcular tiempo
    started = datetime.fromisoformat(ticket["started_at"])
    ended = datetime.now()
    tiempo_mins = int((ended - started).total_seconds() / 60)
    
    # Actualizar ticket
    ticket["ended_at"] = ended.isoformat()
    ticket["estado"] = "completado"
    
    # Limpiar estado
    state["ticket_activo"] = None
    state["state"] = MENU
    
    # Notificar
    mensaje = texto_ticket_completado(ticket, tiempo_mins)
    send_whatsapp(from_phone, mensaje)
    
    # Mostrar siguiente si hay
    mis_tickets = [t for t in DEMO_TICKETS 
                   if t.get("asignado_a") == from_phone 
                   and t.get("estado") != "completado"]
    
    if mis_tickets:
        siguiente = elegir_mejor_ticket(mis_tickets)
        if siguiente:
            prioridad_emoji = {
                "ALTA": "🔴",
                "MEDIA": "🟡",
                "BAJA": "🟢"
            }.get(siguiente.get("prioridad", "MEDIA"), "🟡")
            
            send_whatsapp(
                from_phone,
                f"\nSiguiente disponible:\n"
                f"{prioridad_emoji} #{siguiente['id']} · Hab. {siguiente['habitacion']}\n"
                f"{siguiente['detalle']}\n\n"
                f"💡 Di 'tomar' o 'M'"
            )


def pausar_ticket(from_phone: str) -> None:
    """
    Pausa el ticket activo.
    
    Args:
        from_phone: Número de teléfono
    """
    state = get_user_state(from_phone)
    ticket = state.get("ticket_activo")
    
    if not ticket:
        send_whatsapp(from_phone, "❌ No tienes ticket activo")
        return
    
    # Marcar pausa
    ticket["paused_at"] = datetime.now().isoformat()
    ticket["estado"] = "pausado"
    
    mensaje = texto_ticket_pausado(ticket)
    send_whatsapp(from_phone, mensaje)


def reanudar_ticket(from_phone: str) -> None:
    """
    Reanuda el ticket pausado.
    
    Args:
        from_phone: Número de teléfono
    """
    state = get_user_state(from_phone)
    ticket = state.get("ticket_activo")
    
    if not ticket:
        send_whatsapp(from_phone, "❌ No tienes ticket activo")
        return
    
    if ticket.get("estado") != "pausado":
        send_whatsapp(from_phone, "❌ El ticket no está pausado")
        return
    
    # Reanudar
    ticket["resumed_at"] = datetime.now().isoformat()
    ticket["estado"] = "en_progreso"
    
    mensaje = texto_ticket_reanudado(ticket)
    send_whatsapp(from_phone, mensaje)


def iniciar_reporte(from_phone: str) -> None:
    """
    Inicia el flujo de reportar problema.
    
    Args:
        from_phone: Número de teléfono
    """
    state = get_user_state(from_phone)
    reset_ticket_draft(from_phone)
    
    state["state"] = REPORTANDO_HAB
    send_whatsapp(from_phone, texto_pedir_habitacion())


def handle_reportando_habitacion(from_phone: str, text: str) -> None:
    """
    Maneja la respuesta cuando está pidiendo habitación.
    MEJORA: Si el mensaje incluye habitación + detalle, crear ticket directo.
    
    Args:
        from_phone: Número de teléfono
        text: Texto con la habitación (y posiblemente detalle)
    """
    state = get_user_state(from_phone)
    
    # NUEVO: Intentar detectar reporte completo (ej: "302 tiene mancha de humedad")
    from .intents import detectar_reporte_directo
    reporte_completo = detectar_reporte_directo(text)
    
    if reporte_completo:
        # Tiene habitación + detalle: crear directo con confirmación
        state["ticket_draft"]["habitacion"] = reporte_completo["habitacion"]
        state["ticket_draft"]["detalle"] = reporte_completo["detalle"]
        state["ticket_draft"]["prioridad"] = reporte_completo["prioridad"]
        state["state"] = CONFIRMANDO_REPORTE
        
        # Mostrar confirmación
        mensaje = texto_confirmar_reporte(
            reporte_completo["habitacion"],
            reporte_completo["detalle"],
            reporte_completo["prioridad"]
        )
        send_whatsapp(from_phone, mensaje)
        return
    
    # Solo habitación: continuar flujo normal
    from .intents import extraer_habitacion
    habitacion = extraer_habitacion(text)
    
    if not habitacion:
        send_whatsapp(from_phone, "❌ No entendí el número\n\n" + texto_pedir_habitacion())
        return
    
    # Guardar y continuar
    state["ticket_draft"]["habitacion"] = habitacion
    state["state"] = REPORTANDO_DETALLE
    
    send_whatsapp(from_phone, texto_pedir_detalle())


def handle_reportando_detalle(from_phone: str, text: str) -> None:
    """
    Maneja el detalle del problema.
    
    Args:
        from_phone: Número de teléfono
        text: Detalle del problema
    """
    state = get_user_state(from_phone)
    draft = state["ticket_draft"]
    
    # Guardar detalle
    draft["detalle"] = text
    
    # Detectar prioridad automáticamente
    draft["prioridad"] = detectar_prioridad(text)
    
    # Ir a confirmación (NUEVO)
    state["state"] = CONFIRMANDO_REPORTE
    
    # Mostrar resumen para confirmar
    mensaje = texto_confirmar_reporte(
        draft["habitacion"],
        draft["detalle"],
        draft["prioridad"]
    )
    send_whatsapp(from_phone, mensaje)


def handle_confirmando_reporte(from_phone: str, raw: str) -> None:
    """
    Maneja la confirmación del reporte.
    
    Args:
        from_phone: Número de teléfono
        raw: Texto normalizado
    """
    state = get_user_state(from_phone)
    draft = state["ticket_draft"]
    
    # Confirmar
    if raw in ['si', 'sí', 'yes', 'ok', 'confirmar', 'confirmo', 'dale', 'correcto']:
        crear_ticket_desde_draft(from_phone)
        return
    
    # Editar habitación
    if raw in ['editar', 'cambiar', 'modificar', 'editar habitacion', 'editar habitación']:
        state["state"] = REPORTANDO_HAB
        send_whatsapp(from_phone, texto_pedir_habitacion())
        return
    
    # Editar detalle
    if raw in ['editar detalle', 'cambiar detalle']:
        state["state"] = REPORTANDO_DETALLE
        send_whatsapp(from_phone, texto_pedir_detalle())
        return
    
    # Cancelar
    if raw in ['cancelar', 'cancel', 'no']:
        reset_ticket_draft(from_phone)
        state["state"] = MENU
        send_whatsapp(from_phone, "❌ Reporte cancelado")
        return
    
    # No entendió
    mensaje = texto_confirmar_reporte(
        draft["habitacion"],
        draft["detalle"],
        draft["prioridad"]
    )
    send_whatsapp(from_phone, "❌ No entendí\n\n" + mensaje)


def crear_ticket_directo(from_phone: str, reporte: dict) -> None:
    """
    Crea ticket desde reporte directo (texto/audio) y lo guarda en public.tickets.
    """
    from gateway_app.services.tickets_db import crear_ticket

    try:
        ticket = crear_ticket(
            habitacion=reporte["habitacion"],
            detalle=reporte["detalle"],
            prioridad=reporte["prioridad"],
            creado_por=from_phone,  # el worker que reporta
            origen="trabajador",
            canal_origen="WHATSAPP_BOT_HOUSEKEEPING",
            area="HOUSEKEEPING",
        )

        if not ticket:
            send_whatsapp(from_phone, "❌ No pude crear el ticket en la base de datos.")
            return

        ticket_id = ticket["id"]
        mensaje = texto_ticket_creado(ticket_id, reporte["habitacion"], reporte["prioridad"])
        send_whatsapp(from_phone, mensaje)

        # volver al menú
        state = get_user_state(from_phone)
        state["state"] = MENU

    except Exception:
        logger.exception("Error creando ticket directo en DB")
        send_whatsapp(from_phone, "❌ Error creando el ticket. Intenta de nuevo.")


def crear_ticket_desde_draft(from_phone: str) -> None:
    """
    Crea ticket desde el borrador y lo guarda en public.tickets.
    """
    from gateway_app.services.tickets_db import crear_ticket

    state = get_user_state(from_phone)
    draft = state["ticket_draft"]

    # VALIDACIÓN
    if not draft.get("habitacion") or not draft.get("detalle"):
        send_whatsapp(from_phone, "❌ Error: Falta información del reporte")
        reset_ticket_draft(from_phone)
        state["state"] = MENU
        return

    try:
        ticket = crear_ticket(
            habitacion=draft["habitacion"],
            detalle=draft["detalle"],
            prioridad=draft["prioridad"],
            creado_por=from_phone,  # el worker que reporta
            origen="trabajador",
            canal_origen="WHATSAPP_BOT_HOUSEKEEPING",
            area="HOUSEKEEPING",
        )

        if not ticket:
            send_whatsapp(from_phone, "❌ No pude crear el ticket en la base de datos.")
            reset_ticket_draft(from_phone)
            state["state"] = MENU
            return

        ticket_id = ticket["id"]
        mensaje = texto_ticket_creado(ticket_id, draft["habitacion"], draft["prioridad"])
        send_whatsapp(from_phone, mensaje)

        # Limpiar y volver al menú
        reset_ticket_draft(from_phone)
        state["state"] = MENU

    except Exception:
        logger.exception("Error creando ticket desde draft en DB")
        send_whatsapp(from_phone, "❌ Error creando el ticket. Intenta de nuevo.")
        reset_ticket_draft(from_phone)
        state["state"] = MENU

    """
    Crea ticket desde el borrador.
    VALIDACIÓN: Solo crea si hay habitación Y detalle.
    
    Args:
        from_phone: Número de teléfono
    """
    state = get_user_state(from_phone)
    draft = state["ticket_draft"]
    
    # VALIDACIÓN: Verificar que hay datos completos
    if not draft.get("habitacion") or not draft.get("detalle"):
        send_whatsapp(from_phone, "❌ Error: Falta información del reporte")
        reset_ticket_draft(from_phone)
        state["state"] = MENU
        return
    
    import random
    ticket_id = random.randint(2000, 2999)
    
    # Crear ticket
    nuevo_ticket = {
        "id": ticket_id,
        "habitacion": draft["habitacion"],
        "detalle": draft["detalle"],
        "prioridad": draft["prioridad"],
        "creado_por": from_phone,
        "created_at": datetime.now().isoformat(),
        "estado": "pendiente"
    }
    
    # TODO: Guardar en BD y notificar a supervisión
    
    mensaje = texto_ticket_creado(ticket_id, draft["habitacion"], draft["prioridad"])
    send_whatsapp(from_phone, mensaje)
    
    # Limpiar y volver al menú
    reset_ticket_draft(from_phone)
    state["state"] = MENU