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
    except:
        return "?"


def formatear_ubicacion_con_emoji(ubicacion: str) -> str:
    """
    Agrega emoji apropiado según tipo de ubicación.
    
    Args:
        ubicacion: "305" o "Ascensor Piso 2"
    
    Returns:
        "🏠 Habitación 305" o "📍 Ascensor Piso 2"
    """
    if not ubicacion:
        return "📍 Sin ubicación"
    
    ubicacion = str(ubicacion).strip()
    
    # Si es número de 3-4 dígitos, es habitación
    if ubicacion.isdigit():
        num = int(ubicacion)
        if 100 <= num <= 9999:
            return f"🏠 Habitación {ubicacion}"
    
    # Si no, es área común
    return f"📍 {ubicacion}"

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

                    prioridad = (ticket.get("prioridad") or conf.get("prioridad") or "MEDIA")
                    prioridad = str(prioridad).upper()
                    prioridad_emoji = {"ALTA": "🔴", "MEDIA": "🟡", "BAJA": "🟢"}.get(prioridad, "🟡")

                    ubicacion = (
                        ticket.get("ubicacion")
                        or ticket.get("habitacion")
                        or conf.get("ubicacion")
                        or conf.get("habitacion")
                        or "?"
                    )
                    ubicacion_fmt = formatear_ubicacion_con_emoji(str(ubicacion))

                    # Área del worker (opcional, para mostrarlo)
                    worker_area = (worker.get("area") or "").upper()
                    area_tag = {"HOUSEKEEPING": "HK", "MANTENCION": "MT", "MANTENIMIENTO": "MT", "AREAS_COMUNES": "AC"}.get(worker_area, worker_area or "?")
                    area_emoji = {"HOUSEKEEPING": "🧹", "MANTENCION": "🔧", "MANTENIMIENTO": "🔧", "AREAS_COMUNES": "🏢"}.get(worker_area, "👤")

                    # 1) Confirmación al supervisor
                    send_whatsapp(
                        from_phone,
                        f"✅ Tarea #{ticket_id} asignada\n\n"
                        f"{ubicacion_fmt}\n"
                        f"📝 Problema: {detalle}\n"
                        f"{prioridad_emoji} Prioridad: {prioridad}\n"
                        f"👤 Asignado a: {worker_nombre} ({area_emoji} {area_tag})"
                    )

                    # 2) Notificación al worker
                    from gateway_app.services.whatsapp_client import send_whatsapp_text
                    send_whatsapp_text(
                        to=worker_phone,
                        body=(
                            "📋 Nueva tarea asignada\n\n"
                            f"#{ticket_id} · {ubicacion_fmt}\n"
                            f"{detalle}\n"
                            f"{prioridad_emoji} Prioridad: {prioridad}\n\n"
                            "💡 Responde 'tomar' para aceptar"
                        )
                    )

                    # Limpiar estado de confirmación
                    state.pop("confirmacion_pendiente", None)
                    persist_supervisor_state(from_phone, state)

                    ok = asignar_ticket(ticket_id, worker_phone, worker_nombre)
                    logger.info(f"[CONFIRM] asignar_ticket ticket_id={ticket_id} worker={worker_phone} ok={ok}")

                    if ok:
                        send_whatsapp(from_phone, "✅ Tarea #X asignada ...")
                    else:
                        send_whatsapp(from_phone, "❌ Error asignando ...")
                    return  # <- IMPORTANTE: cortar aquí

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
        
        # 4.1) Pendientes
        if raw in ["pendientes", "pendiente", "ver", "lista"]:
            mostrar_pendientes_simple(from_phone)
            return
        
        # 4.2) Asignados ← ✅ AQUÍ
        if raw in ["asignados", "asignadas", "en proceso", "activos", "activas", "trabajando"]:
            mostrar_tickets_asignados_y_en_curso(from_phone)
            return
        
        # 4.3) Más urgente / siguiente
        if raw in ["siguiente", "next", "proximo", "urgente", "asignar urgente", "mas urgente", "más urgente"]:
            asignar_siguiente(from_phone)
            return
        
        # 4.4) Ver urgentes
        if raw in ["urgentes", "critico"]:
            mostrar_urgentes(from_phone)
            return
        
        # 4.5) Ver retrasados
        if raw in ["retrasados", "retrasado", "atrasados"]:
            mostrar_retrasados(from_phone)
            return
        
        # 4.6) Ver en curso
        if raw in ["en curso", "proceso"]:
            mostrar_en_proceso(from_phone)
            return
        
        # 4.7) BD commands
        if raw in ["bd pendientes", "db pendientes", "pendientes bd"]:
            mostrar_tickets_db(from_phone, "PENDIENTE")
            return
        
        if raw in ["bd asignados", "db asignados", "asignados bd"]:
            mostrar_tickets_db(from_phone, "ASIGNADO")
            return
        
        if raw in ["bd en curso", "db en curso", "en curso bd"]:
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
        if raw in ['equipo', 'trabajadores', 'mucamas', 'team', 'staff', 'trabajadoras']:
            mensaje = construir_mensaje_equipo()
            send_whatsapp(from_phone, mensaje)
            return
        
        # 4.11) Cancelar
        if raw in ["cancelar", "cancel", "salir", "atras", "atrás"]:
            send_whatsapp(from_phone, "✅ No hay nada que cancelar ahora")
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
            "• 'pendientes' - ver todos\n"
            "• 'asignados' - ver trabajos activos\n"
            "• 'más urgente' - asignar la más importante\n"
            "• 'asignar [#] a [nombre]'\n"
            "• 'finalizar [#]'"
        )
    
    finally:
        persist_supervisor_state(from_phone, state)

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
        "pendientes", "urgente", "urgentes", "retrasados", 
        "help", "ayuda", "en curso", "hola"
    ]
    
    # ✅ NUEVO: Detectar intents de crear ticket
    tiene_ubicacion = False
    from .audio_commands import extract_habitacion, extract_area_comun
    
    if extract_habitacion(text) or extract_area_comun(text):
        tiene_ubicacion = True
    
    # Si es comando nuevo o tiene ubicación, salir del flujo de asignación
    if raw in comandos_nuevos or tiene_ubicacion:
        state["esperando_asignacion"] = False
        state["ticket_seleccionado"] = None
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
        
        # ✅ FILTRAR: Solo turno activo
        workers_activos = [w for w in workers if w.get("turno_activo", False)]

        workers_con_score = []
        for w in workers_activos:
            score = calcular_score_worker(w, ticket)  # ✅ Con ticket
            workers_con_score.append({**w, "score": score})
        
        workers_con_score.sort(key=lambda w: w["score"], reverse=True)
        
        if 0 <= index < len(workers_con_score):
            worker = workers_con_score[index]
        else:
            send_whatsapp(
                from_phone,
                f"❌ Número inválido (1-{min(5, len(workers_con_score))})\n\n"
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
            prioridad_emoji = {"ALTA": "🔴", "MEDIA": "🟡", "BAJA": "🟢"}.get(prioridad, "🟡")

            ubicacion_fmt = formatear_ubicacion_con_emoji(str(ubicacion))

            send_whatsapp_text(
                to=worker_phone,
                body=f"📋 Nueva tarea asignada\n\n"
                     f"#{ticket_id} · {ubicacion_fmt}\n"
                     f"{detalle}\n"
                     f"{prioridad_emoji} Prioridad: {prioridad}\n\n"
                     f"💡 Responde 'tomar' para aceptar"
                     f"💡 O 'tomar {ticket_id}' si te lo pido"
            )
            
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
    """
    ✅ MODIFICADO: Muestra tickets pendientes con tiempo transcurrido.
    """
    from gateway_app.services.tickets_db import obtener_pendientes
    
    tickets = obtener_pendientes()
    
    if not tickets:
        send_whatsapp(from_phone, "✅ No hay tickets pendientes")
        return
    
    # Ordenar por prioridad
    prioridad_order = {"ALTA": 0, "MEDIA": 1, "BAJA": 2}
    tickets.sort(key=lambda t: prioridad_order.get(t.get("prioridad", "MEDIA"), 1))
    
    mensaje = formatear_lista_tickets_con_tiempo(
        tickets,
        titulo="📋 Tickets Pendientes",
        mostrar_asignado=False,
        max_items=10
    )
    
    mensaje += "\n\n💡 Di 'asignar [#] a [nombre]'"
    mensaje += "\n💡 Di 'siguiente' para el próximo"
    
    send_whatsapp(from_phone, mensaje)


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
        except:
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
    workers_con_score = []
    for worker in workers:
        score = calcular_score_worker(worker, ticket)

        workers_con_score.append({**worker, "score": score})
    
    workers_con_score.sort(key=lambda m: m["score"], reverse=True)
    
    workers = obtener_todos_workers()
    mostrar_opciones_workers(from_phone, workers, ticket_id)
    state["esperando_asignacion"] = True


def mostrar_urgentes(from_phone: str) -> None:
    """Muestra solo tickets urgentes."""
    from gateway_app.services.tickets_db import obtener_tickets_por_estado
    from datetime import datetime, timedelta
    
    # Pendientes hace >5 min
    pendientes = obtener_tickets_por_estado("PENDIENTE")
    now = datetime.now()
    pendientes_urgentes = [
        t for t in pendientes 
        if (now - t.get("created_at", now)).total_seconds() / 60 > 5
    ]
    
    # En progreso hace >10 min
    progreso = obtener_tickets_por_estado("EN_CURSO")
    retrasados = [
        t for t in progreso 
        if t.get("started_at") and (now - t["started_at"]).total_seconds() / 60 > 10
    ]
    
    mensaje = texto_urgentes(pendientes_urgentes, retrasados)
    send_whatsapp(from_phone, mensaje)


def mostrar_en_proceso(from_phone: str) -> None:
    """
    ✅ MODIFICADO: Muestra tickets en proceso con tiempo transcurrido.
    """
    from gateway_app.services.tickets_db import obtener_tickets_por_estado
    
    tickets = obtener_tickets_por_estado("EN_CURSO")
    
    if not tickets:
        send_whatsapp(from_phone, "✅ No hay tareas en proceso")
        return
    
    mensaje = formatear_lista_tickets_con_tiempo(
        tickets,
        titulo="🔄 Tareas en Proceso",
        mostrar_asignado=True,
        max_items=10
    )
    
    mensaje += "\n\n💡 Di 'reasignar [#] a [nombre]'"
    
    send_whatsapp(from_phone, mensaje)


def mostrar_retrasados(from_phone: str) -> None:
    """Muestra solo tickets retrasados (>10 min)."""
    from gateway_app.services.tickets_db import obtener_tickets_por_estado
    
    tickets = obtener_tickets_por_estado("EN_CURSO")
    now = datetime.now()
    
    # ✅ CORREGIDO: Filtrar con manejo de errores
    retrasados = []
    for t in tickets:
        started_at = t.get("started_at")
        if started_at:
            try:
                from dateutil import parser
                if isinstance(started_at, str):
                    started_at = parser.parse(started_at)
                tiempo_mins = (datetime.now(started_at.tzinfo) - started_at).total_seconds() / 60
                if tiempo_mins > 10:
                    retrasados.append(t)
            except:
                pass
    
    if not retrasados:
        send_whatsapp(from_phone, "✅ No hay tickets retrasados")
        return
    
    lineas = [f"⏰ {len(retrasados)} tickets retrasados:\n"]
    
    for ticket in retrasados:
        # ✅ CORREGIDO: Extraer habitación
        hab = ticket.get('ubicacion') or ticket.get('habitacion', '?')
        
        # ✅ CORREGIDO: Extraer trabajador
        huesped_whatsapp = ticket.get("huesped_whatsapp", "")
        if "|" in huesped_whatsapp:
            worker_phone, trabajador = huesped_whatsapp.split("|", 1)
        else:
            trabajador = "Sin asignar"
        
        # ✅ CORREGIDO: Calcular tiempo
        created_at = ticket.get("created_at")
        if created_at:
            try:
                from dateutil import parser
                if isinstance(created_at, str):
                    created_at = parser.parse(created_at)
                tiempo = int((datetime.now(created_at.tzinfo) - created_at).total_seconds() / 60)
            except:
                tiempo = 0
        else:
            tiempo = 0
        
        lineas.append(
            f"⚠️ #{ticket['id']} · Hab. {hab} · {trabajador} · {tiempo} min"
        )
    
    lineas.append("\n💡 Di: 'reasignar [#] a [nombre]'")
    send_whatsapp(from_phone, "\n".join(lineas))


def mostrar_info_ticket(from_phone: str, ticket_id: int) -> None:
    from gateway_app.services.tickets_db import obtener_ticket_por_id
    
    ticket = obtener_ticket_por_id(ticket_id)
    
    if not ticket:
        send_whatsapp(from_phone, f"❌ No encontré la tarea #{ticket_id}")
        return
    
    # Mapear estado de BD a texto legible
    estado_map = {
        "PENDIENTE": "Pendiente",
        "ASIGNADO": "Asignado",
        "EN_CURSO": "En progreso",
        "PAUSADO": "Pausado",
        "RESUELTO": "Completado"
    }
    estado_actual = estado_map.get(ticket.get("estado", "PENDIENTE"), "Desconocido")

    
    # No hay tickets completados en demo_data, solo pendientes y en progreso
    
    if not ticket:
        send_whatsapp(from_phone, f"❌ No encontré la tarea #{ticket_id}")
        return
    
    # Formatear información
    prioridad_emoji = {
        "ALTA": "🔴",
        "MEDIA": "🟡",
        "BAJA": "🟢"
    }.get(ticket.get("prioridad", "MEDIA"), "🟡")
    
    estado_emoji = {
        "Pendiente": "⏳",
        "En progreso": "🔄",
        "Completado": "✅"
    }.get(estado_actual, "❓")
    
    lineas = [
        f"{estado_emoji} Tarea #{ticket_id}\n",
        f"📍 Ubicación: {ticket.get('ubicacion') or ticket.get('habitacion') or '?'}",
        f"📝 Detalle: {ticket['detalle']}",
        f"{prioridad_emoji} Prioridad: {ticket.get('prioridad', 'MEDIA')}",
        f"📊 Estado: {estado_actual}"
    ]
    
    # Info adicional según estado
    if estado_actual == "En progreso":
        asignado = ticket.get("asignado_a_nombre", "?")
        tiempo = ticket.get("tiempo_sin_resolver_mins", 0)
        lineas.append(f"👤 Trabajador: {asignado}")
        lineas.append(f"⏱️ Tiempo: {tiempo} min")
    elif estado_actual == "Completado":
        asignado = ticket.get("asignado_a_nombre", "?")
        lineas.append(f"👤 Trabajador: {asignado}")
    elif estado_actual == "Pendiente":
        tiempo = ticket.get("tiempo_sin_resolver_mins", 0)
        lineas.append(f"⏱️ Esperando: {tiempo} min")
    
    send_whatsapp(from_phone, "\n".join(lineas))

def mostrar_tickets_db(from_phone: str, estado: str = "PENDIENTE") -> None:
    """
    Muestra tickets desde la BD real por estado.
    
    Args:
        from_phone: Teléfono del supervisor
        estado: Estado a filtrar
    """
    from gateway_app.services.tickets_db import obtener_tickets_por_estado
    
    tickets = obtener_tickets_por_estado(estado)
    
    if not tickets:
        send_whatsapp(from_phone, f"✅ No hay tickets en estado '{estado}'")
        return
    
    estado_emoji = {
        "PENDIENTE": "⏳",
        "ASIGNADO": "👤",
        "EN_CURSO": "🔄",
        "PAUSADO": "⏸️",
        "RESUELTO": "✅"
    }.get(estado, "📋")
    
    lineas = [f"{estado_emoji} {len(tickets)} ticket(s) {estado.lower()}:\n"]
    
    for ticket in tickets[:10]:
        prioridad_emoji = {
            "ALTA": "🔴",
            "MEDIA": "🟡",
            "BAJA": "🟢"
        }.get(ticket.get("prioridad", "MEDIA"), "🟡")
        
        ubicacion = ticket.get("ubicacion", "?")
        detalle = ticket.get("detalle", "")[:30]
        
        # Extraer nombre del trabajador si está asignado
        huesped_wa = ticket.get("huesped_whatsapp", "")
        if "|" in huesped_wa:
            worker_phone, worker_name = huesped_wa.split("|", 1)
        else:
            worker_name = "Sin asignar"
        
        lineas.append(
            f"{prioridad_emoji} #{ticket['id']} · Hab.{ubicacion} · {worker_name}\n"
            f"   {detalle}..."
        )
    
    if len(tickets) > 10:
        lineas.append(f"\n... y {len(tickets) - 10} más")
    
    send_whatsapp(from_phone, "\n".join(lineas))

def mostrar_tickets_asignados_y_en_curso(from_phone: str) -> None:
    """
    Muestra todos los tickets asignados y en curso.
    """
    from gateway_app.services.tickets_db import obtener_tickets_asignados_y_en_curso
    
    tickets = obtener_tickets_asignados_y_en_curso()
    
    if not tickets:
        send_whatsapp(
            from_phone,
            "✅ No hay tareas asignadas ni en proceso"
        )
        return
    
    # Separar por estado
    asignados = [t for t in tickets if t.get("estado") == "ASIGNADO"]
    en_curso = [t for t in tickets if t.get("estado") == "EN_CURSO"]
    
    # Construir mensaje
    lineas = [f"📋 {len(tickets)} tarea(s) activa(s):\n"]
    
    # Primero EN_CURSO
    if en_curso:
        lineas.append(f"⚙️ EN PROCESO ({len(en_curso)}):\n")
        for ticket in en_curso[:5]:
            ticket_id = ticket.get("id")
            ubicacion = ticket.get("ubicacion", "?")
            detalle = ticket.get("detalle", "Sin detalle")[:30]
            prioridad = ticket.get("prioridad", "MEDIA")
            worker = ticket.get("worker_name") or "Sin asignar"  # ✅ Usar worker_name
            
            emoji_prioridad = {
                "ALTA": "🔴",
                "MEDIA": "🟡",
                "BAJA": "🟢"
            }.get(prioridad, "🟡")
            
            # Formatear ubicación
            ubicacion_fmt = formatear_ubicacion_con_emoji(ubicacion)
            ubicacion_corta = ubicacion_fmt.replace("🏠 Habitación ", "Hab. ").replace("📍 ", "")
            
            lineas.append(
                f"{emoji_prioridad} #{ticket_id} · {ubicacion_corta} · {detalle}\n"
                f"   👤 {worker[:15]}\n"
            )
        
        if len(en_curso) > 5:
            lineas.append(f"   ... y {len(en_curso) - 5} más\n")
    
    # Luego ASIGNADOS
    if asignados:
        lineas.append(f"\n📋 ASIGNADOS ({len(asignados)}):\n")
        for ticket in asignados[:5]:
            ticket_id = ticket.get("id")
            ubicacion = ticket.get("ubicacion", "?")
            detalle = ticket.get("detalle", "Sin detalle")[:30]
            prioridad = ticket.get("prioridad", "MEDIA")
            worker = ticket.get("worker_name") or "Sin asignar"  # ✅ Usar worker_name
            
            emoji_prioridad = {
                "ALTA": "🔴",
                "MEDIA": "🟡",
                "BAJA": "🟢"
            }.get(prioridad, "🟡")
            
            # Formatear ubicación
            ubicacion_fmt = formatear_ubicacion_con_emoji(ubicacion)
            ubicacion_corta = ubicacion_fmt.replace("🏠 Habitación ", "Hab. ").replace("📍 ", "")
            
            lineas.append(
                f"{emoji_prioridad} #{ticket_id} · {ubicacion_corta} · {detalle}\n"
                f"   👤 {worker[:15]}\n"
            )
        
        if len(asignados) > 5:
            lineas.append(f"   ... y {len(asignados) - 5} más\n")
    
    lineas.append("\n💡 Di 'finalizar [#]' o 'reasignar [#] a [nombre]'")
    
    send_whatsapp(from_phone, "".join(lineas))
    logger.info(f"📋 Mostrados {len(tickets)} tickets asignados/en_curso a supervisor")

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
            f"❌ No encontré el ticket #{ticket_id}\n\n"
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
            f"⚠️ El ticket #{ticket_id} ya está completado\n\n"
            f"✅ Finalizado hace {tiempo_desde}"
        )
        logger.info(f"👔 SUP | Ticket #{ticket_id} ya completado")
        return
    
    if estado_actual == "CANCELADO":
        send_whatsapp(
            from_phone,
            f"⚠️ El ticket #{ticket_id} está cancelado\n\n"
            f"💡 No se puede finalizar un ticket cancelado"
        )
        logger.info(f"👔 SUP | Ticket #{ticket_id} cancelado, no se puede finalizar")
        return
    
    # 3. Obtener datos del ticket
    ubicacion = ticket.get("habitacion") or ticket.get("ubicacion", "?")
    detalle = ticket.get("detalle", "Sin detalle")
    prioridad = ticket.get("prioridad", "MEDIA")
    asignado_a = ticket.get("asignado_a_telefono")
    worker_nombre = ticket.get("asignado_a_nombre", "?")
    
    # 4. Calcular duración
    created_at = ticket.get("created_at")
    duracion_min = 0
    
    if created_at:
        try:
            from dateutil import parser
            inicio = parser.parse(str(created_at))
            ahora = datetime.now(inicio.tzinfo) if inicio.tzinfo else datetime.now()
            duracion_min = int((ahora - inicio).total_seconds() / 60)
        except Exception as e:
            logger.warning(f"Error calculando duración: {e}")
            duracion_min = 0
    
    # 5. Actualizar en BD
    exito = actualizar_estado_ticket(ticket_id, "COMPLETADO")
    
    if not exito:
        send_whatsapp(
            from_phone,
            f"❌ Error al finalizar ticket #{ticket_id}\n\n"
            f"💡 Intenta de nuevo o contacta soporte"
        )
        logger.error(f"👔 SUP | Error finalizando ticket #{ticket_id}")
        return
    
    # 6. Formatear ubicación con emoji
    ubicacion_fmt = formatear_ubicacion_con_emoji(ubicacion)
    
    # 7. Emojis
    prioridad_emoji = {"ALTA": "🔴", "MEDIA": "🟡", "BAJA": "🟢"}.get(prioridad, "🟡")
    estado_anterior_emoji = {
        "PENDIENTE": "⏳",
        "ASIGNADO": "📋",
        "EN_CURSO": "⚙️"
    }.get(estado_actual, "📋")
    
    # 8. Confirmar al supervisor
    mensaje_supervisor = (
        f"✅ Ticket #{ticket_id} finalizado por supervisión\n\n"
        f"{ubicacion_fmt}\n"
        f"📝 {detalle}\n"
        f"{prioridad_emoji} Prioridad: {prioridad}\n"
        f"{estado_anterior_emoji} Estado anterior: {estado_actual}\n"
        f"⏱️ Duración: {duracion_min} min"
    )
    
    if asignado_a:
        mensaje_supervisor += f"\n👤 Asignado a: {worker_nombre}"
    
    send_whatsapp(from_phone, mensaje_supervisor)
    logger.info(f"✅ Ticket #{ticket_id} finalizado por supervisión")
    
    # 9. Notificar al worker si estaba asignado
    if asignado_a:
        mensaje_worker = (
            f"ℹ️ Supervisión finalizó el ticket #{ticket_id}\n\n"
            f"{ubicacion_fmt}\n"
            f"📝 {detalle}\n\n"
            f"✅ Ya no necesitas completarlo"
        )
        
        try:
            send_whatsapp_text(to=asignado_a, body=mensaje_worker)
            logger.info(f"✅ Worker {asignado_a} notificado de finalización")
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
                prioridad_emoji = {"ALTA": "🔴", "MEDIA": "🟡", "BAJA": "🟢"}.get(prioridad, "🟡")
                ubicacion = seleccion_info.get("ubicacion") or seleccion_info.get("habitacion") or "?"
                ubicacion_fmt = formatear_ubicacion_con_emoji(ubicacion)
                ticket = obtener_ticket_por_id(ticket_id)
                detalle = (ticket.get("detalle") or "—").strip()

                send_whatsapp(
                    from_phone,
                    f"✅ Tarea #{ticket_id} asignada\n\n"
                    f"{ubicacion_fmt}\n"
                    f"📝 Problema: {detalle}\n"
                    f"{prioridad_emoji} Prioridad: {prioridad}\n"
                    f"👤 Asignado a: {worker_nombre}"
                )

                send_whatsapp_text(
                    to=worker_phone,
                    body=(
                        "📋 Nueva tarea asignada\n\n"
                        f"#{ticket_id} · {ubicacion_fmt}\n"
                        f"{detalle}\n"
                        f"{prioridad_emoji} Prioridad: {prioridad}\n\n"
                        "💡 Responde 'tomar' para aceptar"
                    )
                )

                # ✅ NUEVO: Notificar al worker original si es reasignación
                if seleccion_info.get("tipo") == "reasignar":
                    worker_original = seleccion_info.get("worker_original", {})
                    worker_original_phone = worker_original.get("phone")
                    
                    if worker_original_phone:
                        ubicacion = seleccion_info.get("ubicacion", "?")
                        send_whatsapp_text(
                            to=worker_original_phone,
                            body=f"📢 Tu tarea #{ticket_id} (Hab. {ubicacion}) fue reasignada a {worker_nombre}"
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
                send_whatsapp(from_phone, f"❌ No encontré el ticket #{ticket_id}")
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
                    prioridad_emoji = {"ALTA": "🔴", "MEDIA": "🟡", "BAJA": "🟢"}.get(prioridad, "🟡")
                    
                    # 1. Notificar al worker ORIGINAL
                    if worker_original_phone:
                        from gateway_app.services.whatsapp_client import send_whatsapp_text
                        send_whatsapp_text(
                            worker_original_phone,
                            f"📢 Tu tarea #{ticket_id} (Hab. {ubicacion}) fue reasignada a {worker_nombre_completo}"
                        )
                        logger.info(f"✅ Notificación de reasignación enviada a {worker_original_phone}")
                    
                    # 2. Confirmar al SUPERVISOR
                    send_whatsapp(
                        from_phone,
                        f"✅ Tarea #{ticket_id} reasignada\n\n"
                        f"🛏️ Habitación: {ubicacion}\n"
                        f"📝 Problema: {detalle}\n"
                        f"{prioridad_emoji} Prioridad: {prioridad}\n"
                        f"👤 Reasignado a: {worker_nombre_completo}"
                    )
                    
                    # 3. Notificar al NUEVO worker
                    from gateway_app.services.whatsapp_client import send_whatsapp_text
                    send_whatsapp_text(
                        worker_phone,
                        f"📋 Nueva tarea asignada\n\n"
                        f"#{ticket_id} · Hab. {ubicacion}\n"
                        f"{detalle}\n"
                        f"{prioridad_emoji} Prioridad: {prioridad}\n\n"
                        f"💡 Responde 'tomar' para aceptar"
                    )
                    
                    return True
                else:
                    send_whatsapp(from_phone, "❌ Error reasignando ticket")
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

    # Caso 1: Asignar ticket existente
    if intent == "asignar_ticket":
        ticket_id = intent_data["ticket_id"]
        worker_query = normalizar_nombre(intent_data["worker"])

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

        # Limpieza preventiva de estados viejos
        state.pop("seleccion_worker_pendiente", None)
        state.pop("confirmacion_pendiente", None)

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
            ubicacion_fmt = formatear_ubicacion_con_emoji(str(ubicacion))

            send_whatsapp(
                from_phone,
                "🟦 Confirmar asignación\n\n"
                f"📋 Tarea #{ticket_id}\n"
                f"{ubicacion_fmt}\n"
                f"📝 Problema: {detalle}\n\n"
                f"👤 ¿Asignar a: {worker_nombre}?\n\n"
                "Responde: 'si' / 'no' (o 'cancelar')"
            )
            return True

        # Caso B: múltiples -> pedir número
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
        
        from .worker_search import normalizar_nombre
        worker_nombre = normalizar_nombre(worker_nombre)
        
        # ✅ Obtener ticket para guardar worker original
        from gateway_app.services.tickets_db import obtener_ticket_por_id, asignar_ticket
        ticket = obtener_ticket_por_id(ticket_id)
        
        if not ticket:
            send_whatsapp(from_phone, f"❌ No encontré el ticket #{ticket_id}")
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
                prioridad_emoji = {"ALTA": "🔴", "MEDIA": "🟡", "BAJA": "🟢"}.get(prioridad, "🟡")
                
                # 1. ✅ Notificar al worker ORIGINAL (SINTAXIS CORREGIDA)
                if worker_original_phone:
                    from gateway_app.services.whatsapp_client import send_whatsapp_text
                    ubicacion_fmt = formatear_ubicacion_con_emoji(ubicacion)
                    send_whatsapp_text(
                        to=worker_original_phone,  # ✅ Parámetro con nombre
                        body=f"📢 Tu tarea #{ticket_id} ({ubicacion_fmt}) fue reasignada a {worker_nombre_completo}"
                    )
                    logger.info(f"✅ Notificación de reasignación enviada a {worker_original_phone}")
                
                # 2. ✅ Confirmar al SUPERVISOR
                ubicacion_fmt = formatear_ubicacion_con_emoji(ubicacion)

                send_whatsapp(
                    from_phone,
                    f"✅ Tarea #{ticket_id} reasignada\n\n"
                    f"{ubicacion_fmt}\n"
                    f"📝 Problema: {detalle}\n"
                    f"{prioridad_emoji} Prioridad: {prioridad}\n"
                    f"👤 Reasignado a: {worker_nombre_completo}"
                )
                
                # 3. ✅ Notificar al NUEVO worker (SINTAXIS CORREGIDA)
                from gateway_app.services.whatsapp_client import send_whatsapp_text
                ubicacion_fmt = formatear_ubicacion_con_emoji(ubicacion)
                send_whatsapp_text(
                    to=worker_phone,  # ✅ Parámetro con nombre
                    body=f"📋 Nueva tarea asignada\n\n"
                         f"#{ticket_id} · {ubicacion_fmt}\n"
                         f"{detalle}\n"
                         f"{prioridad_emoji} Prioridad: {prioridad}\n\n"
                         f"💡 Responde 'tomar' para aceptar"
                )
                
                logger.info(f"✅ Ticket #{ticket_id} reasignado de {worker_original_name} a {worker_nombre_completo}")
                return True
            else:
                send_whatsapp(from_phone, "❌ Error reasignando ticket")
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
                
                # Mostrar resumen COMPLETO y pedir confirmación
                ubicacion_fmt = formatear_ubicacion_con_emoji(ubicacion)

                send_whatsapp(
                    from_phone,
                    f"🟦 Confirmar asignación\n\n"
                    f"📋 Tarea #{ticket_id} creada\n"
                    f"{ubicacion_fmt}\n"
                    f"📝 {detalle}\n"
                    f"{prioridad_emoji} Prioridad: {prioridad}\n\n"
                    f"👤 ¿Asignar a: {worker_nombre}?\n"
                    f"Responde: 'si' / 'no'"
                )
                return True
            
            elif len(coincidencias) > 1:
                # Múltiples: mostrar opciones
                state["ticket_seleccionado"] = ticket_id
                state["esperando_asignacion"] = True
                
                send_whatsapp(
                    from_phone,
                    f"✅ Tarea #{ticket_id} creada\n\n"
                    f"📍 Ubicación: {ticket.get('ubicacion') or ticket.get('habitacion') or '?'}\n"
                    f"📝 Problema: {detalle}\n"
                    f"{prioridad_emoji} Prioridad: {prioridad}\n\n"
                    f"📋 Encontré {len(coincidencias)} personas con '{nombre_trabajador}':"
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
                    f"✅ Tarea #{ticket_id} creada\n\n"
                    f"🛏️ Habitación: {habitacion}\n"
                    f"📝 Problema: {detalle}\n"
                    f"{prioridad_emoji} Prioridad: {prioridad}\n\n"
                    f"⚠️ No encontré a '{nombre_trabajador}'\n"
                    f"Mostrando todas las opciones:"
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
        ubicacion = intent_data.get("ubicacion", intent_data.get("habitacion"))  # ✅ MODIFICADO
        detalle = intent_data["detalle"]
        prioridad = intent_data["prioridad"]
        
        # ✅ GUARDAR EN DB REAL
        from gateway_app.services.tickets_db import crear_ticket
        
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
            
            if ticket:
                ticket_id = ticket["id"]
                prioridad_emoji = {"ALTA": "🔴", "MEDIA": "🟡", "BAJA": "🟢"}.get(prioridad, "🟡")

                # ✅ CORREGIDO: Formatear ubicación con emoji
                ubicacion_fmt = formatear_ubicacion_con_emoji(ubicacion)
                
                send_whatsapp(
                    from_phone,
                    f"✅ Tarea #{ticket_id} creada\n\n"
                    f"{ubicacion_fmt}\n"  # ✅ Con emoji apropiado
                    f"📝 Problema: {detalle}\n"
                    f"{prioridad_emoji} Prioridad: {prioridad}\n\n"
                    f"💡 Di 'asignar {ticket_id} a [nombre]'"
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