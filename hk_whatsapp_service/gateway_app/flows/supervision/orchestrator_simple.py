"""
Orquestador SIMPLE para supervisión - Sin menú, solo comandos.
"""
import logging

from .ticket_assignment import calcular_score_worker
from gateway_app.services.workers_db import buscar_worker_por_nombre, obtener_todos_workers
from gateway_app.services.tickets_db import obtener_tickets_asignados_a, obtener_ticket_por_id, asignar_ticket
from .ticket_assignment import formatear_ubicacion_con_emoji
from .state import get_supervisor_state, persist_supervisor_state
from gateway_app.services.whatsapp_client import send_whatsapp_text
from gateway_app.services.tickets_db import obtener_pendientes

from gateway_app.core.utils.message_constants import (
        msg_sup_confirmacion, msg_sup_dialogo,
       msg_worker_nueva_tarea, msg_worker_tarea_reasignada_saliente,
       msg_worker_tarea_finalizada_sup,
       emoji_prioridad, ubicacion_con_emoji, ubicacion_de_ticket,
       calcular_minutos, formato_tiempo,
   )

from gateway_app.flows.supervision.tiempo_utils import (
    formatear_lista_tickets_con_tiempo,
    formatear_workers_para_asignacion,
    construir_mensaje_equipo,
    calcular_tiempo_transcurrido
)

from gateway_app.services import tickets_db
from .ubicacion_helpers import (
    get_area_emoji,
    get_area_short
)

logger = logging.getLogger(__name__)

from datetime import date, datetime
from .state import get_supervisor_state
from .ui_simple import (
    texto_saludo_supervisor,
    texto_tickets_pendientes_simple,
    texto_urgentes
)
from .outgoing import send_whatsapp

def calcular_tiempo_desde(fecha_str: str) -> str:
    """
    Calcula tiempo transcurrido desde una fecha.
    
    Args:
        fecha_str: Fecha en formato ISO
    
    Returns:
        Texto amigable: "5 min", "2 horas", "3 días"
    """
    if not fecha_str:
        return "?"
    
    try:
        from dateutil import parser
        from datetime import datetime
        
        fecha = parser.parse(str(fecha_str))
        ahora = datetime.now(fecha.tzinfo) if fecha.tzinfo else datetime.now()
        
        diff = ahora - fecha
        
        minutos = int(diff.total_seconds() / 60)
        horas = int(diff.total_seconds() / 3600)
        dias = diff.days
        
        if minutos < 60:
            return f"{minutos} min"
        elif horas < 24:
            return f"{horas} hora{'s' if horas != 1 else ''}"
        else:
            return f"{dias} día{'s' if dias != 1 else ''}"
    except Exception:
        logger.warning(f"Error calculando tiempo desde {fecha_str}")
        return "?"

def notificar_worker_nueva_tarea(worker_phone: str, ticket_id: int, 
                                  ubicacion: str, detalle: str, prioridad: str) -> None:
    """
    Envía notificación de nueva tarea al worker + reenvía media asociada si existe.
    """
    from gateway_app.services.whatsapp_client import (
        send_whatsapp_text, send_whatsapp_image, send_whatsapp_video
    )
    from gateway_app.services.tickets_db import obtener_media_de_ticket

    # 1) Mensaje de texto con la tarea
    send_whatsapp_text(
        to=worker_phone,
        body=msg_worker_nueva_tarea(ticket_id, ubicacion, detalle, prioridad),
    )

    # 2) Reenviar media asociada (si existe)
    try:
        medias = obtener_media_de_ticket(ticket_id)
        for media in medias:
            storage_url = media.get("storage_url")
            media_type = media.get("media_type", "image")
            
            if not storage_url:
                continue
            
            caption = f"📎 Foto de tarea #{ticket_id}"
            
            if media_type == "video":
                send_whatsapp_video(
                    to=worker_phone,
                    video_url=storage_url,
                    caption=caption,
                )
            else:
                send_whatsapp_image(
                    to=worker_phone,
                    image_url=storage_url,
                    caption=caption,
                )
            logger.info(f"📤 Media reenviada a worker {worker_phone} | Ticket #{ticket_id} | {media_type}")
    except Exception as e:
        logger.error(f"⚠️ Error reenviando media de ticket #{ticket_id} a {worker_phone}: {e}")

def infer_area_from_ubicacion(ubicacion: str) -> str:
    if not ubicacion:
        return "HOUSEKEEPING"
    u = str(ubicacion).strip()
    # Habitación si es número puro
    if u.isdigit():
        return "HOUSEKEEPING"
    # Si no es número puro -> área común
    return "AREAS_COMUNES"

