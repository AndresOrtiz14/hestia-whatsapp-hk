"""
Orquestador simplificado para bot de Housekeeping.
VERSIÓN MULTI-TICKET: Permite trabajar en varios tickets simultáneamente.
"""
import logging

from gateway_app.flows.supervision import state

logger = logging.getLogger(__name__)

from gateway_app.services.tickets_db import crear_ticket
from gateway_app.services import tickets_db
from zoneinfo import ZoneInfo

from gateway_app.flows.housekeeping.turno_auto import verificar_y_activar_turno_auto

from datetime import date, datetime, timezone
from .state_simple import (
    get_user_state,
    reset_ticket_draft,
    persist_user_state,
    MENU,
    VIENDO_TICKETS,
    TRABAJANDO,
    REPORTANDO_HAB,
    REPORTANDO_DETALLE,
    CONFIRMANDO_REPORTE
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
    texto_confirmar_reporte
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

# ✅ NUEVO: Soporte para áreas comunes
from .areas_comunes_helpers import (
    obtener_area_worker,
    extraer_ubicacion_generica,
    detectar_reporte_directo_adaptado,
    get_texto_por_area,
    formatear_ubicacion_para_mensaje
)

from .media_handler import handle_media_context_response, handle_media_detail_response

def verificar_turno_activo(from_phone: str, tenant=None) -> bool:
    """
    Verifica si el turno está activo.
    YA NO auto-inicia - eso lo hace turno_auto.py
    """
    from gateway_app.services.workers_db import activar_turno_por_telefono
    
    state = get_user_state(from_phone)
    
    # Si ya está activo, OK
    if state.get("turno_activo", False):
        return True
    
    # Si fue auto-activado recientemente (por turno_auto), no duplicar mensaje
    if state.get("turno_auto_activado"):
        del state["turno_auto_activado"]
        return True
    
    # Auto-iniciar turno silenciosamente (para acciones que requieren turno)
    from datetime import datetime
    ok = activar_turno_por_telefono(from_phone, property_id=tenant.property_id if tenant else "")
    if ok:
        state["turno_activo"] = True
        state["turno_inicio"] = datetime.now().isoformat()
        
        send_whatsapp(
            from_phone,
            "🟢 Turno iniciado automáticamente\n\n"
            "💡 Para terminar tu turno, escribe 'terminar turno'"
        )
    
    return True

import re

def _norm_txt(s: str) -> str:
    s = (s or "").strip().lower()
    return (s.replace("á","a").replace("é","e").replace("í","i").replace("ó","o").replace("ú","u"))

def _extract_ticket_id_any(s: str):
    m = re.search(r"\b(\d+)\b", s or "")
    return int(m.group(1)) if m else None

def maybe_handle_tomar_anywhere(from_phone: str, text: str, state: dict) -> bool:
    """
    Maneja 'tomar' desde cualquier estado.
    Regla: si el mensaje incluye un número -> tomar ese ticket_id (no "el siguiente").
    """
    raw = (text or "").strip().lower()

    # Solo reaccionamos a comandos de tomar/aceptar o números directos (cuando están viendo tickets).
    triggers = (
        raw.startswith("tomar") or
        raw.startswith("aceptar") or
        raw in {"tomo", "tomarlo"} or
        (raw.isdigit() and state.get("state") == VIENDO_TICKETS)
    )
    if not triggers:
        return False

    import re
    m = re.search(r"\b(\d{1,6})\b", raw)

    from gateway_app.services.tickets_db import (
        obtener_ticket_por_id,
        obtener_tickets_por_worker,
        actualizar_ticket_estado,
    )
    from .outgoing import send_whatsapp

    # 1) Caso: "tomar <id>" o "aceptar <id>" o número directo en VIENDO_TICKETS
    if m:
        ticket_id = int(m.group(1))

        # ✅ VALIDAR ASIGNACIÓN contra "mis tickets" (fuente consistente)
        tickets_mios = obtener_tickets_por_worker(from_phone) or []
        ticket = next(
            (t for t in tickets_mios if str(t.get("id")) == str(ticket_id)),
            None
        )

        # Si no está en mis tickets, ahí sí reviso si existe para dar mejor mensaje
        if not ticket:
            ticket_existe = obtener_ticket_por_id(ticket_id)
            if not ticket_existe:
                send_whatsapp(from_phone, f"❌ No encontré la tarea #{ticket_id}.")
            else:
                send_whatsapp(from_phone, f"❌ La tarea #{ticket_id} no está asignada a ti.")
            return True

        estado = str(ticket.get("estado") or "").upper()
        if estado == "RESUELTO":
            send_whatsapp(from_phone, f"✅ La tarea #{ticket_id} ya está resuelta.")
            return True

        if estado == "EN_CURSO":
            send_whatsapp(from_phone, f"⚙️ La tarea #{ticket_id} ya está en curso.")
            return True

        # Solo tiene sentido tomar si está ASIGNADO (o si tú permites PENDIENTE)
        if estado != "ASIGNADO":
            send_whatsapp(from_phone, f"⚠️ La tarea #{ticket_id} está en estado {estado} y no se puede 'tomar'.")
            return True

        ok = actualizar_ticket_estado(ticket_id, "EN_CURSO")
        if not ok:
            send_whatsapp(from_phone, "❌ No pude tomar la tarea. Intenta de nuevo.")
            return True

        # ✅ Marca estado runtime (importante: guarda el id activo)
        state["state"] = TRABAJANDO
        state["ticket_activo_id"] = ticket_id
        
        ubic = ticket.get("ubicacion") or ticket.get("habitacion") or "?"
        detalle = ticket.get("detalle") or ticket.get("descripcion") or "Sin detalle"
        prioridad = str(ticket.get("prioridad") or "MEDIA").upper()
        p_emoji = {"ALTA": "🔴", "MEDIA": "🟡", "BAJA": "🟢"}.get(prioridad, "🟡")

        # Conteo activos
        tickets = obtener_tickets_por_worker(from_phone) or []
        activos = [t for t in tickets if str(t.get("estado", "")).upper() == "EN_CURSO"]

        send_whatsapp(
            from_phone,
            "✅ Tarea tomada\n\n"
            f"{p_emoji} #{ticket_id} · Hab. {ubic}\n"
            f"{detalle}\n\n"
            f"📊 Tienes {len(activos)} tarea(s) activa(s)\n\n"
            f"💡 'fin {ticket_id}' cuando termines\n"
            "💡 'activos' para ver todas"
        )
        return True

    # 2) Caso: "tomar" sin número -> tomar SOLO si hay 1 ASIGNADO; si hay varios, pedir cuál
    from gateway_app.services.tickets_db import obtener_tickets_por_worker

    tickets = obtener_tickets_por_worker(from_phone) or []
    asignados = [t for t in tickets if str(t.get("estado", "")).upper() == "ASIGNADO"]

    if not asignados:
        send_whatsapp(from_phone, "✅ No tienes tareas ASIGNADAS para tomar ahora.")
        return True

    if len(asignados) == 1:
        # Re-entrar usando el ID del único asignado (misma ruta que arriba)
        unico_id = int(asignados[0]["id"])
        return maybe_handle_tomar_anywhere(from_phone, f"tomar {unico_id}", state)

    # Hay varios asignados: pedir ID explícito
    ids = ", ".join([str(t.get("id")) for t in asignados[:8]])
    send_whatsapp(
        from_phone,
        "📋 Tienes varias tareas asignadas.\n"
        "Indica cuál quieres tomar:\n\n"
        f"Ejemplo: 'tomar {asignados[0]['id']}'\n"
        f"Asignadas: {ids}"
    )
    return True

def handle_hk_message_simple(from_phone: str, text: str, tenant=None) -> None:
    state = get_user_state(from_phone)

    from gateway_app.flows.housekeeping.turno_auto import verificar_y_activar_turno_auto
    mensaje_turno_auto = verificar_y_activar_turno_auto(from_phone, state, tenant=tenant)
    if mensaje_turno_auto:
        send_whatsapp(from_phone, mensaje_turno_auto)
        # NO hacer return aquí - dejar que continúe procesando el mensaje
        
    if state.get("media_pendiente"):
        from .media_handler import handle_media_context_response
        if handle_media_context_response(from_phone, text, tenant=tenant):
            return

    if state.get("media_para_ticket"):
        from .media_handler import handle_media_detail_response
        if handle_media_detail_response(from_phone, text, tenant=tenant):
            return

    try:
        raw = (text or "").strip().lower()
        logger.info(f"🏨 HK | {from_phone} | Comando: '{raw[:30]}...'")

        # ✅ PEGAR AQUÍ (antes de saludo/menú)
        if maybe_handle_tomar_anywhere(from_phone, text, state):
            return
        
        # ✅ NUEVO: Detectar y guardar área del worker
        if "area_worker" not in state:
            area_worker = obtener_area_worker(from_phone, tenant=tenant)
            state["area_worker"] = area_worker
            logger.info(f"📍 Worker {from_phone} detectado como área: {area_worker}")
        else:
            area_worker = state["area_worker"]
        logger.info(f"🔍 DEBUG - Area worker: {area_worker}, Estado: {state.get('state')}, Texto: '{text[:50]}'")

        # ✅ 0) COMANDO GLOBAL MÁS PRIORITARIO: Menú (SIEMPRE funciona, incluso en errores)
        if raw in ['m', 'menu', 'menú', 'volver', 'salir', 'reiniciar', 'reset']:
            # Limpiar cualquier estado de error o flujo
            reset_ticket_draft(from_phone)
            state["state"] = MENU
            
            # Enviar menú según estado del turno
            turno_activo = state.get("turno_activo", False)
            from .ui_simple import texto_menu_simple
            send_whatsapp(from_phone, texto_menu_simple(turno_activo))
            
            logger.info(f"🔄 Worker {from_phone} reinició al menú (estado limpio)")
            return

        # 1) Saludo inicial del día
        today_str = date.today().isoformat()
        if state.get("last_greet_date") != today_str:
            state["last_greet_date"] = today_str
            turno_activo = state.get("turno_activo", False)
            
            from .ui_simple import texto_saludo_con_turno
            send_whatsapp(from_phone, texto_saludo_con_turno(turno_activo))
            state["state"] = MENU
            return
        
        # ✅ 2.3) COMANDO GLOBAL: Finalizar ticket (con o sin número)
        if raw.startswith('fin') or raw in ['finalizar', 'terminar', 'listo', 'terminado', 'completar']:
            # Intentar extraer número de ticket: "fin 15", "finalizar 12"
            import re
            match = re.search(r'\b(\d{1,4})\b', raw)
            
            if match:
                # Tiene número específico
                ticket_id = int(match.group(1))
                finalizar_ticket_especifico(from_phone, ticket_id)
            else:
                # Sin número: finalizar el único activo o preguntar cuál
                finalizar_ticket_interactivo(from_phone)
            return
        
        # ✅ 2.4) COMANDO GLOBAL: Pausar ticket (con o sin número)
        if raw.startswith('pausar') or raw == 'pausa':
            import re
            match = re.search(r'\b(\d{1,4})\b', raw)
            
            if match:
                ticket_id = int(match.group(1))
                pausar_ticket_especifico(from_phone, ticket_id)
            else:
                pausar_ticket_interactivo(from_phone)
            return
        
        # ✅ 2.5) COMANDO GLOBAL: Reanudar ticket (con número)
        if raw.startswith('reanudar') or raw.startswith('continuar'):
            import re
            match = re.search(r'\b(\d{1,4})\b', raw)
            
            if match:
                ticket_id = int(match.group(1))
                reanudar_ticket_especifico(from_phone, ticket_id)
            else:
                send_whatsapp(from_phone, "💡 Indica qué tarea: 'reanudar [#]'")
            return
        
        # 2.7) Comandos de turno
        if raw in ['iniciar turno', 'iniciar', 'comenzar turno', 'empezar turno', 'start']:
            iniciar_turno(from_phone, tenant=tenant)
            return

        if raw in ['terminar turno', 'terminar', 'finalizar turno', 'fin turno', 'stop']:
            terminar_turno(from_phone, tenant=tenant)
            return
        
        # 2.8) Navegación directa de menú (desde cualquier estado)
        if raw in ['1', '2', '3', '4'] and state.get("state") not in [REPORTANDO_HAB, REPORTANDO_DETALLE, CONFIRMANDO_REPORTE]:
            turno_activo = state.get("turno_activo", False)
            handle_menu(from_phone, raw, tenant=tenant)
            return
        
        # 3) Detectar reporte directo adaptado al área del worker
        current_state = state.get("state")
        if current_state not in [REPORTANDO_HAB, REPORTANDO_DETALLE, CONFIRMANDO_REPORTE]:
            logger.info(f"🔍 DETECCIÓN - Intentando detectar reporte directo para área: {area_worker}")

            reporte = detectar_reporte_directo_adaptado(text, area_worker)
            logger.info(f"🔍 RESULTADO - Reporte detectado: {reporte}")
            
            if reporte:
                # En vez de crear ticket directo, armamos draft + pedimos confirmación
                draft = state.get("ticket_draft") or {}
                draft.clear()

                ubic = reporte.get("ubicacion")
                detalle = reporte.get("detalle")
                prioridad = reporte.get("prioridad", "MEDIA")

                # Normalizamos (habitacion/ubicacion) para que jamás quede None
                if ubic is not None:
                    ubic = str(ubic).strip()

                draft["ubicacion"] = ubic
                draft["habitacion"] = ubic
                draft["detalle"] = detalle
                draft["prioridad"] = prioridad

                state["ticket_draft"] = draft
                state["state"] = CONFIRMANDO_REPORTE

                # Confirmación (adaptada por área)
                from .ui_simple import texto_confirmar_reporte_adaptado
                mensaje = texto_confirmar_reporte_adaptado(ubic, detalle, prioridad, area_worker)
                send_whatsapp(from_phone, mensaje)
                return
        
        # 4) Comandos globales
        if es_comando_reportar(raw):
            iniciar_reporte(from_phone)
            return
        
        if raw in ['tickets', 'ver tickets', 'mis tickets', 'mis tareas']:
            mostrar_tickets(from_phone)
            return
        
        # ✅ NUEVO: Ver tickets activos (en progreso)
        if raw in ['activos', 'en curso', 'trabajando', 'progreso']:
            mostrar_tickets_activos(from_phone)
            return
        
        # 5) Routing por estado
        current_state = state.get("state")
        
        if current_state == MENU:
            handle_menu(from_phone, raw, tenant=tenant)
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
        
        if state["state"] == TRABAJANDO:
            # Mensaje genérico cuando está trabajando
            send_whatsapp(
                from_phone,
                "⚙️ Trabajando en tarea(s)\n\n"
                "💡 Comandos:\n"
                "• 'activos' - Ver tus tareas activas\n"
                "• 'fin [#]' - Terminar tarea específica\n"
                "• 'pausar [#]' - Pausar tarea\n"
                "• 'tomar' - Tomar otra tarea\n"
                "• 'M' - Menú"
            )
            return
        
        # 6) No entendí
        send_whatsapp(
            from_phone,
            "🤔 No entendí.\n\n"
            "💡 Puedes decir:\n"
            "• 'tomar' - Tomar ticket\n"
            "• 'activos' - Ver tus tareas activas\n"
            "• 'fin [#]' - Terminar tarea\n"
            "• 'tickets' - Ver tus tickets\n"
            "• 'reportar' - Reportar problema\n"
            "• 'M' - Menú"
    )
    finally:
        # Persist full state at end of processing
        persist_user_state(from_phone, state)


def handle_menu(from_phone: str, raw: str, tenant=None) -> None:
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
            terminar_turno(from_phone, tenant=tenant)
            return
        
        if raw in ['4', 'ayuda', 'help']:
            send_whatsapp(from_phone, texto_ayuda())
            return
    else:
        # Menú sin turno activo
        if raw in ['1', 'iniciar turno', 'iniciar']:
            iniciar_turno(from_phone, tenant=tenant)
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
    # al inicio de handle_viendo_tickets(...)
    if maybe_handle_tomar_anywhere(from_phone, raw, state):
        return

    # Comando: tomar
    if es_comando_tomar(raw):
        tomar_ticket(from_phone)
        return
    
    # Volver
    send_whatsapp(from_phone, "💡 Di 'tomar' o 'M'")


def mostrar_tickets(from_phone: str) -> None:
    """
    Muestra tickets (tareas) asignados al worker desde la BD real: public.tickets
    """
    verificar_turno_activo(from_phone, tenant=tenant)
    state = get_user_state(from_phone)

    mis_tickets = obtener_tickets_asignados_a(from_phone)

    mensaje = texto_lista_tickets(mis_tickets)
    send_whatsapp(from_phone, mensaje)

    state["state"] = VIENDO_TICKETS


def mostrar_tickets_activos(from_phone: str) -> None:
    """
    ✅ NUEVO: Muestra solo los tickets EN_CURSO del worker.
    """
    tickets = obtener_tickets_asignados_a(from_phone)
    tickets_activos = [t for t in tickets if t.get('estado') == 'EN_CURSO']
    
    if not tickets_activos:
        send_whatsapp(from_phone, "✅ No tienes tareas activas\n\n💡 Di 'tickets' para ver tus asignaciones")
        return
    
    lineas = [f"⚙️ {len(tickets_activos)} tarea(s) activa(s):\n"]
    
    for ticket in tickets_activos:
        prioridad_emoji = {"ALTA": "🔴", "MEDIA": "🟡", "BAJA": "🟢"}.get(
            ticket.get("prioridad", "MEDIA"), "🟡"
        )
        
        ubicacion = ticket.get("ubicacion") or ticket.get("habitacion", "?")
        detalle = ticket.get("detalle", "Sin detalle")[:30]
        
        # Calcular tiempo trabajando
        started_at = ticket.get("started_at")
        if started_at:
            try:
                from dateutil import parser
                if isinstance(started_at, str):
                    started_at = parser.parse(started_at)
                tiempo_mins = int((datetime.now(started_at.tzinfo) - started_at).total_seconds() / 60)
            except Exception:
                tiempo_mins = 0
        else:
            tiempo_mins = 0
        
        lineas.append(
            f"{prioridad_emoji} #{ticket['id']} · Hab. {ubicacion} · {tiempo_mins} min\n"
            f"   {detalle}"
        )
    
    lineas.append("\n💡 'fin [#]' para terminar | 'pausar [#]' para pausar")
    
    send_whatsapp(from_phone, "\n".join(lineas))


def tomar_ticket(from_phone: str) -> None:
    """
    ✅ MODIFICADO: Permite tomar múltiples tickets.
    Ya no verifica si hay ticket activo, solo toma el siguiente disponible.
    """
    verificar_turno_activo(from_phone, tenant=tenant)
    state = get_user_state(from_phone)
    
    # ✅ Buscar tickets ASIGNADOS desde BD
    from gateway_app.services.tickets_db import obtener_tickets_asignados_a, actualizar_estado_ticket
    from gateway_app.services.db import execute
    
    tickets = obtener_tickets_asignados_a(from_phone)
    tickets_asignados = [t for t in tickets if t.get('estado') == 'ASIGNADO']
    
    if not tickets_asignados:
        # Ver si tiene tickets EN_CURSO
        tickets_en_curso = [t for t in tickets if t.get('estado') == 'EN_CURSO']
        if tickets_en_curso:
            send_whatsapp(
                from_phone,
                f"✅ Ya tienes {len(tickets_en_curso)} tarea(s) activa(s)\n\n"
                f"💡 Di 'activos' para verlas"
            )
        else:
            send_whatsapp(from_phone, "✅ No tienes tickets pendientes por tomar")
        return
    
    # Tomar el primer ticket asignado
    ticket = tickets_asignados[0]
    ticket_id = ticket["id"]
    
    # ✅ Actualizar estado en BD: ASIGNADO → EN_CURSO
    if actualizar_estado_ticket(ticket_id, "EN_CURSO"):
        # ✅ FIX M9: Usar timezone-aware para compatibilidad con PostgreSQL TIMESTAMPTZ
        from datetime import datetime, timezone
        now_utc = datetime.now(timezone.utc)
        execute(
            "UPDATE public.tickets SET started_at = ?, accepted_at = ? WHERE id = ?",
            [now_utc, now_utc, ticket_id],
            commit=True
        )
        
        # Actualizar estado local (agregar a lista en lugar de reemplazar)
        state["state"] = TRABAJANDO
        persist_user_state(from_phone, state)
        
        # Notificar al worker
        prioridad_emoji = {"ALTA": "🔴", "MEDIA": "🟡", "BAJA": "🟢"}.get(
            ticket.get("prioridad", "MEDIA"), "🟡"
        )
        hab = ticket.get("ubicacion") or ticket.get("habitacion", "?")
        
        # Contar tickets activos
        tickets_activos_total = len([t for t in tickets if t.get('estado') == 'EN_CURSO']) + 1
        
        send_whatsapp(
            from_phone,
            f"✅ Tarea tomada\n\n"
            f"{prioridad_emoji} #{ticket_id} · Hab. {hab}\n"
            f"{ticket.get('detalle', 'Sin detalle')}\n\n"
            f"📊 Tienes {tickets_activos_total} tarea(s) activa(s)\n\n"
            f"💡 'fin {ticket_id}' cuando termines\n"
            f"💡 'activos' para ver todas"
        )
    else:
        send_whatsapp(from_phone, "❌ Error tomando tarea. Intenta de nuevo.\n\n💡 Di 'M' para volver al menú")


def finalizar_ticket_interactivo(from_phone: str) -> None:
    """
    ✅ NUEVO: Finaliza ticket de forma interactiva.
    Si tiene uno solo, lo finaliza. Si tiene varios, pide cuál.
    """
    tickets = obtener_tickets_asignados_a(from_phone)
    tickets_en_curso = [t for t in tickets if t.get('estado') == 'EN_CURSO']
    
    if not tickets_en_curso:
        send_whatsapp(from_phone, "⚠️ No tienes ninguna tarea activa\n\n💡 Di 'M' para volver al menú")
        return
    
    if len(tickets_en_curso) == 1:
        # Solo una: finalizar directamente
        finalizar_ticket_especifico(from_phone, tickets_en_curso[0]['id'])
    else:
        # Varias: preguntar cuál
        lineas = [f"Tienes {len(tickets_en_curso)} tareas activas:\n"]
        
        for ticket in tickets_en_curso:
            ubicacion = ticket.get("ubicacion") or ticket.get("habitacion", "?")
            lineas.append(f"• #{ticket['id']} - Hab. {ubicacion}")
        
        lineas.append("\n💡 Indica cuál: 'fin [#]'")
        send_whatsapp(from_phone, "\n".join(lineas))


def finalizar_ticket_especifico(from_phone: str, ticket_id: int) -> None:
    """
    ✅ NUEVO: Finaliza un ticket específico por su ID.
    """
    from gateway_app.services.tickets_db import actualizar_estado_ticket, obtener_ticket_por_id
    from gateway_app.services.db import execute
    from datetime import datetime
    
    # Verificar que el ticket existe y está EN_CURSO
    ticket_data = obtener_ticket_por_id(ticket_id)
    
    if not ticket_data:
        send_whatsapp(from_phone, f"❌ No encontré la tarea #{ticket_id}\n\n💡 Di 'M' para volver al menú")
        return
    
    # Verificar que pertenece al worker
    huesped_whatsapp = ticket_data.get("huesped_whatsapp", "")
    if from_phone not in huesped_whatsapp:
        send_whatsapp(from_phone, f"❌ La tarea #{ticket_id} no está asignada a ti\n\n💡 Di 'M' para volver al menú")
        return
    
    # Verificar que está EN_CURSO
    if ticket_data.get("estado") != "EN_CURSO":
        send_whatsapp(from_phone, f"⚠️ La tarea #{ticket_id} no está en progreso\n\n💡 Di 'M' para volver al menú")
        return
    
# ✅ Actualizar estado en BD: EN_CURSO → RESUELTO
    if actualizar_estado_ticket(ticket_id, "RESUELTO"):
        # ✅ FIX A7: Usar timezone-aware para compatibilidad con PostgreSQL TIMESTAMPTZ
        from datetime import timezone
        now = datetime.now(timezone.utc)
        execute(
            "UPDATE public.tickets SET finished_at = ? WHERE id = ?",
            [now, ticket_id],
            commit=True
        )
        
        # ✅ CALCULAR TIEMPO DE RESOLUCIÓN
        started_at = ticket_data.get("started_at")
        if started_at:
            if isinstance(started_at, str):
                from dateutil import parser
                started_at = parser.parse(started_at)
            # FIX: if DB returned a naive datetime, treat it as UTC
            if started_at.tzinfo is None:
                started_at = started_at.replace(tzinfo=timezone.utc)

            duracion = now - started_at
            minutos_totales = int(duracion.total_seconds() / 60)
            
            if minutos_totales < 60:
                tiempo_texto = f"{minutos_totales} min"
            else:
                horas = minutos_totales // 60
                minutos = minutos_totales % 60
                tiempo_texto = f"{horas}h {minutos}min" if minutos > 0 else f"{horas}h"
        else:
            tiempo_texto = "No disponible"
            minutos_totales = 0
        
        # ✅ NOTIFICAR AL SUPERVISOR
        from gateway_app.services.workers_db import obtener_supervisores_por_area as _get_sups_hk
        _ticket_area = ticket_data.get("area", "HOUSEKEEPING")
        _sups = _get_sups_hk(_ticket_area, property_id=tenant.property_id if tenant else "")
        supervisor_phones = [s["telefono"] for s in _sups if s.get("telefono")]

        if supervisor_phones:
            from gateway_app.services.whatsapp_client import send_whatsapp_text
            from gateway_app.services.workers_db import buscar_worker_por_telefono

            worker = buscar_worker_por_telefono(from_phone, property_id=tenant.property_id if tenant else "")
            worker_nombre = worker.get("nombre_completo") if worker else "Trabajador"
            
            prioridad_emoji = {"ALTA": "🔴", "MEDIA": "🟡", "BAJA": "🟢"}.get(
                ticket_data.get("prioridad", "MEDIA"), "🟡"
            )
            
            if minutos_totales <= 15:
                tiempo_emoji = "⚡"
            elif minutos_totales <= 30:
                tiempo_emoji = "✅"
            else:
                tiempo_emoji = "🕐"
            
            ubicacion = ticket_data.get("ubicacion") or ticket_data.get("habitacion", "?")
            
            for supervisor_phone in supervisor_phones:
                send_whatsapp_text(
                    to=supervisor_phone,
                    body=f"✅ Tarea completada por {worker_nombre}\n\n"
                         f"#{ticket_id} · Hab. {ubicacion}\n"
                         f"{ticket_data.get('detalle', 'Sin detalle')}\n"
                         f"{prioridad_emoji} Prioridad: {ticket_data.get('prioridad', 'MEDIA')}\n"
                         f"{tiempo_emoji} Tiempo: {tiempo_texto}"
                )
                logger.info(f"✅ Notificación de finalización enviada a supervisor {supervisor_phone}")
        
        # Verificar si aún tiene tickets activos
        tickets = obtener_tickets_asignados_a(from_phone)
        tickets_activos = [t for t in tickets if t.get('estado') == 'EN_CURSO']
        
        # Actualizar estado
        state = get_user_state(from_phone)
        if len(tickets_activos) == 0:
            state["state"] = MENU
        persist_user_state(from_phone, state)
        
        # Notificar al worker
        if len(tickets_activos) > 0:
            send_whatsapp(
                from_phone,
                f"✅ Tarea #{ticket_id} completada\n\n"
                f"⏱️ Tiempo: {tiempo_texto}\n"
                f"🎉 ¡Buen trabajo!\n\n"
                f"📊 Tienes {len(tickets_activos)} tarea(s) activa(s)\n"
                f"💡 'activos' para verlas"
            )
        else:
            send_whatsapp(
                from_phone,
                f"✅ Tarea #{ticket_id} completada\n\n"
                f"⏱️ Tiempo: {tiempo_texto}\n"
                f"🎉 ¡Buen trabajo!\n\n"
                f"✨ No tienes más tareas activas\n"
                f"💡 Di 'M' para el menú"
            )
        
        logger.info(f"✅ Ticket #{ticket_id} finalizado por {from_phone} en {tiempo_texto}")
    else:
        send_whatsapp(from_phone, "❌ Error finalizando tarea. Intenta de nuevo.\n\n💡 Di 'M' para volver al menú")


def pausar_ticket_interactivo(from_phone: str) -> None:
    """
    ✅ NUEVO: Pausa ticket de forma interactiva.
    """
    tickets = obtener_tickets_asignados_a(from_phone)
    tickets_en_curso = [t for t in tickets if t.get('estado') == 'EN_CURSO']
    
    if not tickets_en_curso:
        send_whatsapp(from_phone, "⚠️ No tienes ninguna tarea activa\n\n💡 Di 'M' para volver al menú")
        return
    
    if len(tickets_en_curso) == 1:
        pausar_ticket_especifico(from_phone, tickets_en_curso[0]['id'])
    else:
        lineas = [f"Tienes {len(tickets_en_curso)} tareas activas:\n"]
        
        for ticket in tickets_en_curso:
            ubicacion = ticket.get("ubicacion") or ticket.get("habitacion", "?")
            lineas.append(f"• #{ticket['id']} - Hab. {ubicacion}")
        
        lineas.append("\n💡 Indica cuál: 'pausar [#]'")
        send_whatsapp(from_phone, "\n".join(lineas))


def pausar_ticket_especifico(from_phone: str, ticket_id: int) -> None:
    """
    ✅ NUEVO: Pausa un ticket específico.
    """
    from gateway_app.services.tickets_db import actualizar_estado_ticket, obtener_ticket_por_id
    
    ticket_data = obtener_ticket_por_id(ticket_id)
    
    if not ticket_data:
        send_whatsapp(from_phone, f"❌ No encontré la tarea #{ticket_id}\n\n💡 Di 'M' para volver al menú")
        return
    
    if ticket_data.get("estado") != "EN_CURSO":
        send_whatsapp(from_phone, f"⚠️ La tarea #{ticket_id} no está en progreso\n\n💡 Di 'M' para volver al menú")
        return
    
    # Actualizar a PAUSADO
    if actualizar_estado_ticket(ticket_id, "PAUSADO"):
        ubicacion = ticket_data.get("ubicacion") or ticket_data.get("habitacion", "?")
        
        send_whatsapp(
            from_phone,
            f"⏸️ Tarea #{ticket_id} pausada\n\n"
            f"📍 Hab. {ubicacion}\n\n"
            f"💡 'reanudar {ticket_id}' para continuar"
        )
    else:
        send_whatsapp(from_phone, "❌ Error pausando tarea\n\n💡 Di 'M' para volver al menú")


def reanudar_ticket_especifico(from_phone: str, ticket_id: int) -> None:
    """
    ✅ NUEVO: Reanuda un ticket pausado.
    """
    from gateway_app.services.tickets_db import actualizar_estado_ticket, obtener_ticket_por_id
    
    ticket_data = obtener_ticket_por_id(ticket_id)
    
    if not ticket_data:
        send_whatsapp(from_phone, f"❌ No encontré la tarea #{ticket_id}\n\n💡 Di 'M' para volver al menú")
        return
    
    if ticket_data.get("estado") != "PAUSADO":
        send_whatsapp(from_phone, f"⚠️ La tarea #{ticket_id} no está pausada\n\n💡 Di 'M' para volver al menú")
        return
    
    # Actualizar a EN_CURSO
    if actualizar_estado_ticket(ticket_id, "EN_CURSO"):
        ubicacion = ticket_data.get("ubicacion") or ticket_data.get("habitacion", "?")
        
        send_whatsapp(
            from_phone,
            f"▶️ Tarea #{ticket_id} reanudada\n\n"
            f"📍 Hab. {ubicacion}\n\n"
            f"💡 'fin {ticket_id}' cuando termines"
        )
    else:
        send_whatsapp(from_phone, "❌ Error reanudando tarea\n\n💡 Di 'M' para volver al menú")


def iniciar_reporte(from_phone: str) -> None:
    """
    Inicia el flujo de reportar problema.
    
    Args:
        from_phone: Número de teléfono
    """
    verificar_turno_activo(from_phone, tenant=tenant)
    state = get_user_state(from_phone)
    reset_ticket_draft(from_phone)
    
    # ✅ MODIFICADO: Mensaje adaptado al área del worker
    area_worker = state.get("area_worker", "HOUSEKEEPING")
    mensaje = get_texto_por_area(area_worker, "ubicacion_pregunta")
    
    state["state"] = REPORTANDO_HAB
    send_whatsapp(from_phone, mensaje)


def handle_reportando_habitacion(from_phone: str, text: str) -> None:
    """
    Maneja la respuesta cuando está pidiendo ubicación (habitación o área).
    """
    from .ui_simple import texto_confirmar_reporte_adaptado

    state = get_user_state(from_phone)
    area_worker = state.get("area_worker", "HOUSEKEEPING")
    state.setdefault("ticket_draft", {})
    
    # ✅ MODIFICADO: Detectar reporte completo adaptado
    reporte_completo = detectar_reporte_directo_adaptado(text, area_worker)
    
    if reporte_completo:
        ubic = str(reporte_completo["ubicacion"])
        state["ticket_draft"]["ubicacion"] = ubic
        state["ticket_draft"]["habitacion"] = ubic      # ✅ compatibilidad
        state["draft_habitacion"] = ubic
        state["ticket_draft"]["detalle"] = reporte_completo["detalle"]
        state["ticket_draft"]["prioridad"] = reporte_completo["prioridad"]
        state["state"] = CONFIRMANDO_REPORTE
        
        # ✅ MODIFICADO: Confirmación adaptada
        mensaje = texto_confirmar_reporte_adaptado(
            reporte_completo["ubicacion"],
            reporte_completo["detalle"],
            reporte_completo["prioridad"],
            area_worker
        )
        send_whatsapp(from_phone, mensaje)
        return
    
    # ✅ MODIFICADO: Extracción adaptada
    ubicacion = extraer_ubicacion_generica(text, area_worker)
    
    if not ubicacion:
        # ✅ MODIFICADO: Mensaje de error adaptado
        ejemplo = get_texto_por_area(area_worker, "ubicacion_ejemplo")
        send_whatsapp(
            from_phone, 
            f"❌ No entendí la ubicación\n\n"
            f"💡 Ejemplo: {ejemplo}\n"
            f"O di 'M' para volver al menú"
        )
        return
    
    ubic = str(ubicacion)
    state["ticket_draft"]["ubicacion"] = ubic
    state["ticket_draft"]["habitacion"] = ubic
    state["draft_habitacion"] = ubic
    state["state"] = REPORTANDO_DETALLE
    
    send_whatsapp(from_phone, texto_pedir_detalle())


def handle_reportando_detalle(from_phone: str, text: str) -> None:
    """
    Maneja el detalle del problema.
    """
    from .ui_simple import texto_confirmar_reporte_adaptado

    state = get_user_state(from_phone)
    draft = state["ticket_draft"]
    area_worker = state.get("area_worker", "HOUSEKEEPING")
    
    draft["detalle"] = text
    draft["prioridad"] = detectar_prioridad(text)
    state["state"] = CONFIRMANDO_REPORTE
    
    # ✅ MODIFICADO: Usar campo genérico y función adaptada
    mensaje = texto_confirmar_reporte_adaptado(
        draft.get("ubicacion", draft.get("habitacion", "?")),  # Compatibilidad
        draft["detalle"],
        draft["prioridad"],
        area_worker
    )
    send_whatsapp(from_phone, mensaje)


def handle_confirmando_reporte(from_phone: str, raw: str) -> None:
    """
    Maneja la confirmación del reporte.
    """
    state = get_user_state(from_phone)
    draft = state.get("ticket_draft") or {}
    state["ticket_draft"] = draft

    logger.info("HK_CONFIRM from=%s raw=%r draft=%s", from_phone, raw, draft)
    # ✅ Blindaje: si "habitacion" quedó None pero "ubicacion" sí viene, unificamos
    ubic = (
        draft.get("habitacion")
        or draft.get("ubicacion")
        or state.get("draft_habitacion")
    )

    if ubic:
        ubic = str(ubic).strip()
        draft["habitacion"] = ubic
        draft["ubicacion"] = ubic

    
    if raw in ['si', 'sí', 'yes', 'ok', 'confirmar', 'confirmo', 'dale', 'correcto']:
        # ✅ Si por alguna razón aún no hay ubicación, no creamos el ticket
        if not draft.get("habitacion") and not draft.get("ubicacion"):
            area_worker = state.get("area_worker", "HOUSEKEEPING")
            mensaje = get_texto_por_area(area_worker, "ubicacion_pregunta")
            state["state"] = REPORTANDO_HAB
            send_whatsapp(from_phone, "❌ Me falta la ubicación.\n\n" + mensaje)
            return

        crear_ticket_desde_draft(from_phone)
        return

    
    if raw in ['editar', 'cambiar', 'modificar', 'editar ubicacion', 'editar ubicación', 'editar habitacion', 'editar habitación']:
        # ✅ MODIFICADO: Mensaje adaptado
        area_worker = state.get("area_worker", "HOUSEKEEPING")
        mensaje = get_texto_por_area(area_worker, "ubicacion_pregunta")
        state["state"] = REPORTANDO_HAB
        send_whatsapp(from_phone, mensaje)
        return
    
    if raw in ['editar detalle', 'cambiar detalle']:
        state["state"] = REPORTANDO_DETALLE
        send_whatsapp(from_phone, texto_pedir_detalle())
        return
    
    if raw in ['cancelar', 'cancel', 'no']:
        reset_ticket_draft(from_phone)
        state["state"] = MENU
        send_whatsapp(from_phone, "❌ Reporte cancelado\n\n💡 Di 'M' para volver al menú")
        return
    
    if raw in ['m', 'menu', 'menú', 'volver']:
        reset_ticket_draft(from_phone)
        from .ui_simple import texto_menu_simple
        turno_activo = state.get("turno_activo", False)
        send_whatsapp(from_phone, texto_menu_simple(turno_activo))
        state["state"] = MENU
        return
    
    habitacion = draft.get("habitacion") or draft.get("ubicacion") or "?"
    detalle = draft.get("detalle") or "Sin detalle"
    prioridad = draft.get("prioridad") or "MEDIA"

    mensaje = texto_confirmar_reporte(habitacion, detalle, prioridad)
    send_whatsapp(from_phone, "❌ No entendí\n\n" + mensaje)



def crear_ticket_directo_DESPUES(from_phone: str, reporte: dict, area_worker: str = "HOUSEKEEPING") -> None:
    from gateway_app.services.tickets_db import crear_ticket, obtener_tickets_asignados_a
    from gateway_app.services.ticket_classifier import clasificar_ticket  # ← NUEVO

    try:
        # ── NUEVO: Clasificar con IA ───────────────────────────────
        clasificacion = clasificar_ticket(
            detalle=reporte["detalle"],
            ubicacion=reporte["ubicacion"],
            area_worker=area_worker,
        )
        # ──────────────────────────────────────────────────────────

        ticket = crear_ticket(
            habitacion=reporte["ubicacion"],
            detalle=reporte["detalle"],
            prioridad=clasificacion["prioridad"],          # ← ahora viene del clasificador
            creado_por=from_phone,
            origen="trabajador",
            canal_origen="WHATSAPP_BOT_HOUSEKEEPING",
            area=clasificacion["area"],                    # ← ahora viene del clasificador
            # ── NUEVO: pasar metadata de routing ──────────────────
            routing_source=clasificacion["routing_source"],
            routing_reason=clasificacion["routing_reason"],
            routing_confidence=clasificacion["routing_confidence"],
            routing_version=clasificacion["routing_source"],
        )

        if not ticket:
            send_whatsapp(from_phone, "❌ No pude crear el ticket en la base de datos.\n\n💡 Di 'M' para volver al menú")
            return

        ticket_id = ticket["id"]
        
        # ✅ MODIFICADO: Mensaje con ubicación formateada
        ubicacion_fmt = formatear_ubicacion_para_mensaje(reporte["ubicacion"], area_worker)
        prioridad_emoji = {"ALTA": "🔴", "MEDIA": "🟡", "BAJA": "🟢"}.get(reporte["prioridad"], "🟡")
        
        send_whatsapp(
            from_phone,
            f"✅ Reporte #{ticket_id} creado\n\n"
            f"{ubicacion_fmt}\n"
            f"{prioridad_emoji} Prioridad: {reporte['prioridad']}"
        )

        state = get_user_state(from_phone)
        state["state"] = MENU

    except Exception:
        logger.exception("Error creando ticket directo en DB")
        send_whatsapp(from_phone, "❌ Error creando el ticket. Intenta de nuevo.\n\n💡 Di 'M' para volver al menú")


def crear_ticket_desde_draft(from_phone: str) -> None:
    """
    Crea ticket desde el borrador y notifica al supervisor.
    ✅ MODIFICADO: Solo notifica a supervisores en horario laboral (7:30 AM - 11:30 PM)
    """
    from gateway_app.core.utils.horario import esta_en_horario_laboral, obtener_mensaje_fuera_horario
    
    state = get_user_state(from_phone)

    if state.get("state") != CONFIRMANDO_REPORTE:
        logger.warning(
            "HK_CREATE_FROM_DRAFT ignored (state=%s) from=%s",
            state.get("state"),
            from_phone,
        )
        return

    draft = state.get("ticket_draft") or {}
    logger.info("HK_CREATE_FROM_DRAFT from=%s draft=%s", from_phone, draft)

    # ✅ MODIFICADO: Verificar ubicacion O habitacion (compatibilidad)
    ubicacion = draft.get("ubicacion", draft.get("habitacion"))
    
    if not ubicacion or not draft.get("detalle"):
        logger.warning("HK_CREATE_FROM_DRAFT missing_fields from=%s draft=%s", from_phone, draft)
        send_whatsapp(from_phone, "❌ Error: Falta información del reporte\n\n💡 Di 'M' para volver al menú")
        reset_ticket_draft(from_phone)
        state["state"] = MENU
        return

    try:
        # ✅ NUEVO: Obtener área del worker
        area_worker = state.get("area_worker", "HOUSEKEEPING")
        
        # ── NUEVO: Clasificar con IA ───────────────────────────────
        from gateway_app.services.ticket_classifier import clasificar_ticket
        clasificacion = clasificar_ticket(
            detalle=draft["detalle"],
            ubicacion=ubicacion,
            area_worker=area_worker,
        )
        # ──────────────────────────────────────────────────────────

        ticket = tickets_db.crear_ticket(
            habitacion=ubicacion,
            detalle=draft["detalle"],
            prioridad=clasificacion["prioridad"],         # ← CAMBIADO
            creado_por=from_phone,
            origen="trabajador",
            canal_origen="WHATSAPP_BOT_HOUSEKEEPING",
            area=clasificacion["area"],                   # ← CAMBIADO
            property_id=tenant.property_id if tenant else None,
            routing_source=clasificacion["routing_source"],    # ← NUEVO
            routing_reason=clasificacion["routing_reason"],    # ← NUEVO
            routing_confidence=clasificacion["routing_confidence"],  # ← NUEVO
            routing_version=clasificacion["routing_source"],   # ← NUEVO
        )

# Y actualizar el mensaje de confirmación para usar clasificacion["prioridad"]
#en lugar de draft["prioridad"] si los vas a mostrar al trabajador:

        prioridad_emoji = {"ALTA": "🔴", "MEDIA": "🟡", "BAJA": "🟢", "URGENTE": "🚨"}.get(
            clasificacion["prioridad"], "🟡"
        )

        logger.info(
            "HK_CREATE_FROM_DRAFT db_return from=%s ticket_is_none=%s ticket=%s",
            from_phone,
            ticket is None,
            ticket,
        )

        if not ticket:
            send_whatsapp(from_phone, "❌ No pude crear el ticket en la base de datos.\n\n💡 Di 'M' para volver al menú")
            reset_ticket_draft(from_phone)
            state["state"] = MENU
            return

        ticket_id = ticket["id"]
        logger.info("HK_CREATE_FROM_DRAFT created_id=%s from=%s", ticket_id, from_phone)

        # ✅ MODIFICADO: Mensaje con ubicación formateada
        ubicacion_fmt = formatear_ubicacion_para_mensaje(ubicacion, area_worker)
        prioridad_emoji = {"ALTA": "🔴", "MEDIA": "🟡", "BAJA": "🟢"}.get(draft["prioridad"], "🟡")
        
        send_whatsapp(
            from_phone,
            f"✅ Ticket #{ticket_id} creado\n\n"
            f"{ubicacion_fmt}\n"
            f"📝 {draft['detalle']}\n"
            f"{prioridad_emoji} Prioridad: {draft['prioridad']}"
        )

        from gateway_app.services.workers_db import obtener_supervisores_por_area as _get_sups_create
        _sups_create = _get_sups_create(clasificacion["area"], property_id=tenant.property_id if tenant else "")
        supervisor_phones = [s["telefono"] for s in _sups_create if s.get("telefono")]

        # ====================================================================
        # ✅ NUEVO: CHECK DE HORARIO LABORAL
        # ====================================================================
        if supervisor_phones:
            en_horario = esta_en_horario_laboral()

            if en_horario:
                # ✅ EN HORARIO: Notificar supervisores normalmente
                logger.info(f"✅ Ticket #{ticket_id} creado EN horario laboral - Notificando {len(supervisor_phones)} supervisores")

                from gateway_app.services.whatsapp_client import send_whatsapp_text
                from gateway_app.services.workers_db import buscar_worker_por_telefono

                worker = buscar_worker_por_telefono(from_phone, property_id=tenant.property_id if tenant else "")
                worker_nombre = worker.get("nombre_completo") if worker else "Trabajador"
                
                for supervisor_phone in supervisor_phones:
                    send_whatsapp_text(
                        to=supervisor_phone,
                        body=f"📋 Nuevo reporte de {worker_nombre}\n\n"
                             f"#{ticket_id} · {ubicacion}\n"
                             f"{draft['detalle']}\n"
                             f"{prioridad_emoji} Prioridad: {draft['prioridad']}\n\n"
                             f"💡 Di 'asignar {ticket_id} a [nombre]' para derivar"
                    )
                    logger.info(f"✅ Notificación enviada a supervisor {supervisor_phone}")
            else:
                # 🌙 FUERA DE HORARIO: NO notificar supervisores
                logger.warning(f"🌙 Ticket #{ticket_id} creado FUERA de horario laboral - NO se notifica a supervisores")
                
                # Informar al worker que será atendido mañana
                send_whatsapp(
                    from_phone,
                    f"\n🌙 Fuera de horario laboral\n"
                    f"⏰ Supervisión será notificada mañana a las 7:30 AM"
                )
        # ====================================================================

        reset_ticket_draft(from_phone)
        state["state"] = MENU

    except Exception as e:
        logger.exception("HK_CREATE_FROM_DRAFT exception from=%s err=%s", from_phone, e)
        send_whatsapp(from_phone, "❌ Error creando el ticket. Intenta de nuevo.\n\n💡 Di 'M' para volver al menú")
        reset_ticket_draft(from_phone)
        state["state"] = MENU


from gateway_app.services.workers_db import activar_turno_por_telefono, desactivar_turno_por_telefono
def iniciar_turno(from_phone: str, tenant=None) -> None:
    """
    Inicia el turno del trabajador.
    """
    from datetime import datetime
    state = get_user_state(from_phone)

    if state.get("turno_activo", False):
        send_whatsapp(from_phone, "⚠️ Tu turno ya está activo\n\n💡 Di 'M' para volver al menú")
        return

    ok = activar_turno_por_telefono(from_phone, property_id=tenant.property_id if tenant else "")
    if not ok:
        send_whatsapp(from_phone, "❌ No pude activar tu turno en el sistema (usuario no encontrado).")
        return
    
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


def terminar_turno(from_phone: str, tenant=None) -> None:
    """
    ✅ CORREGIDO: Manejo correcto de timezone para calcular duración.
    """
    from datetime import datetime
    from zoneinfo import ZoneInfo
    
    TIMEZONE = ZoneInfo("America/Santiago")
    
    state = get_user_state(from_phone)
    
    if not state.get("turno_activo", False):
        send_whatsapp(from_phone, "⚠️ No tienes turno activo\n\n💡 Di 'M' para volver al menú")
        return
    
    desactivar_turno_por_telefono(from_phone, property_id=tenant.property_id if tenant else "")

    # Verificar si tiene tickets activos
    tickets = obtener_tickets_asignados_a(from_phone)
    tickets_activos = [t for t in tickets if t.get('estado') == 'EN_CURSO']
    
    if len(tickets_activos) > 0:
        from gateway_app.services.tickets_db import actualizar_estado_ticket
        
        for ticket in tickets_activos:
            actualizar_estado_ticket(ticket['id'], "PAUSADO")
        
        send_whatsapp(
            from_phone,
            f"⏸️ {len(tickets_activos)} tarea(s) pausada(s) automáticamente"
        )
    
    # Calcular duración - ✅ FIX: Manejar timezone correctamente
    inicio = state.get("turno_inicio")
    duracion_texto = "No disponible"
    
    if inicio:
        try:
            inicio_dt = datetime.fromisoformat(inicio)
            
            # ✅ FIX: Asegurar que ambos tengan el mismo tipo de timezone
            if inicio_dt.tzinfo is not None:
                # Si inicio tiene timezone, usar now() con timezone
                fin_dt = datetime.now(TIMEZONE)
            else:
                # Si inicio NO tiene timezone, usar now() sin timezone
                fin_dt = datetime.now()
            
            duracion = fin_dt - inicio_dt
            horas = int(duracion.total_seconds() / 3600)
            minutos = int((duracion.total_seconds() % 3600) / 60)
            duracion_texto = f"{horas}h {minutos}min"
        except Exception as e:
            logger.warning(f"Error calculando duración de turno: {e}")
            duracion_texto = "No disponible"
    
    # Terminar turno
    state["turno_activo"] = False
    state["turno_fin"] = datetime.now(TIMEZONE).isoformat()
    
    # ✅ Limpiar flags de recordatorio para el próximo día
    state.pop("respondio_recordatorio_hoy", None)
    state.pop("turno_auto_activado", None)
    
    send_whatsapp(
        from_phone,
        f"🔴 Turno terminado\n\n"
        f"⏱️ Duración: {duracion_texto}\n"
        f"¡Buen trabajo! 👏"
    )
    state["state"] = "MENU"
