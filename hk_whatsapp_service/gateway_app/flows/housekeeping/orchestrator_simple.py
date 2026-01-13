"""
Orquestador simplificado para bot de Housekeeping.
Sin menú complejo, flujo directo.
"""
import logging

logger = logging.getLogger(__name__)

from gateway_app.services.tickets_db import crear_ticket
from gateway_app.services import tickets_db


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

def verificar_turno_activo(from_phone: str) -> bool:
    """
    Verifica si el turno está activo. Si no, lo inicia automáticamente.
    
    Args:
        from_phone: Número de teléfono
    
    Returns:
        True si el turno está activo (o fue auto-iniciado)
    """
    state = get_user_state(from_phone)
    
    if not state.get("turno_activo", False):
        # Auto-iniciar turno
        from datetime import datetime
        state["turno_activo"] = True
        state["turno_inicio"] = datetime.now().isoformat()
        
        send_whatsapp(
            from_phone,
            "🟢 Turno iniciado automáticamente\n\n"
            "💡 Para terminar tu turno, escribe 'terminar turno'"
        )
    
    return True

def handle_hk_message_simple(from_phone: str, text: str) -> None:

    state = get_user_state(from_phone)
    try:
        raw = (text or "").strip().lower()
        logger.info(f"🏨 HK | {from_phone} | Comando: '{raw[:30]}...'")

        # 1) Saludo inicial del día
        today_str = date.today().isoformat()
        if state.get("last_greet_date") != today_str:
            state["last_greet_date"] = today_str
            turno_activo = state.get("turno_activo", False)
            
            from .ui_simple import texto_saludo_con_turno
            send_whatsapp(from_phone, texto_saludo_con_turno(turno_activo))
            state["state"] = MENU
            return

        
        # 2) Comando global: Menú
        if raw in ['m', 'menu', 'menú', 'volver']:
            reset_ticket_draft(from_phone)  # NUEVO: Limpiar draft al volver
            send_whatsapp(from_phone, texto_menu_simple())
            state["state"] = MENU
            return
        
        # 2.5) Comandos de turno
        if raw in ['iniciar turno', 'iniciar', 'comenzar turno', 'empezar turno', 'start']:
            iniciar_turno(from_phone)
            return

        if raw in ['terminar turno', 'terminar', 'finalizar turno', 'fin turno', 'stop']:
            terminar_turno(from_phone)
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
        
            # Estado: TRABAJANDO
        if state["state"] == TRABAJANDO:
            if raw in ['fin', 'finalizar', 'terminar', 'listo', 'terminado']:
                finalizar_ticket(from_phone)
                return
            
            if raw in ['pausar', 'pausa']:
                pausar_ticket(from_phone)
                return
            
            if raw in ['m', 'menu', 'menú', 'volver']:
                mostrar_menu(from_phone)
                return
            
            # Mensaje genérico cuando está trabajando
            send_whatsapp(
                from_phone,
                "⚙️ Tarea en progreso\n\n"
                "💡 Comandos:\n"
                "• 'fin' - Terminar tarea\n"
                "• 'pausar' - Pausar tarea\n"
                "• 'M' - Menú"
            )
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
    state = get_user_state(from_phone)
    turno_activo = state.get("turno_activo", False)
    
    if turno_activo:
        # Menú con turno activo
        if raw in ['1', 'ver tickets', 'tickets']:
            mostrar_tickets(from_phone)
            return
        
        if raw in ['2', 'reportar', 'reportar problema']:
            iniciar_reporte(from_phone)
            return
        
        if raw in ['3', 'terminar turno', 'fin turno']:
            terminar_turno(from_phone)
            return
        
        if raw in ['4', 'ayuda', 'help']:
            send_whatsapp(from_phone, texto_ayuda())
            return
    else:
        # Menú sin turno activo
        if raw in ['1', 'iniciar turno', 'iniciar']:
            iniciar_turno(from_phone)
            return
        
        if raw in ['2', 'ayuda', 'help']:
            send_whatsapp(from_phone, texto_ayuda())
            return
    
    # No reconocido
    from .ui_simple import texto_menu_simple
    send_whatsapp(
        from_phone,
        "❌ Opción no válida\n\n" + texto_menu_simple(turno_activo)
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
    verificar_turno_activo(from_phone)
    state = get_user_state(from_phone)

    mis_tickets = obtener_tickets_asignados_a(from_phone)

    mensaje = texto_lista_tickets(mis_tickets)
    send_whatsapp(from_phone, mensaje)

    state["state"] = VIENDO_TICKETS

def tomar_ticket(from_phone: str) -> None:
    """
    Toma el ticket de mayor prioridad asignado al worker.
    Actualiza estado en BD: ASIGNADO → EN_CURSO
    
    Args:
        from_phone: Número de teléfono del worker
    """
    verificar_turno_activo(from_phone)
    state = get_user_state(from_phone)
    
    # Si ya tiene ticket activo
    if state.get("ticket_activo_id"):
        from gateway_app.services.tickets_db import obtener_ticket_por_id
        ticket = obtener_ticket_por_id(state["ticket_activo_id"])
        if ticket:
            send_whatsapp(
                from_phone,
                f"⚠️ Ya tienes el ticket #{ticket['id']} en progreso\n\n"
                "💡 'fin' para terminarlo"
            )
            return
    
    # ✅ Buscar tickets asignados desde BD
    from gateway_app.services.tickets_db import obtener_tickets_asignados_a, actualizar_estado_ticket
    from gateway_app.services.db import execute
    
    tickets = obtener_tickets_asignados_a(from_phone)
    
    if not tickets:
        send_whatsapp(from_phone, "✅ No tienes tickets pendientes")
        return
    
    # Tomar el primer ticket (ya viene ordenado por prioridad)
    ticket = tickets[0]
    ticket_id = ticket["id"]
    
    # ✅ Actualizar estado en BD: ASIGNADO → EN_CURSO
    if actualizar_estado_ticket(ticket_id, "EN_CURSO"):
        # Registrar timestamps
        from datetime import datetime
        execute(
            "UPDATE public.tickets SET started_at = ?, accepted_at = ? WHERE id = ?",
            [datetime.now(), datetime.now(), ticket_id],
            commit=True
        )
        
        # Actualizar estado local
        state["ticket_activo_id"] = ticket_id
        state["state"] = TRABAJANDO
        
        # ✅ PERSISTIR ESTADO EN BD
        from gateway_app.flows.housekeeping.state_simple import persist_state
        persist_state(from_phone, state)
        
        # Notificar al worker
        prioridad_emoji = {"ALTA": "🔴", "MEDIA": "🟡", "BAJA": "🟢"}.get(
            ticket.get("prioridad", "MEDIA"), "🟡"
        )
        hab = ticket.get("ubicacion") or ticket.get("habitacion", "?")
        
        send_whatsapp(
            from_phone,
            f"✅ Tarea tomada\n\n"
            f"{prioridad_emoji} #{ticket_id} · Hab. {hab}\n"
            f"{ticket.get('detalle', 'Sin detalle')}\n\n"
            f"💡 Di 'fin' cuando termines"
        )
    else:
        send_whatsapp(from_phone, "❌ Error tomando tarea. Intenta de nuevo.")    



def finalizar_ticket(from_phone: str) -> None:
    """
    Finaliza el ticket activo.
    Actualiza estado en BD: EN_CURSO → RESUELTO
    
    Args:
        from_phone: Número de teléfono del worker
    """
    state = get_user_state(from_phone)
    
    # Verificar que tiene ticket activo
    ticket_id = state.get("ticket_activo_id")
    if not ticket_id:
        send_whatsapp(from_phone, "⚠️ No tienes ninguna tarea activa")
        return
    
    # ✅ Actualizar estado en BD: EN_CURSO → RESUELTO
    from gateway_app.services.tickets_db import actualizar_estado_ticket, obtener_ticket_por_id
    from gateway_app.services.db import execute
    from datetime import datetime
    
    if actualizar_estado_ticket(ticket_id, "RESUELTO"):
        # Registrar finished_at
        execute(
            "UPDATE public.tickets SET finished_at = ? WHERE id = ?",
            [datetime.now(), ticket_id],
            commit=True
        )
        
        # Limpiar estado local
        state["ticket_activo_id"] = None
        state["state"] = MENU
        
        # Persistir estado
        from gateway_app.flows.housekeeping.state_simple import persist_state
        persist_state(from_phone, state)
        
        # Notificar
        send_whatsapp(
            from_phone,
            f"✅ Tarea #{ticket_id} completada\n\n"
            f"🎉 ¡Buen trabajo!\n\n"
            f"💡 Di 'M' para el menú"
        )
        
        logger.info(f"✅ Ticket #{ticket_id} finalizado por {from_phone}")
    else:
        send_whatsapp(from_phone, "❌ Error finalizando tarea. Intenta de nuevo.")


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
    verificar_turno_activo(from_phone)
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
    logger.info("HK_CONFIRM from=%s raw=%r draft=%s", from_phone, raw, draft)

    
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
    
        # Volver al menú
    if raw in ['m', 'menu', 'menú', 'volver']:
        reset_ticket_draft(from_phone)
        send_whatsapp(from_phone, texto_menu_simple())
        state["state"] = MENU
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
    from gateway_app.services.tickets_db import crear_ticket, obtener_tickets_asignados_a


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
    Crea ticket desde el borrador y notifica al supervisor.
    
    Args:
        from_phone: Número de teléfono del worker
    """
    state = get_user_state(from_phone)

    # ✅ Guard: Solo crear si estamos en estado de confirmación
    if state.get("state") != CONFIRMANDO_REPORTE:
        logger.warning(
            "HK_CREATE_FROM_DRAFT ignored (state=%s) from=%s",
            state.get("state"),
            from_phone,
        )
        return

    draft = state.get("ticket_draft") or {}
    logger.info("HK_CREATE_FROM_DRAFT from=%s draft=%s", from_phone, draft)

    # VALIDACIÓN
    if not draft.get("habitacion") or not draft.get("detalle"):
        logger.warning("HK_CREATE_FROM_DRAFT missing_fields from=%s draft=%s", from_phone, draft)
        send_whatsapp(from_phone, "❌ Error: Falta información del reporte")
        reset_ticket_draft(from_phone)
        state["state"] = MENU
        return

    try:
        # Crear ticket en BD
        ticket = tickets_db.crear_ticket(
            habitacion=draft["habitacion"],
            detalle=draft["detalle"],
            prioridad=draft["prioridad"],
            creado_por=from_phone,
            origen="trabajador",
            canal_origen="WHATSAPP_BOT_HOUSEKEEPING",
            area="HOUSEKEEPING",
        )

        logger.info(
            "HK_CREATE_FROM_DRAFT db_return from=%s ticket_is_none=%s ticket=%s",
            from_phone,
            ticket is None,
            ticket,
        )

        if not ticket:
            send_whatsapp(from_phone, "❌ No pude crear el ticket en la base de datos.")
            reset_ticket_draft(from_phone)
            state["state"] = MENU
            return

        ticket_id = ticket["id"]
        logger.info("HK_CREATE_FROM_DRAFT created_id=%s from=%s", ticket_id, from_phone)

        # 1️⃣ Confirmar al worker
        mensaje = texto_ticket_creado(ticket_id, draft["habitacion"], draft["prioridad"])
        send_whatsapp(from_phone, mensaje)

        # 2️⃣ ✅ NOTIFICAR AL SUPERVISOR
        import os
        supervisor_phones = os.getenv("SUPERVISOR_PHONES", "").split(",")
        supervisor_phones = [p.strip() for p in supervisor_phones if p.strip()]
        
        if supervisor_phones:
            from gateway_app.services.whatsapp_client import send_whatsapp_text
            from gateway_app.services.workers_db import buscar_worker_por_telefono
            
            prioridad_emoji = {"ALTA": "🔴", "MEDIA": "🟡", "BAJA": "🟢"}.get(draft["prioridad"], "🟡")
            
            # Obtener nombre del worker
            worker = buscar_worker_por_telefono(from_phone)
            worker_nombre = worker.get("nombre_completo") if worker else "Trabajador"
            
            for supervisor_phone in supervisor_phones:
                send_whatsapp_text(
                    to=supervisor_phone,
                    body=f"📋 Nuevo reporte de {worker_nombre}\n\n"
                         f"#{ticket_id} · Hab. {draft['habitacion']}\n"
                         f"{draft['detalle']}\n"
                         f"{prioridad_emoji} Prioridad: {draft['prioridad']}\n\n"
                         f"💡 Di 'asignar {ticket_id} a [nombre]' para derivar"
                )
                logger.info(f"✅ Notificación enviada a supervisor {supervisor_phone}")

        # Limpiar y volver al menú
        reset_ticket_draft(from_phone)
        state["state"] = MENU

    except Exception as e:
        logger.exception("HK_CREATE_FROM_DRAFT exception from=%s err=%s", from_phone, e)
        send_whatsapp(from_phone, "❌ Error creando el ticket. Intenta de nuevo.")
        reset_ticket_draft(from_phone)
        state["state"] = MENU

def iniciar_turno(from_phone: str) -> None:
    """
    Inicia el turno del trabajador.
    
    Args:
        from_phone: Número de teléfono
    """
    from datetime import datetime
    state = get_user_state(from_phone)
    
    if state.get("turno_activo", False):
        send_whatsapp(from_phone, "⚠️ Tu turno ya está activo")
        return
    
    # Iniciar turno
    state["turno_activo"] = True
    state["turno_inicio"] = datetime.now().isoformat()
    state["turno_fin"] = None
    
    from .ui_simple import texto_menu_simple
    send_whatsapp(
        from_phone,
        "🟢 Turno iniciado\n\n"
        "¡Listo para trabajar! 💪"
    )
    send_whatsapp(from_phone, texto_menu_simple(turno_activo=True))
    state["state"] = MENU


def terminar_turno(from_phone: str) -> None:
    """
    Termina el turno del trabajador.
    
    Args:
        from_phone: Número de teléfono
    """
    from datetime import datetime
    state = get_user_state(from_phone)
    
    if not state.get("turno_activo", False):
        send_whatsapp(from_phone, "⚠️ No tienes turno activo")
        return
    
    # Verificar si tiene ticket activo
    if state.get("ticket_activo"):
        send_whatsapp(
            from_phone,
            "⚠️ No puedes terminar turno con tarea activa\n\n"
            "💡 Finaliza o pausa tu tarea primero"
        )
        return
    
    # Calcular duración
    inicio = state.get("turno_inicio")
    if inicio:
        from datetime import datetime
        inicio_dt = datetime.fromisoformat(inicio)
        fin_dt = datetime.now()
        duracion = fin_dt - inicio_dt
        horas = int(duracion.total_seconds() / 3600)
        minutos = int((duracion.total_seconds() % 3600) / 60)
        duracion_texto = f"{horas}h {minutos}min"
    else:
        duracion_texto = "No disponible"
    
    # Terminar turno
    state["turno_activo"] = False
    state["turno_fin"] = datetime.now().isoformat()
    
    send_whatsapp(
        from_phone,
        f"🔴 Turno terminado\n\n"
        f"⏱️ Duración: {duracion_texto}\n"
        f"¡Buen trabajo! 👏"
    )
    state["state"] = MENU