def handle_supervisor_message_simple(from_phone: str, text: str) -> None:
    state = get_supervisor_state(from_phone)

    # ═══════════════════════════════════════════════════════════════
    # ✅ NUEVO: Verificar si hay media pendiente ANTES de todo
    # ═══════════════════════════════════════════════════════════════
    if state.get("media_pendiente") or state.get("media_para_ticket"):
        from gateway_app.flows.housekeeping.media_handler import (
            handle_media_context_response,
            handle_media_detail_response
        )
        
        # Primero verificar media_para_ticket (esperando descripción)
        if state.get("media_para_ticket"):
            if handle_media_detail_response(from_phone, text):
                return
        
        # Luego verificar media_pendiente (esperando ubicación)
        if state.get("media_pendiente"):
            if handle_media_context_response(from_phone, text):
                return
    # ═══════════════════════════════════════════════════════════════

    try:
        raw = (text or "").strip().lower()
        logger.info(f"👔 SUP | {from_phone} | Comando: '{raw[:30]}...'")
        
        # 1) Comando: Saludo (siempre responde)
        if raw in ['hola', 'hi', 'hello', 'buenas', 'buenos dias', 'buenas tardes']:
            # ✅ LIMPIAR ESTADO
            state["esperando_asignacion"] = False
            state["ticket_seleccionado"] = None
            state["seleccion_mucamas"] = None

            send_whatsapp(from_phone, texto_saludo_supervisor())
            return
        # ==========================================================
        # 2) CONFIRMACIÓN PENDIENTE (SI/NO)
        # Debe ir ANTES de esperando_asignacion y ANTES de maybe_handle_audio_command_simple
        # ==========================================================
        conf = state.get("confirmacion_pendiente")
        if conf:
            # Normalizar input para comparar
            raw_conf = (text or "").strip().lower()
            raw_conf_norm = (
                raw_conf.replace("á", "a")
                        .replace("é", "e")
                        .replace("í", "i")
                        .replace("ó", "o")
                        .replace("ú", "u")
            )

            YES = {"si", "sí", "yes", "ok", "confirmar", "dale"}
            NO  = {"no", "cancelar", "cancel", "rechazar"}

            # Caso 1: el usuario respondió afirmativo
            if raw_conf_norm in {w.replace("í", "i") for w in YES} or raw_conf in YES:
                ticket_id = conf.get("ticket_id")
                worker = conf.get("worker") or {}
                worker_phone = worker.get("telefono")
                worker_nombre = worker.get("nombre_completo") or worker.get("username") or "Trabajador"

                # ✅ IMPORTS EXPLÍCITOS (evita UnboundLocalError/NameError)
                from gateway_app.services.tickets_db import asignar_ticket, obtener_ticket_por_id

                if asignar_ticket(ticket_id, worker_phone, worker_nombre):
                    ticket = (obtener_ticket_por_id(ticket_id) or {})

                    # Tomar datos reales del ticket (con fallback al conf)
                    detalle = (
                        ticket.get("detalle")
                        or ticket.get("descripcion")
                        or conf.get("detalle")
                        or "Tarea asignada"
                    )

                    prioridad = str(ticket.get("prioridad") or conf.get("prioridad") or "MEDIA").upper()
                    ubicacion = (
                        ticket.get("ubicacion") or ticket.get("habitacion")
                        or conf.get("ubicacion") or conf.get("habitacion") or "?"
                    )
                    worker_area = (worker.get("area") or "")

                    # 1) Confirmación al supervisor
                    send_whatsapp(
                        from_phone,
                        msg_sup_confirmacion(
                            ticket_id, "asignada", ubicacion, detalle,
                            prioridad, worker_nombre, worker_area,
                        )
                    )

                    # 2) Notificación al worker
                    notificar_worker_nueva_tarea(worker_phone, ticket_id, ubicacion, detalle, prioridad)

                    # Limpiar estado de confirmación
                    state.pop("confirmacion_pendiente", None)
                    persist_supervisor_state(from_phone, state)
                    return  

                # error asignando
                send_whatsapp(from_phone, "❌ Error asignando. Intenta de nuevo.")
                state.pop("confirmacion_pendiente", None)
                persist_supervisor_state(from_phone, state)
                return  # <- IMPORTANTE

            # Caso 2: el usuario respondió negativo / cancelar
            if raw_conf_norm in NO:
                send_whatsapp(from_phone, "✅ OK. No asigno por ahora (la tarea quedó creada).")
                state.pop("confirmacion_pendiente", None)
                persist_supervisor_state(from_phone, state)
                return  # <- IMPORTANTE

            # Caso 3: llegó cualquier otra cosa (no es confirmación)
            # -> cancelo la confirmación y dejo que siga el flujo normal
            state.pop("confirmacion_pendiente", None)
            persist_supervisor_state(from_phone, state)
            # NO return aquí: dejamos que el mensaje se procese como comando normal
        
        # ==================================================
        # 3) ESPERANDO ASIGNACIÓN
        # ==================================================
        if state.get("esperando_asignacion"):
            if handle_respuesta_asignacion(from_phone, text):
                return
        
        # ==================================================
        # 4) COMANDOS DE TEXTO DIRECTO
        # ⚠️ IMPORTANTE: ESTOS VAN **ANTES** DE maybe_handle_audio_command_simple
        # ==================================================
        
        raw_cmd = raw
        if raw_cmd.startswith("ver "):
            raw_cmd = raw_cmd[4:].strip()

        # 4) Crear nuevo ticket
        if raw_cmd in ["crear", "nuevo", "nueva", "nueva tarea", "crear tarea", "registrar"]:
            send_whatsapp(
                from_phone,
                "📝 Listo, espero tu reporte.\n\n"
                "Describe el problema con la ubicación:\n")
            return

        # 4.1) Pendientes
        if raw_cmd in ["pendientes", "pendiente", "ver", "lista"]:
            mostrar_pendientes_simple(from_phone)
            return
        
        # 4.2) Asignados ← ✅ AQUÍ
        if raw_cmd in ["asignados", "asignadas", "en proceso", "activos", "activas", "trabajando"]:
            mostrar_tickets_asignados_y_en_curso(from_phone)
            return
        
        # 4.3) Más urgente / siguiente
        if raw_cmd in ["siguiente", "next", "proximo", "urgente", "asignar urgente", "mas urgente", "más urgente"]:
            asignar_siguiente(from_phone)
            return
        
        # 4.4) Ver urgentes
        if raw_cmd in ["urgentes", "critico"]:
            mostrar_urgentes(from_phone)
            return
        
        # 4.5) Ver retrasados
        if raw_cmd in ["retrasados", "retrasado", "atrasados"]:
            mostrar_retrasados(from_phone)
            return
        
        # 4.6) Ver en curso
        if raw_cmd in ["en curso", "proceso"]:
            mostrar_en_proceso(from_phone)
            return
        
        # 4.7) BD commands
        if raw_cmd in ["bd pendientes", "db pendientes", "pendientes bd"]:
            mostrar_tickets_db(from_phone, "PENDIENTE")
            return
        
        if raw_cmd in ["bd asignados", "db asignados", "asignados bd"]:
            mostrar_tickets_db(from_phone, "ASIGNADO")
            return
        
        if raw_cmd in ["bd en curso", "db en curso", "en curso bd"]:
            mostrar_tickets_db(from_phone, "EN_CURSO")
            return
        
        # 4.8) Ver info de ticket
        if any(word in raw for word in ["ticket", "tarea", "cual es", "cuál es", "ver el", "info"]):
            import re
            match = re.search(r'\b(\d{3,4})\b', raw)
            if match:
                ticket_id = int(match.group(1))
                mostrar_info_ticket(from_phone, ticket_id)
                return
        
        # 4.9) "asignar" solo
        if raw in ["asignar", "derivar", "enviar"]:
            send_whatsapp(
                from_phone,
                "💡 Para asignar, di:\n"
                "• 'más urgente' - asigna la más importante\n"
                "• 'asignar [#] a [nombre]' - asigna específica\n"
                "• 'pendientes' - ve todas primero"
            )
            return
        
        # 4.10) Ver estado del equipo
        if raw_cmd in ['equipo', 'trabajadores', 'mucamas', 'team', 'staff', 'trabajadoras']:
            mensaje = construir_mensaje_equipo()
            send_whatsapp(from_phone, mensaje)
            return
        
        # 4.11) Cancelar - ✅ FIX: Limpiar TODOS los estados pendientes
        if raw in ["cancelar", "cancel", "salir", "atras", "atrás"]:
            # Verificar si hay algo que cancelar
            tiene_pendiente = (
                state.get("esperando_asignacion") or
                state.get("confirmacion_pendiente") or
                state.get("seleccion_worker_pendiente") or
                state.get("seleccion_mucamas") or
                state.get("ticket_seleccionado")
            )
            
            # Limpiar todos los estados de flujo
            state["esperando_asignacion"] = False
            state["ticket_seleccionado"] = None
            state.pop("confirmacion_pendiente", None)
            state.pop("seleccion_worker_pendiente", None)
            state.pop("seleccion_mucamas", None)
            persist_supervisor_state(from_phone, state)
            
            if tiene_pendiente:
                send_whatsapp(from_phone, "❌ Operación cancelada")
            else:
                send_whatsapp(from_phone, "✅ No hay nada que cancelar ahora")
            return
        
        # 4.12) Ayuda
        if raw_cmd in ['ayuda', 'help', 'comandos', 'menu', 'menú', '?']:
            send_whatsapp(from_phone, texto_saludo_supervisor())
            return
        
        # ==================================================
        # 5) COMANDOS DE AUDIO
        # ⚠️ ESTO VA **DESPUÉS** DE LOS COMANDOS DE TEXTO
        # ==================================================
        if maybe_handle_audio_command_simple(from_phone, text):
            return
        
        # ==================================================
        # 6) REASIGNAR (si no matcheó en audio_commands)
        # ==================================================
        if "reasignar" in raw or "cambiar" in raw:
            send_whatsapp(
                from_phone,
                "💡 Para reasignar, di:\n"
                "• 'reasignar [#] a [nombre]'\n"
                "• 'cambiar [#] a [nombre]'\n\n"
                "Ejemplo: 'reasignar 1503 a María'"
            )
            return
        
        # ==================================================
        # 7) NO ENTENDÍ
        # ==================================================
        send_whatsapp(
            from_phone,
            "🤔 No entendí.\n\n"
            "💡 Puedes decir:\n"
            "• 'pendientes' → tareas sin asignar\n"
            "• 'asignados' → tareas activas\n"
            "• 'urgentes' → prioridad alta\n"
            "• 'siguiente' → asignar la más urgente\n"
            "• 'asignar [#] a [nombre]'\n"
            "• 'finalizar [#]'"
        )
    except Exception as e:
        logger.exception(f"❌ Error en supervisor handler: {e}")
        send_whatsapp(from_phone, "❌ Error interno. Intenta de nuevo.")

def mostrar_opciones_workers(from_phone: str, workers: list, ticket_id: int) -> None:
    """
    ✅ MODIFICADO: Muestra workers con estado de turno.
    Prioriza los que tienen turno activo.
    """
    from gateway_app.services.tickets_db import obtener_ticket_por_id
    
    ticket = obtener_ticket_por_id(ticket_id)
    mensaje = formatear_workers_para_asignacion(workers, ticket)
    
    state = get_supervisor_state(from_phone)
    state["ticket_seleccionado"] = ticket_id
    state["esperando_asignacion"] = True
    
    send_whatsapp(from_phone, mensaje)

def handle_respuesta_asignacion(from_phone: str, text: str) -> bool:
    """
    Maneja la respuesta cuando está esperando asignación.
    
    Args:
        from_phone: Número del supervisor
        text: Respuesta (nombre, número, o cancelar)
    
    Returns:
        True si se manejó la asignación
    """

    from .ticket_assignment import calcular_score_worker, confirmar_asignacion
    
    state = get_supervisor_state(from_phone)
    ticket_id = state.get("ticket_seleccionado")
    
    if not ticket_id:
        # No hay ticket seleccionado, cancelar
        state["esperando_asignacion"] = False
        return False
    
    raw = text.strip().lower()

    # ✅ NUEVO: Si detecta ubicación (habitación o área), no es nombre de worker
    from .audio_commands import extract_habitacion, extract_area_comun
    
    habitacion = extract_habitacion(text)
    area = extract_area_comun(text)
    
    if habitacion or area:
        # Es un nuevo comando de crear ticket, no una asignación
        logger.info(f"🔄 SUP | Cancelando asignación - detectado nuevo ticket")
        state["esperando_asignacion"] = False
        state["ticket_seleccionado"] = None
        return False  # Procesar como comando normal
    
    # NUEVO: Permitir cancelar
    if raw in ["cancelar", "cancel", "salir", "atras", "atrás", "volver"]:
        state["esperando_asignacion"] = False
        state["ticket_seleccionado"] = None
        send_whatsapp(from_phone, "❌ Asignación cancelada")
        return True
    
    # ✅ NUEVO: Detectar comandos que indican nueva tarea (no asignación)
    comandos_nuevos = [
    # Ver tickets
    "pendientes", "pendiente", "ver", "lista",
    "asignados", "asignadas", "en proceso", "activos", "activas", "trabajando",
    "urgentes", "urgente", "critico",
    "retrasados", "retrasado", "atrasados",
    "en curso", "proceso",
    # Ver equipo
    "equipo", "team", "trabajadores", "personal", "staff", "mucamas", "quienes",
    # Ayuda/navegación
    "help", "ayuda", "comandos", "menu", "menú", "?",
    "hola", "hi", "hello", "buenas", "buenos dias", "buenas tardes",
    # Otros
    "siguiente", "next", "proximo", "mas urgente", "más urgente",
    # Crear
    "crear", "nuevo", "nueva", "nueva tarea", "crear tarea", "registrar",
]
    
    # ✅ NUEVO: Detectar intents de crear ticket
    tiene_ubicacion = False
    from .audio_commands import extract_habitacion, extract_area_comun
    
    if extract_habitacion(text) or extract_area_comun(text):
        tiene_ubicacion = True
    
    # ✅ FIX: Normalizar prefijo "ver " para que "ver asignados" → "asignados"
    raw_check = raw
    if raw_check.startswith("ver "):
        raw_check = raw_check[4:].strip()

    # Si es comando nuevo o tiene ubicación, salir del flujo de asignación
    if raw in comandos_nuevos or raw_check in comandos_nuevos or tiene_ubicacion:
        state["esperando_asignacion"] = False
        state["ticket_seleccionado"] = None
        state["seleccion_mucamas"] = None
        persist_supervisor_state(from_phone, state)
        return False  # ✅ Dejar que se procese como comando normal
    
    worker = None
    
    # Opción 1: Respuesta por número (1, 2, 3, 4, 5)
    if raw.isdigit():
        index = int(raw) - 1
        
        from gateway_app.services.workers_db import obtener_todos_workers
        from gateway_app.services.tickets_db import obtener_ticket_por_id
        
        # ✅ OBTENER TICKET para scoring
        ticket = obtener_ticket_por_id(ticket_id)
        
        workers = obtener_todos_workers()
        
        # ✅ MODIFICADO: Incluir TODOS los workers, no solo con turno activo
        # Separar por turno activo para ordenar (activos primero)
        workers_activos = [w for w in workers if w.get("turno_activo", False)]
        workers_sin_turno = [w for w in workers if not w.get("turno_activo", False)]

        # Calcular scores para ambos grupos
        workers_con_score = []
        for w in workers_activos:
            score = calcular_score_worker(w, ticket)
            workers_con_score.append({**w, "score": score})
        
        for w in workers_sin_turno:
            score = calcular_score_worker(w, ticket) - 1000  # Penalizar sin turno
            workers_con_score.append({**w, "score": score})
        
        workers_con_score.sort(key=lambda w: w["score"], reverse=True)
        
        # ✅ Tomar top 6 (para que coincida con lo mostrado)
        top_workers = workers_con_score[:6]
        
        if 0 <= index < len(top_workers):
            worker = top_workers[index]
        else:
            send_whatsapp(
                from_phone,
                f"❌ Número inválido (1-{len(top_workers)})\n\n"
                "💡 Di el nombre o número\n"
                "O escribe 'cancelar'"
            )
            return True
    
    # Opción 2: Respuesta por nombre
    else:
        import re
        
        # ✅ LIMPIAR: Remover preposiciones y artículos
        nombre_limpio = text.strip()
        nombre_limpio = re.sub(r'^(a|para|de|el|la|los|las)\s+', '', nombre_limpio, flags=re.IGNORECASE)
        nombre_limpio = nombre_limpio.strip()
        
        # Buscar
        from gateway_app.services.workers_db import buscar_workers_por_nombre
        candidatos = buscar_workers_por_nombre(nombre_limpio)
        
        if len(candidatos) == 1:
            worker = candidatos[0]
        elif len(candidatos) > 1:
            # Múltiples: mostrar con área
            state["seleccion_mucamas"] = {
                "tipo": "asignar",
                "ticket_id": ticket_id,
                "candidatas": candidatos
            }
            
            lineas = ["👥 Encontré varias personas:\n"]
            for i, w in enumerate(candidatos, 1):
                area = (w.get("area") or "HOUSEKEEPING").upper()
                area_emoji = {
                    "HOUSEKEEPING": "🏠", "HK": "🏠",
                    "AREAS_COMUNES": "📍", "AC": "📍",
                    "MANTENIMIENTO": "🔧", "MT": "🔧"
                }.get(area, "👤")
                
                lineas.append(f"{i}. {area_emoji} {w.get('nombre_completo')}")
            
            lineas.append("\n💡 Di el número o apellido")
            send_whatsapp(from_phone, "\n".join(lineas))
            return True
        else:
            # No encontrado
            send_whatsapp(
                from_phone,
                f"❌ No encontré a '{nombre_limpio}'\n\n"
                "💡 Di el nombre o número (1-5)\n"
                "O escribe 'cancelar'"
            )
            return True
    
    # Verificar que se encontró
    if worker:
        # ✅ ASIGNAR EN BD REAL
        from gateway_app.services.tickets_db import asignar_ticket
        
        worker_phone = worker.get("telefono")
        worker_nombre = worker.get("nombre_completo", worker.get("nombre"))
        
        if asignar_ticket(ticket_id, worker_phone, worker_nombre):
            # Notificar al supervisor
            confirmar_asignacion(from_phone, ticket_id, worker)
            
            # ✅ NOTIFICAR AL TRABAJADOR
            from gateway_app.services.whatsapp_client import send_whatsapp_text

            ticket_data = obtener_ticket_por_id(ticket_id) or {}

            detalle = (
                ticket_data.get("detalle")
                or ticket_data.get("descripcion")
                or "Tarea asignada"
            )

            ubicacion = (
                ticket_data.get("ubicacion")
                or ticket_data.get("habitacion")
                or "?"
            )

            prioridad = str(ticket_data.get("prioridad") or "MEDIA").upper()

            # ✅ FIX A3: Usar template unificado en vez de formato inline
            notificar_worker_nueva_tarea(worker_phone, ticket_id, ubicacion, detalle, prioridad)
            
            state["esperando_asignacion"] = False
            state["ticket_seleccionado"] = None
            return True
        else:
            send_whatsapp(from_phone, "❌ Error asignando. Intenta de nuevo.")
            return True
    else:
        send_whatsapp(
            from_phone,
            f"❌ No encontré a '{text}'\n\n"
            "💡 Di el nombre o número (1, 2, 3)\n"
            "O escribe 'cancelar' para abortar"
        )
        return True


def mostrar_pendientes_simple(from_phone: str) -> None:
    """Muestra tareas pendientes ordenadas por prioridad con tiempo."""
    from gateway_app.services.tickets_db import obtener_pendientes
    from gateway_app.core.utils.message_constants import (
        formatear_lista_tickets, PRIORIDAD_ORDER,
    )

    tickets = obtener_pendientes()

    if not tickets:
        send_whatsapp(from_phone, "✅ No hay tareas pendientes")
        return

    tickets.sort(key=lambda t: PRIORIDAD_ORDER.get(
        (t.get("prioridad") or "MEDIA").upper(), 1
    ))

    msg = formatear_lista_tickets(
        tickets,
        titulo="📋 Tareas Pendientes",
        hint="💡 Di 'asignar [#] a [nombre]' o 'siguiente'",
        mostrar_tiempo=True,
        mostrar_worker=False,
    )
    send_whatsapp(from_phone, msg)


def asignar_siguiente(from_phone: str) -> None:
    """Asigna el ticket de mayor prioridad."""
    from gateway_app.services.tickets_db import obtener_tickets_por_estado
    from gateway_app.services.workers_db import obtener_todos_workers
    from .ticket_assignment import calcular_score_worker
    from .ui_simple import texto_recomendaciones_simple
    
    tickets = obtener_pendientes()
    
    if not tickets:
        send_whatsapp(from_phone, "✅ No hay tickets pendientes")
        return
    
    # Ordenar por prioridad
    prioridad_order = {"ALTA": 0, "MEDIA": 1, "BAJA": 2}
    tickets_sorted = sorted(
        tickets,
        key=lambda t: (
            prioridad_order.get(t.get("prioridad", "MEDIA"), 1),
            -t.get("tiempo_sin_resolver_mins", 0)
        )
    )
    
    ticket = tickets_sorted[0]
    ticket_id = ticket["id"]
    
    # Guardar ticket seleccionado
    state = get_supervisor_state(from_phone)
    state["ticket_seleccionado"] = ticket_id
    
    # Mostrar ticket + recomendaciones
    prioridad_emoji = {"ALTA": "🔴", "MEDIA": "🟡", "BAJA": "🟢"}.get(
        ticket.get("prioridad", "MEDIA"), "🟡"
    )
    
    # ✅ CORREGIDO: Extraer habitación
    hab = ticket.get('ubicacion') or ticket.get('habitacion', '?')
    
    # ✅ CORREGIDO: Calcular tiempo esperando
    created_at = ticket.get("created_at")
    if created_at:
        try:
            from dateutil import parser
            if isinstance(created_at, str):
                created_at = parser.parse(created_at)
            tiempo_mins = int((datetime.now(created_at.tzinfo) - created_at).total_seconds() / 60)
        except Exception:
            tiempo_mins = 0
    else:
        tiempo_mins = 0
    
    send_whatsapp(
        from_phone,
        f"📋 Siguiente ticket:\n\n"
        f"{prioridad_emoji} #{ticket_id} · Hab. {hab}\n"
        f"{ticket['detalle']}\n"
        f"{tiempo_mins} min esperando"  # ✅ Usa variable calculada
    )
    
    # Mostrar recomendaciones compactas (inline, no función externa)
    workers = obtener_todos_workers()
    mostrar_opciones_workers(from_phone, workers, ticket_id)
    state["esperando_asignacion"] = True

def mostrar_urgentes(from_phone: str) -> None:
    """Muestra tareas urgentes: pendientes >5 min y en curso >10 min."""
    from gateway_app.services.tickets_db import obtener_tickets_por_estado
    from gateway_app.core.utils.message_constants import calcular_minutos

    pendientes = obtener_tickets_por_estado("PENDIENTE")
    pendientes_urgentes = [
        t for t in pendientes
        if calcular_minutos(t.get("created_at")) > 5
    ]

    en_curso = obtener_tickets_por_estado("EN_CURSO")
    retrasados = [
        t for t in en_curso
        if calcular_minutos(t.get("started_at")) > 10
    ]

    mensaje = texto_urgentes(pendientes_urgentes, retrasados)
    send_whatsapp(from_phone, mensaje)


def mostrar_en_proceso(from_phone: str) -> None:
    """Muestra tareas en proceso con tiempo y worker asignado."""
    from gateway_app.services.tickets_db import obtener_tickets_por_estado
    from gateway_app.core.utils.message_constants import formatear_lista_tickets

    tickets = obtener_tickets_por_estado("EN_CURSO")

    if not tickets:
        send_whatsapp(from_phone, "✅ No hay tareas en proceso")
        return

    msg = formatear_lista_tickets(
        tickets,
        titulo="🔄 Tareas en Proceso",
        hint="💡 Di 'reasignar [#] a [nombre]'",
        mostrar_tiempo=True,
        mostrar_worker=True,
        campo_fecha="started_at",
    )
    send_whatsapp(from_phone, msg)


def mostrar_retrasados(from_phone: str) -> None:
    """Muestra tareas en curso retrasadas (>10 min)."""
    from gateway_app.services.tickets_db import obtener_tickets_por_estado
    from gateway_app.core.utils.message_constants import (
        calcular_minutos, formatear_lista_tickets,
    )

    tickets = obtener_tickets_por_estado("EN_CURSO")
    retrasados = [
        t for t in tickets
        if calcular_minutos(t.get("started_at")) > 10
    ]

    if not retrasados:
        send_whatsapp(from_phone, "✅ No hay tareas retrasadas")
        return

    msg = formatear_lista_tickets(
        retrasados,
        titulo="⏰ Tareas Retrasadas",
        hint="💡 Di 'reasignar [#] a [nombre]'",
        mostrar_tiempo=True,
        mostrar_worker=True,
        campo_fecha="started_at",
    )
    send_whatsapp(from_phone, msg)


def mostrar_info_ticket(from_phone: str, ticket_id: int) -> None:
    """Muestra detalle completo de una tarea."""
    from gateway_app.services.tickets_db import obtener_ticket_por_id
    from gateway_app.core.utils.message_constants import (
        emoji_prioridad, emoji_estado, label_estado,
        ubicacion_de_ticket, calcular_minutos, formato_tiempo,
        nombre_worker_de_ticket,
    )

    ticket = obtener_ticket_por_id(ticket_id)

    if not ticket:
        send_whatsapp(from_phone, f"❌ No encontré la tarea #{ticket_id}")
        return

    estado = (ticket.get("estado") or "PENDIENTE").upper()
    prioridad = (ticket.get("prioridad") or "MEDIA").upper()
    ubicacion = ubicacion_de_ticket(ticket)
    detalle = ticket.get("detalle") or ticket.get("descripcion") or "Sin detalle"

    lineas = [
        f"{emoji_estado(estado)} Tarea #{ticket_id}\n",
        f"📍 Ubicación: {ubicacion}",
        f"📝 Detalle: {detalle}",
        f"{emoji_prioridad(prioridad)} Prioridad: {prioridad}",
        f"📊 Estado: {label_estado(estado)}",
    ]

    if estado in ("EN_CURSO", "ASIGNADO"):
        worker = nombre_worker_de_ticket(ticket)
        lineas.append(f"👤 Trabajador: {worker}")
        fecha = ticket.get("started_at") or ticket.get("created_at")
        mins = calcular_minutos(fecha)
        if mins > 0:
            lineas.append(f"⏱️ Tiempo: {formato_tiempo(mins)}")

    elif estado == "PENDIENTE":
        mins = calcular_minutos(ticket.get("created_at"))
        if mins > 0:
            lineas.append(f"⏱️ Esperando: {formato_tiempo(mins)}")

    elif estado in ("RESUELTO", "COMPLETADO"):
        worker = nombre_worker_de_ticket(ticket)
        if worker != "Sin asignar":
            lineas.append(f"👤 Trabajador: {worker}")

    send_whatsapp(from_phone, "\n".join(lineas))

def mostrar_tickets_db(from_phone: str, estado: str = "PENDIENTE") -> None:
    """Muestra tareas desde BD por estado (comando bd/db)."""
    from gateway_app.services.tickets_db import obtener_tickets_por_estado
    from gateway_app.core.utils.message_constants import (
        emoji_estado, formatear_lista_tickets,
    )

    tickets = obtener_tickets_por_estado(estado)

    if not tickets:
        send_whatsapp(from_phone, f"✅ No hay tareas en estado '{estado}'")
        return

    estado_label = estado.lower().replace("_", " ")
    msg = formatear_lista_tickets(
        tickets,
        titulo=f"{emoji_estado(estado)} Tareas {estado_label}",
        mostrar_tiempo=True,
        mostrar_worker=(estado != "PENDIENTE"),
    )
    send_whatsapp(from_phone, msg)

def mostrar_tickets_asignados_y_en_curso(from_phone: str) -> None:
    """Muestra tareas activas: en curso + asignadas, formato unificado."""
    from gateway_app.services.tickets_db import obtener_tickets_asignados_y_en_curso
    from gateway_app.core.utils.message_constants import formatear_linea_ticket

    tickets = obtener_tickets_asignados_y_en_curso()

    if not tickets:
        send_whatsapp(from_phone, "✅ No hay tareas asignadas ni en proceso")
        return

    en_curso = [t for t in tickets if t.get("estado") == "EN_CURSO"]
    asignados = [t for t in tickets if t.get("estado") == "ASIGNADO"]

    lineas = [f"📋 Tareas Activas ({len(tickets)})\n"]

    if en_curso:
        lineas.append(f"🔄 EN CURSO ({len(en_curso)}):")
        for t in en_curso[:5]:
            lineas.append(formatear_linea_ticket(
                t, mostrar_tiempo=True, mostrar_worker=True,
                campo_fecha="started_at",
            ))
        if len(en_curso) > 5:
            lineas.append(f"   ... y {len(en_curso) - 5} más")
        lineas.append("")

    if asignados:
        lineas.append(f"📋 ASIGNADAS ({len(asignados)}):")
        for t in asignados[:5]:
            lineas.append(formatear_linea_ticket(
                t, mostrar_tiempo=False, mostrar_worker=True,
            ))
        if len(asignados) > 5:
            lineas.append(f"   ... y {len(asignados) - 5} más")

    lineas.append("\n💡 Di 'finalizar [#]' o 'reasignar [#] a [nombre]'")

    send_whatsapp(from_phone, "\n".join(lineas))
    logger.info(f"📋 Mostrados {len(tickets)} tareas activas a supervisor")

def finalizar_ticket_supervisor(from_phone: str, ticket_id: int) -> None:
    """
    Finaliza un ticket desde supervisión.
    
    Args:
        from_phone: Teléfono del supervisor
        ticket_id: ID del ticket a finalizar
    
    Flujo:
    1. Obtener ticket de BD
    2. Validar que existe y estado
    3. Actualizar a COMPLETADO
    4. Notificar supervisor y worker
    """
    from gateway_app.services.tickets_db import (
        obtener_ticket_por_id,
        actualizar_estado_ticket
    )
    from gateway_app.services.whatsapp_client import send_whatsapp_text
    from datetime import datetime
    
    logger.info(f"👔 SUP | Finalizando ticket #{ticket_id} desde supervisión")
    
    # 1. Obtener ticket
    ticket = obtener_ticket_por_id(ticket_id)
    
    if not ticket:
        send_whatsapp(
            from_phone,
            f"❌ No encontré la tarea #{ticket_id}\n\n"
            f"💡 Usa 'pendientes' para ver tickets disponibles"
        )
        logger.warning(f"👔 SUP | Ticket #{ticket_id} no encontrado")
        return
    
    # 2. Verificar estado
    estado_actual = ticket.get("estado")
    
    if estado_actual == "COMPLETADO":
        fecha_completado = ticket.get("fecha_completado")
        tiempo_desde = calcular_tiempo_desde(fecha_completado)
        
        send_whatsapp(
            from_phone,
            f"⚠️ La tarea #{ticket_id} ya está completada\n\n"
            f"✅ Finalizado hace {tiempo_desde}"
        )
        logger.info(f"👔 SUP | Ticket #{ticket_id} ya completado")
        return
    
    if estado_actual == "CANCELADO":
        send_whatsapp(
            from_phone,
            f"⚠️ La tarea #{ticket_id} está cancelada\n\n"
            f"💡 No se puede finalizar una tarea cancelada"
        )
        logger.info(f"👔 SUP | Ticket #{ticket_id} cancelado, no se puede finalizar")
        return
    
# 3. Obtener datos del ticket
    ubicacion = ticket.get("ubicacion") or ticket.get("habitacion", "?")
    detalle = ticket.get("detalle", "Sin detalle")
    prioridad = ticket.get("prioridad", "MEDIA")

    # ✅ FIX C5: Extraer worker desde huesped_whatsapp (formato "phone|nombre")
    huesped_wa = ticket.get("huesped_whatsapp") or ""
    if "|" in huesped_wa:
        worker_phone_dest, worker_nombre = huesped_wa.split("|", 1)
    else:
        worker_phone_dest = None
        worker_nombre = ""

    # 4. Calcular duración
    duracion_min = calcular_minutos(ticket.get("created_at"))

    # 5. Actualizar en BD
    exito = actualizar_estado_ticket(ticket_id, "COMPLETADO")

    if not exito:
        send_whatsapp(
            from_phone,
            f"❌ Error al finalizar tarea #{ticket_id}\n\n"
            f"💡 Intenta de nuevo o contacta soporte"
        )
        logger.error(f"👔 SUP | Error finalizando tarea #{ticket_id}")
        return

    # 6. Confirmar al supervisor
    send_whatsapp(
        from_phone,
        msg_sup_confirmacion(
            ticket_id, "finalizada", ubicacion, detalle, prioridad,
            worker_nombre=worker_nombre or None,
            duracion_min=duracion_min,
        )
    )
    logger.info(f"✅ Tarea #{ticket_id} finalizada por supervisión")

    # 7. Notificar al worker si estaba asignado
    if worker_phone_dest:
        try:
            send_whatsapp_text(
                to=worker_phone_dest,
                body=msg_worker_tarea_finalizada_sup(ticket_id, ubicacion, detalle),
            )
            logger.info(f"✅ Worker {worker_phone_dest} notificado de finalización")
        except Exception as e:
            logger.error(f"Error notificando worker: {e}")

def maybe_handle_audio_command_simple(from_phone: str, text: str) -> bool:
    """
    Detecta y maneja comandos de audio de forma simple.
    
    Args:
        from_phone: Número de teléfono
        text: Texto transcrito
    
    Returns:
        True si se manejó
    """
    from .audio_commands import detect_audio_intent
    from .ticket_assignment import confirmar_asignacion
    # DESPUÉS
    from gateway_app.services.workers_db import (
    obtener_todos_workers,
    buscar_worker_por_nombre,
    buscar_workers_por_nombre
    )
    from .worker_search import (
        buscar_workers,
        formato_lista_workers,
        normalizar_nombre,
        manejar_seleccion_worker
    )
    from .ui_simple import texto_ticket_asignado_simple, texto_ticket_creado_simple
    
    # Detectar intención
    intent_data = detect_audio_intent(text)
    intent = intent_data.get("intent")
    state = get_supervisor_state(from_phone)

    # 🔍 DEBUG - Agregar estas 3 líneas
    logger.info(f"🎯 INTENT DETECTADO: {intent}")
    logger.info(f"📦 DATOS: {intent_data}")
    logger.info(f"📝 TEXTO ORIGINAL: {text}")
    
    # PRIMERO: Manejar selección pendiente (si hay confirmación esperando)
    if state.get("seleccion_mucamas"):
        seleccion_info = state["seleccion_mucamas"]
        candidatas = seleccion_info["candidatas"]
        ticket_id = seleccion_info["ticket_id"]
        
        mucama_seleccionada = manejar_seleccion_worker(text, candidatas)
        
        # Caso 1: Selección válida
        if mucama_seleccionada and mucama_seleccionada != "CANCEL":
            # Recuperar datos del ticket desde seleccion_info
            habitacion = seleccion_info.get("habitacion", "?")
            detalle = seleccion_info.get("detalle", "Tarea asignada")
            prioridad = seleccion_info.get("prioridad", "MEDIA")
            
            # Asignar y notificar con datos completos
            worker_phone = mucama_seleccionada.get("telefono")
            worker_nombre = mucama_seleccionada.get("nombre_completo") or mucama_seleccionada.get("username")
            
            from gateway_app.services.tickets_db import asignar_ticket
            if asignar_ticket(ticket_id, worker_phone, worker_nombre):
                ubicacion = seleccion_info.get("ubicacion") or seleccion_info.get("habitacion") or "?"
                ticket = obtener_ticket_por_id(ticket_id)
                detalle = (ticket.get("detalle") or "—").strip()

                send_whatsapp(
                    from_phone,
                    msg_sup_confirmacion(
                        ticket_id, "asignada", ubicacion, detalle, prioridad, worker_nombre,
                    )
                )

                notificar_worker_nueva_tarea(worker_phone, ticket_id, ubicacion, detalle, prioridad)

                # Notificar al worker original si es reasignación
                if seleccion_info.get("tipo") == "reasignar":
                    worker_original = seleccion_info.get("worker_original", {})
                    worker_original_phone = worker_original.get("phone")
                    if worker_original_phone:
                        send_whatsapp_text(
                            to=worker_original_phone,
                            body=msg_worker_tarea_reasignada_saliente(
                                ticket_id, ubicacion, worker_nombre,
                            ),
                        )
                        logger.info(f"✅ Notificación de reasignación enviada a {worker_original_phone}")

                state.pop("seleccion_mucamas", None)
                return True
            
        # Caso 1.5: Reasignar ticket existente
        if intent == "reasignar_ticket":
            ticket_id = intent_data["ticket_id"]
            worker_nombre = intent_data["worker"]
            # ✅ NO normalizar - buscar tal cual viene del intent
            
            # Obtener ticket para guardar worker original
            from gateway_app.services.tickets_db import obtener_ticket_por_id, asignar_ticket
            ticket = obtener_ticket_por_id(ticket_id)
            
            if not ticket:
                send_whatsapp(from_phone, f"❌ No encontré la tarea #{ticket_id}")
                return True
            
            # Guardar worker original
            huesped_whatsapp_original = ticket.get("huesped_whatsapp", "")
            if "|" in huesped_whatsapp_original:
                worker_original_phone, worker_original_name = huesped_whatsapp_original.split("|", 1)
            else:
                worker_original_phone = None
                worker_original_name = None
            
            # Buscar nuevo worker
            from gateway_app.services.workers_db import buscar_workers_por_nombre
            candidatas = buscar_workers_por_nombre(worker_nombre)
            
            if not candidatas:
                send_whatsapp(
                    from_phone,
                    f"❌ No encontré a '{worker_nombre}'\n\n"
                    "💡 Verifica el nombre"
                )
                return True
            
            if len(candidatas) == 1:
                # Un solo worker: reasignar directamente
                worker = candidatas[0]
                worker_phone = worker.get("telefono")
                worker_nombre_completo = worker.get("nombre_completo", worker.get("nombre"))
                
                if asignar_ticket(ticket_id, worker_phone, worker_nombre_completo):
                    ubicacion = ticket.get("ubicacion") or ticket.get("habitacion", "?")
                    detalle = ticket.get("detalle", "Sin detalle")
                    prioridad = ticket.get("prioridad", "MEDIA")

                    # 1. Notificar al worker ORIGINAL
                    if worker_original_phone:
                        from gateway_app.services.whatsapp_client import send_whatsapp_text
                        send_whatsapp_text(
                            worker_original_phone,
                            msg_worker_tarea_reasignada_saliente(
                                ticket_id, ubicacion, worker_nombre_completo,
                            ),
                        )
                        logger.info(f"✅ Notificación de reasignación enviada a {worker_original_phone}")

                    # 2. Confirmar al SUPERVISOR
                    send_whatsapp(
                        from_phone,
                        msg_sup_confirmacion(
                            ticket_id, "reasignada", ubicacion, detalle,
                            prioridad, worker_nombre_completo,
                        )
                    )

                    # 3. Notificar al NUEVO worker
                    notificar_worker_nueva_tarea(worker_phone, ticket_id, ubicacion, detalle, prioridad)

                    return True
                else:
                    send_whatsapp(from_phone, "❌ Error reasignando tarea")
                    return True
            else:
                # Múltiples coincidencias: mostrar opciones
                state["seleccion_mucamas"] = {
                    "tipo": "reasignar",
                    "ticket_id": ticket_id,
                    "candidatas": candidatas,
                    "worker_original": {
                        "phone": worker_original_phone,
                        "name": worker_original_name
                    },
                    "ubicacion": ticket.get("ubicacion") or ticket.get("habitacion", "?"),
                    "detalle": ticket.get("detalle", "Sin detalle"),
                    "prioridad": ticket.get("prioridad", "MEDIA")
                }
                from .worker_search import formato_lista_workers
                mensaje = formato_lista_workers(candidatas)
                send_whatsapp(from_phone, mensaje)
                return True
        
        # Caso 2: Cancelar
        elif mucama_seleccionada == "CANCEL":
            send_whatsapp(from_phone, "❌ Asignación cancelada")
            state.pop("seleccion_mucamas", None)
            return True
        
        # Caso 3: Selección inválida
        else:
            # Mensaje de error claro
            max_num = len(candidatas)
            send_whatsapp(
                from_phone,
                f"❌ Selección no válida\n\n"
                f"Por favor escribe:\n"
                f"• Un número del 1 al {max_num}\n"
                f"• O el apellido completo\n"
                f"• O 'cancelar' para abortar\n\n"
                f"Ejemplo: '1' o 'González'"
            )
            return True
    
    # ============================================================
    # (NUEVO) Si estoy esperando que el supervisor elija un worker (1..N)
    # ============================================================
    sel = state.get("seleccion_worker_pendiente")
    if sel:
        raw = (text or "").strip().lower()

        # cancelar selección
        if raw in {"cancelar", "cancel", "no"}:
            state.pop("seleccion_worker_pendiente", None)
            persist_supervisor_state(from_phone, state)
            send_whatsapp(from_phone, "✅ OK, cancelé la selección.")
            return True

        # elegir por número
        if raw.isdigit():
            idx = int(raw) - 1
            workers = sel.get("workers") or []
            if 0 <= idx < len(workers):
                worker = workers[idx]

                # Construir confirmación pendiente (aquí se “activa” el si/no)
                state["confirmacion_pendiente"] = {
                    "ticket_id": sel.get("ticket_id"),
                    "worker": worker,
                    # pasar contexto para que NO se pierda ubicación/detalle
                    "ubicacion": sel.get("ubicacion"),
                    "habitacion": sel.get("habitacion"),
                    "detalle": sel.get("detalle"),
                    "prioridad": sel.get("prioridad", "MEDIA"),
                }

                # ya no estamos en selección
                state.pop("seleccion_worker_pendiente", None)
                persist_supervisor_state(from_phone, state)

                worker_nombre = worker.get("nombre_completo") or worker.get("username") or "Sin nombre"
                send_whatsapp(
                    from_phone,
                    f"❓ Confirmas asignar a *{worker_nombre}*?\n\nResponde 'si' o 'no' (o 'cancelar')."
                )
                return True

            send_whatsapp(from_phone, "❌ Número inválido. Responde con un número de la lista o 'cancelar'.")
            return True

        # si responde otra cosa mientras está en selección
        send_whatsapp(from_phone, "💡 Responde con el número de la lista (ej: 1) o 'cancelar'.")
        return True

    # Si está esperando asignación y dice un nombre
    if state.get("esperando_asignacion"):
        worker_nombre = intent_data.get("components", {}).get("worker") or text.strip()
        worker_nombre = normalizar_nombre(worker_nombre)
        
        from gateway_app.services.workers_db import buscar_workers_por_nombre
        candidatas = buscar_workers_por_nombre(worker_nombre)

        
        if not candidatas:
            send_whatsapp(
                from_phone,
                f"❌ No encontré a '{worker_nombre}'\n\n"
                "💡 Di otro nombre o 'cancelar'"
            )
            return True
        
        ticket_id = state.get("ticket_seleccionado")
        if not ticket_id:
            state["esperando_asignacion"] = False
            return False
        
        if len(candidatas) == 1:
            # Solo una: asignar directamente
            worker = candidatas[0]
            send_whatsapp(from_phone, texto_ticket_asignado_simple(ticket_id, worker["nombre_completo"]))
            state["esperando_asignacion"] = False
            state["ticket_seleccionado"] = None
            return True
        else:
            # Múltiples: pedir que elija
            state["seleccion_mucamas"] = {
                "tipo": "asignar",
                "ticket_id": ticket_id,
                "candidatas": candidatas
            }
            mensaje = formato_lista_workers(candidatas)
            send_whatsapp(from_phone, mensaje)
            return True
    
    # ✅ NUEVO: Finalizar ticket
    if intent == "finalizar_ticket":
        ticket_id = intent_data["ticket_id"]
        finalizar_ticket_supervisor(from_phone, ticket_id)
        return True

    # ✅ NUEVO: Asignar ticket sin especificar worker → mostrar lista
    if intent == "asignar_ticket_sin_worker":
        ticket_id = intent_data["ticket_id"]
        from gateway_app.services.tickets_db import obtener_ticket_por_id
        
        ticket = obtener_ticket_por_id(ticket_id)
        if not ticket:
            send_whatsapp(from_phone, f"❌ No encontré la tarea #{ticket_id}")
            return True
        
        # Mostrar opciones de workers
        workers = obtener_todos_workers()
        
        # Guardar estado para esperar selección
        state["esperando_asignacion"] = True
        state["ticket_seleccionado"] = ticket_id
        persist_supervisor_state(from_phone, state)
        
        # Mostrar lista de workers
        mostrar_opciones_workers(from_phone, workers, ticket_id)
        return True

# Caso 1: Asignar ticket existente
    if intent == "asignar_ticket":
        ticket_id = intent_data["ticket_id"]
        worker_query = normalizar_nombre(intent_data["worker"])

        # Limpieza defensiva COMPLETA al inicio de nuevo intent
        state["esperando_asignacion"] = False
        state["ticket_seleccionado"] = None
        state.pop("seleccion_worker_pendiente", None)
        state.pop("confirmacion_pendiente", None)
        state.pop("seleccion_mucamas", None)

        from gateway_app.services.workers_db import buscar_workers_por_nombre
        from gateway_app.services.tickets_db import obtener_ticket_por_id

        candidatas = buscar_workers_por_nombre(worker_query) or []

        if not candidatas:
            send_whatsapp(
                from_phone,
                f"❌ No encontré a '{worker_query}'\n\n💡 Verifica el nombre"
            )
            return True

        # Traer ticket para armar confirmaciones con datos reales
        ticket = obtener_ticket_por_id(ticket_id) or {}
        detalle = ticket.get("detalle") or ticket.get("descripcion") or "Tarea asignada"
        prioridad = str(ticket.get("prioridad") or "MEDIA").upper()
        ubicacion = ticket.get("ubicacion") or ticket.get("habitacion") or "?"

        # Caso A: 1 match -> pedir SI/NO
        if len(candidatas) == 1:
            worker = candidatas[0]

            state["confirmacion_pendiente"] = {
                "tipo": "asignar",
                "ticket_id": ticket_id,
                "worker": worker,
                "detalle": detalle,
                "prioridad": prioridad,
                "ubicacion": ubicacion,
            }
            persist_supervisor_state(from_phone, state)

            worker_nombre = worker.get("nombre_completo") or worker.get("username") or "Sin nombre"

            send_whatsapp(
                from_phone,
                msg_sup_dialogo(ticket_id, ubicacion, detalle, prioridad, worker_nombre),
            )
            return True  # ✅ FIX: Evita que Caso B se ejecute

        # Caso B: múltiples -> pedir número
        else:  # ✅ FIX: Convertido a else (defensa adicional)
            candidatas_top = candidatas[:5]
            state["seleccion_worker_pendiente"] = {
                "tipo": "asignar",
                "ticket_id": ticket_id,
                "workers": candidatas_top,
                "detalle": detalle,
                "prioridad": prioridad,
                "ubicacion": ubicacion,
            }
            persist_supervisor_state(from_phone, state)

            send_whatsapp(
                from_phone,
                formato_lista_workers(candidatas_top) + "\n\n"
                "💡 Responde con el número (1-5) o 'cancelar'."
            )
            return True

    
    # Caso 1.5: Reasignar ticket existente
    if intent == "reasignar_ticket":
        ticket_id = intent_data["ticket_id"]
        worker_nombre = intent_data["worker"]
        
        # ✅ FIX 3: Limpieza defensiva al inicio
        state["esperando_asignacion"] = False
        state["ticket_seleccionado"] = None
        state.pop("seleccion_worker_pendiente", None)
        state.pop("confirmacion_pendiente", None)
        state.pop("seleccion_mucamas", None)
        
        from .worker_search import normalizar_nombre
        worker_nombre = normalizar_nombre(worker_nombre)
        
        # ✅ Obtener ticket para guardar worker original
        from gateway_app.services.tickets_db import obtener_ticket_por_id, asignar_ticket
        ticket = obtener_ticket_por_id(ticket_id)
        
        if not ticket:
            send_whatsapp(from_phone, f"❌ No encontré la tarea #{ticket_id}")
            return True
        
        # ✅ Guardar worker original
        huesped_whatsapp_original = ticket.get("huesped_whatsapp", "")
        if "|" in huesped_whatsapp_original:
            worker_original_phone, worker_original_name = huesped_whatsapp_original.split("|", 1)
        else:
            worker_original_phone = None
            worker_original_name = None
        
        # Buscar nuevo worker
        from gateway_app.services.workers_db import buscar_workers_por_nombre
        candidatas = buscar_workers_por_nombre(worker_nombre)
        
        if not candidatas:
            send_whatsapp(
                from_phone,
                f"❌ No encontré a '{worker_nombre}'\n\n"
                "💡 Verifica el nombre"
            )
            return True
        
        if len(candidatas) == 1:
            # ✅ Reasignar y notificar a TODOS
            worker = candidatas[0]
            worker_phone = worker.get("telefono")
            worker_nombre_completo = worker.get("nombre_completo", worker.get("nombre"))
            
            if asignar_ticket(ticket_id, worker_phone, worker_nombre_completo):
                ubicacion = ticket.get("ubicacion") or ticket.get("habitacion", "?")
                detalle = ticket.get("detalle", "Sin detalle")
                prioridad = ticket.get("prioridad", "MEDIA")

                # 1. Notificar al worker ORIGINAL
                if worker_original_phone:
                    from gateway_app.services.whatsapp_client import send_whatsapp_text
                    send_whatsapp_text(
                        to=worker_original_phone,
                        body=msg_worker_tarea_reasignada_saliente(
                            ticket_id, ubicacion, worker_nombre_completo,
                        ),
                    )
                    logger.info(f"✅ Notificación de reasignación enviada a {worker_original_phone}")

                # 2. Confirmar al SUPERVISOR
                send_whatsapp(
                    from_phone,
                    msg_sup_confirmacion(
                        ticket_id, "reasignada", ubicacion, detalle,
                        prioridad, worker_nombre_completo,
                    )
                )

                # 3. Notificar al NUEVO worker
                notificar_worker_nueva_tarea(worker_phone, ticket_id, ubicacion, detalle, prioridad)

                logger.info(f"✅ Tarea #{ticket_id} reasignada de {worker_original_name} a {worker_nombre_completo}")
                return True
            else:
                send_whatsapp(from_phone, "❌ Error reasignando tarea")
                return True
        else:
            # Múltiples: guardar en estado para selección
            from .worker_search import formato_lista_workers
            
            state["seleccion_mucamas"] = {
                "tipo": "reasignar",
                "ticket_id": ticket_id,
                "candidatas": candidatas,
                "worker_original": {
                    "phone": worker_original_phone,
                    "name": worker_original_name
                },
                "ubicacion": ticket.get("ubicacion") or ticket.get("habitacion", "?"),
                "detalle": ticket.get("detalle", "Sin detalle"),
                "prioridad": ticket.get("prioridad", "MEDIA")
            }
            mensaje = formato_lista_workers(candidatas)
            send_whatsapp(from_phone, mensaje)
            return True
    
    # Caso 2: Crear y asignar
    if intent == "crear_y_asignar":
        ubicacion = intent_data.get("ubicacion", intent_data.get("habitacion"))  # ✅ MODIFICADO
        detalle = intent_data["detalle"]
        prioridad = intent_data["prioridad"]
        nombre_trabajador = intent_data["worker"]
        
        # 1. Crear el ticket en BD
        from gateway_app.services.tickets_db import crear_ticket, asignar_ticket
        
        try:
            area = infer_area_from_ubicacion(ubicacion)
            ticket = crear_ticket(
                habitacion=ubicacion,  # ✅ MODIFICADO: Genérico
                detalle=detalle,
                prioridad=prioridad,
                area=area,
                creado_por=from_phone,
                origen="supervisor"
            )
            
            if not ticket:
                send_whatsapp(from_phone, "❌ Error creando tarea. Intenta de nuevo.")
                return True
            
            ticket_id = ticket["id"]
            prioridad_emoji = {"ALTA": "🔴", "MEDIA": "🟡", "BAJA": "🟢"}.get(prioridad, "🟡")
            
            # 2. Buscar trabajador
            from gateway_app.services.workers_db import buscar_workers_por_nombre
            coincidencias = buscar_workers_por_nombre(nombre_trabajador)
            
            if len(coincidencias) == 1:
                # ✅ PEDIR CONFIRMACIÓN
                worker = coincidencias[0]
                worker_phone = worker.get("telefono")
                worker_nombre = worker.get("nombre_completo") or worker.get("username")
                
                estado_emoji = {
                    "disponible": "✅",
                    "ocupada": "🔴",
                    "en_pausa": "⏸️"
                }.get(worker.get("estado"), "✅")
                
                # Guardar en estado para confirmar después
                state["confirmacion_pendiente"] = {
                    "tipo": "crear_y_asignar",
                    "ticket_id": ticket_id,
                    "worker": worker,
                    "ubicacion": ubicacion,  # ✅ MODIFICADO
                    "detalle": detalle,
                    "prioridad": prioridad
                }
                
                send_whatsapp(
                    from_phone,
                    msg_sup_dialogo(
                        ticket_id, ubicacion, detalle, prioridad,
                        worker_nombre, es_creacion=True,
                    )
                )
                return True
            
            elif len(coincidencias) > 1:
                # Múltiples: mostrar opciones
                state["ticket_seleccionado"] = ticket_id
                state["esperando_asignacion"] = True
                
                send_whatsapp(
                    from_phone,
                    msg_sup_confirmacion(
                        ticket_id, "creada", ubicacion, detalle, prioridad,
                        hint=f"📋 Encontré {len(coincidencias)} personas con '{nombre_trabajador}':",
                    )
                )
                
                from .ticket_assignment import calcular_score_worker
                from .ui_simple import texto_recomendaciones_simple
                from gateway_app.services.workers_db import obtener_todos_workers
                
                workers = obtener_todos_workers()
                workers_con_score = []
                for worker in workers:
                    score = calcular_score_worker(worker)
                    workers_con_score.append({**worker, "score": score})
                
                workers_con_score.sort(key=lambda w: w["score"], reverse=True)
                workers = obtener_todos_workers()
                mostrar_opciones_workers(from_phone, workers, ticket_id)

                state["ticket_seleccionado"] = ticket_id
                state["esperando_asignacion"] = True
                return True
            
            else:
                # No encontrado: mostrar todos
                state["ticket_seleccionado"] = ticket_id
                state["esperando_asignacion"] = True
                
                send_whatsapp(
                    from_phone,
                    msg_sup_confirmacion(
                        ticket_id, "creada", ubicacion, detalle, prioridad,
                        hint=f"⚠️ No encontré a '{nombre_trabajador}'\nMostrando todas las opciones:",
                    )
                )
                
                from .ticket_assignment import calcular_score_worker
                from .ui_simple import texto_recomendaciones_simple
                from gateway_app.services.workers_db import obtener_todos_workers
                
                workers = obtener_todos_workers()
                workers_con_score = []
                for worker in workers:
                    score = calcular_score_worker(worker)
                    workers_con_score.append({**worker, "score": score})
                
                workers_con_score.sort(key=lambda w: w["score"], reverse=True)
                workers = obtener_todos_workers()
                mostrar_opciones_workers(from_phone, workers, ticket_id)

                state["ticket_seleccionado"] = ticket_id
                state["esperando_asignacion"] = True
                return True
        
        except Exception as e:
            logger.exception(f"❌ Error en crear_y_asignar: {e}")
            send_whatsapp(from_phone, "❌ Error creando tarea. Intenta de nuevo.")
            return True

    # Caso 3: Solo crear
    if intent == "crear_ticket":
        ubicacion = intent_data.get("ubicacion", intent_data.get("habitacion"))
        detalle = intent_data["detalle"]
        
        from gateway_app.services.tickets_db import crear_ticket
        from gateway_app.services.ticket_classifier import clasificar_ticket  # ← NUEVO
        try:
            # ── Clasificación inteligente ────────────────────────────────
            clasificacion = clasificar_ticket(
                detalle=detalle,
                ubicacion=str(ubicacion) if ubicacion else "",
            )
            # ────────────────────────────────────────────────────────────
            
            ticket = crear_ticket(
                habitacion=ubicacion,
                detalle=detalle,
                prioridad=clasificacion["prioridad"],          # ← antes era intent_data["prioridad"]
                area=clasificacion["area"],                    # ← antes era infer_area_from_ubicacion()
                creado_por=from_phone,
                origen="supervisor",
                routing_source=clasificacion["routing_source"],    # ← NUEVO
                routing_reason=clasificacion["routing_reason"],    # ← NUEVO
                routing_confidence=clasificacion["routing_confidence"],  # ← NUEVO
                routing_version=clasificacion["routing_source"],   # ← NUEVO
            )
            
            if ticket:
                ticket_id = ticket["id"]

                send_whatsapp(
                    from_phone,
                    msg_sup_confirmacion(
                        ticket_id, "creada", ubicacion, detalle, prioridad,
                        hint=f"💡 Di 'asignar {ticket_id} a [nombre]'",
                    )
                )
                
                # Guardar para asignación rápida
                state["ticket_seleccionado"] = ticket_id
                state["esperando_asignacion"] = True
                
                # ✅ Recomendaciones (no deben romper el flujo si falla algo)
                try:
                    from gateway_app.services.workers_db import obtener_todos_workers
                    workers = obtener_todos_workers()
                    mostrar_opciones_workers(from_phone, workers, ticket_id)
                    
                    return True
                except Exception as e:
                    logger.exception(f"⚠️ No pude mostrar recomendaciones de workers: {e}")
                    # No abortar: el ticket ya se creó. Opcional: no enviar nada extra.
            else:
                send_whatsapp(from_phone, "❌ Error creando tarea. Intenta de nuevo.")
                return True
        
        # ✅ AQUÍ ESTÁ EL EXCEPT QUE FALTABA
        except Exception as e:
            logger.exception(f"❌ Error creando ticket en DB: {e}")
            send_whatsapp(from_phone, "❌ Error creando tarea. Intenta de nuevo.")
            return True
        
    # Caso 4: Asignar sin ticket (usar el de mayor prioridad)
    if intent == "asignar_sin_ticket":
        worker_nombre = intent_data.get("worker")
        
        if not worker_nombre:
            send_whatsapp(from_phone, "❌ No entendí el nombre del trabajador")
            return True
        
        from gateway_app.services.workers_db import buscar_worker_por_nombre
        from gateway_app.services.tickets_db import obtener_tickets_por_estado, asignar_ticket, obtener_ticket_por_id
        
        worker = buscar_worker_por_nombre(worker_nombre)
        
        if worker:
            tickets = obtener_pendientes()
            if tickets:
                prioridad_order = {"ALTA": 0, "MEDIA": 1, "BAJA": 2}
                tickets_sorted = sorted(
                    tickets,
                    key=lambda t: prioridad_order.get(t.get("prioridad", "MEDIA"), 1)
                )
                ticket = tickets_sorted[0]
                ticket_id = ticket["id"]
                
                worker_phone = worker.get("telefono")
                worker_nombre_completo = worker.get("nombre_completo") or worker.get("username")
                
                # ✅ Asignar en BD
                if asignar_ticket(ticket_id, worker_phone, worker_nombre_completo):
                    # Obtener datos completos del ticket
                    ticket_data = obtener_ticket_por_id(ticket_id)
                    habitacion = ticket_data.get("ubicacion") or ticket_data.get("habitacion", "?")
                    detalle = ticket_data.get("detalle", "Tarea asignada")
                    prioridad = ticket_data.get("prioridad", "MEDIA")
                    prioridad_emoji = {"ALTA": "🔴", "MEDIA": "🟡", "BAJA": "🟢"}.get(prioridad, "🟡")
                    
                    # 1. Notificar supervisor
                    send_whatsapp(
                        from_phone,
                        f"✅ Tarea #{ticket_id} asignada\n\n"
                        f"📍 Ubicación: {ticket.get('ubicacion') or ticket.get('habitacion') or '?'}",
                        f"📝 Problema: {detalle}\n"
                        f"{prioridad_emoji} Prioridad: {prioridad}\n"
                        f"👤 Asignado a: {worker_nombre_completo}"
                    )
                    
                    # 2. ✅ Notificar worker
                    from gateway_app.services.whatsapp_client import send_whatsapp_text
                    send_whatsapp_text(
                        to=worker_phone,
                        body=f"📋 Nueva tarea asignada\n\n"
                            f"#{ticket_id} · {ticket.get('ubicacion') or ticket.get('habitacion') or '?'}\n"
                            f"{detalle}\n"
                            f"{prioridad_emoji} Prioridad: {prioridad}\n\n"
                            f"💡 Responde 'tomar' para aceptar"
                    )
                    
                    return True
                else:
                    send_whatsapp(from_phone, "❌ Error asignando. Intenta de nuevo.")
                    return True
            else:
                send_whatsapp(from_phone, "✅ No hay tickets pendientes")
                return True
        else:
            send_whatsapp(from_phone, f"❌ No encontré a '{worker_nombre}'")
            return True
    
    return False