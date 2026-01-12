"""
Orquestador SIMPLE para supervisión - Sin menú, solo comandos.
"""
import logging

from .ticket_assignment import calcular_score_worker
from gateway_app.services.workers_db import buscar_worker_por_nombre, obtener_todos_workers
from gateway_app.services.tickets_db import obtener_tickets_asignados_a


logger = logging.getLogger(__name__)

from datetime import date
from .state import get_supervisor_state
from .ui_simple import (
    texto_saludo_supervisor,
    texto_tickets_pendientes_simple,
    texto_urgentes
)
from .outgoing import send_whatsapp


def handle_supervisor_message_simple(from_phone: str, text: str) -> None:
    """
    Orquestador SIMPLE - sin menú, solo comandos naturales.
    
    Args:
        from_phone: Número de teléfono del supervisor
        text: Texto del mensaje (puede venir de audio)
    """

    state = get_supervisor_state(from_phone)
    try:
        raw = (text or "").strip().lower()
        logger.info(f"👔 SUP | {from_phone} | Comando: '{raw[:30]}...'")
        
        # 1) Saludo inicial del día (solo una vez)
        today_str = date.today().isoformat()
        if state.get("last_greet_date") != today_str:
            state["last_greet_date"] = today_str
            send_whatsapp(from_phone, texto_saludo_supervisor())
            return
        
        # 2) Si está esperando asignación, manejar respuesta
        if state.get("esperando_asignacion"):
            if handle_respuesta_asignacion(from_phone, text):
                return
        
        # 3) Comandos de audio (asignar, crear)
        if maybe_handle_audio_command_simple(from_phone, text):
            return
        
        # 4) Comando: Ver pendientes
        if raw in ["pendientes", "pendiente", "ver", "lista"]:
            mostrar_pendientes_simple(from_phone)
            return
        
        # 4.5) Comando: Ver por estado desde BD (NUEVO)
        if raw in ["bd pendientes", "db pendientes", "pendientes bd"]:
            mostrar_tickets_db(from_phone, "PENDIENTE")
            return
        
        if raw in ["bd asignados", "db asignados", "asignados bd"]:
            mostrar_tickets_db(from_phone, "ASIGNADO")
            return
        
        if raw in ["bd en curso", "db en curso", "en curso bd"]:
            mostrar_tickets_db(from_phone, "EN_CURSO")
            return
        
        # 5) Comando: Asignar urgente / más urgente / siguiente
        if raw in ["siguiente", "next", "proximo", "urgente", "asignar urgente", "mas urgente", "más urgente"]:
            asignar_siguiente(from_phone)
            return
        
        # 6) Comando: Urgente
        if raw in ["urgente", "urgentes", "critico"]:
            mostrar_urgentes(from_phone)
            return
        
        # 6.5) Comando: Ver info de ticket específico
        if any(word in raw for word in ["ticket", "tarea", "cual es", "cuál es", "ver el", "info"]):
            import re
            match = re.search(r'\b(\d{3,4})\b', raw)
            if match:
                ticket_id = int(match.group(1))
                mostrar_info_ticket(from_phone, ticket_id)
                return
        
        # 7) Comando: Retrasados
        if raw in ["retrasados", "retrasado", "atrasados"]:
            mostrar_retrasados(from_phone)
            return
        
        # 7.5) Comando: "asignar" solo (sin detalles)
        if raw in ["asignar", "derivar", "enviar"]:
            send_whatsapp(
                from_phone,
                "💡 Para asignar, di:\n"
                "• 'más urgente' - asigna la más importante\n"
                "• 'asignar [#] a [nombre]' - asigna específica\n"
                "• 'pendientes' - ve todas primero"
            )
            return
        
        # 8) Comando: Ver tickets en proceso
        if raw in ["en proceso", "progreso", "trabajando", "en curso", "activos"]:
            mostrar_en_proceso(from_phone)
            return
        
        # 9) Comando: Reasignar (ahora usa audio_commands)
        # Esto se maneja en maybe_handle_audio_command_simple
        if "reasignar" in raw or "cambiar" in raw:
            # Intentar detectar con audio_commands
            if maybe_handle_audio_command_simple(from_phone, text):
                return
            # Si no se detectó, pedir formato correcto
            send_whatsapp(
                from_phone,
                "💡 Para reasignar, di:\n"
                "• 'reasignar [#] a [nombre]'\n"
                "• 'cambiar [#] a [nombre]'\n\n"
                "Ejemplo: 'reasignar 1503 a María'"
            )
            return
        
        # 10) Comando: Cancelar (cuando no hay nada que cancelar)
        if raw in ["cancelar", "cancel", "salir", "atras", "atrás"]:
            send_whatsapp(from_phone, "✅ No hay nada que cancelar ahora")
            return
        
        # 9) No entendí - dar sugerencias
        send_whatsapp(
            from_phone,
            "🤔 No entendí.\n\n"
            "💡 Puedes decir:\n"
            "• 'pendientes' - ver todos\n"
            "• 'más urgente' - asignar la más importante\n"
            "• 'urgente' - ver solo urgentes\n"
            "• 'asignar [#] a [nombre]'\n"
            "• 'hab [#] [detalle]'"
        )
    finally:
        from .state import persist_supervisor_state
        persist_supervisor_state(from_phone, state)


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
    
    # NUEVO: Permitir cancelar
    if raw in ["cancelar", "cancel", "salir", "atras", "atrás", "volver"]:
        state["esperando_asignacion"] = False
        state["ticket_seleccionado"] = None
        send_whatsapp(from_phone, "❌ Asignación cancelada")
        return True
    
    # NUEVO: Permitir comandos globales
    if raw in ["pendientes", "urgente", "urgentes", "retrasados", "help", "ayuda"]:
        # Cancelar selección y dejar que otros comandos se ejecuten
        state["esperando_asignacion"] = False
        state["ticket_seleccionado"] = None
        return False  # Devolver False para que se procese el comando
    
    worker = None
    
    # Opción 1: Respuesta por número (1, 2, 3)
    if raw.isdigit():
        index = int(raw) - 1
        
        # Ordenar workers por score igual que en recomendaciones
        from gateway_app.services.workers_db import obtener_todos_workers
        all_workers = obtener_todos_workers()

        workers_con_score = []
        for w in all_workers:
            score = calcular_score_worker(w)
            workers_con_score.append({**w, "score": score})

        
        workers_con_score.sort(key=lambda w: w["score"], reverse=True)
        
        if 0 <= index < len(workers_con_score):
            worker = workers_con_score[index]
        else:
            send_whatsapp(
                from_phone,
                f"❌ Número inválido (1-{len(workers_con_score)})\n\n"
                "💡 Di el nombre o número (1, 2, 3)\n"
                "O escribe 'cancelar' para abortar"
            )
            return True
    
    # Opción 2: Respuesta por nombre
    else:
        from gateway_app.services.workers_db import buscar_worker_por_nombre
        worker = buscar_worker_por_nombre(raw)

    
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
            send_whatsapp_text(
                to=worker_phone,
                body=f"📋 Nueva tarea asignada\n\n"
                     f"#{ticket_id} · Habitación asignada\n"
                     f"💡 Responde 'tomar' para aceptar"
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
    """Muestra tickets pendientes de forma simple."""
    from gateway_app.services.tickets_db import obtener_tickets_por_estado
    
    tickets = obtener_tickets_por_estado("PENDIENTE")
    
    # Ordenar por prioridad
    prioridad_order = {"ALTA": 0, "MEDIA": 1, "BAJA": 2}
    tickets_sorted = sorted(
        tickets,
        key=lambda t: (
            prioridad_order.get(t.get("prioridad", "MEDIA"), 1),
            -t.get("tiempo_sin_resolver_mins", 0)
        )
    )
    
    mensaje = texto_tickets_pendientes_simple(tickets_sorted)
    send_whatsapp(from_phone, mensaje)


def asignar_siguiente(from_phone: str) -> None:
    """Asigna el ticket de mayor prioridad."""
    from gateway_app.services.tickets_db import obtener_tickets_por_estado
    from gateway_app.services.workers_db import obtener_todos_workers
    from .ticket_assignment import calcular_score_worker
    from .ui_simple import texto_recomendaciones_simple
    
    tickets = obtener_tickets_por_estado("PENDIENTE")
    
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
    
    send_whatsapp(
        from_phone,
        f"📋 Siguiente ticket:\n\n"
        f"{prioridad_emoji} #{ticket_id} · Hab. {ticket['habitacion']}\n"
        f"{ticket['detalle']}\n"
        f"{ticket['tiempo_sin_resolver_mins']} min esperando"
    )
    
    # Mostrar recomendaciones compactas (inline, no función externa)
    all_workers = obtener_todos_workers()
    workers_con_score = []
    for worker in all_workers:
        score = calcular_score_worker(worker)

        workers_con_score.append({**worker, "score": score})
    
    workers_con_score.sort(key=lambda m: m["score"], reverse=True)
    
    mensaje = texto_recomendaciones_simple(workers_con_score)
    send_whatsapp(from_phone, mensaje)
    
    # Guardar estado de asignación
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
    """Muestra todos los tickets en proceso."""
    from gateway_app.services.tickets_db import obtener_tickets_por_estado
    
    tickets = obtener_tickets_por_estado("EN_CURSO")
    
    if not tickets:
        send_whatsapp(from_phone, "✅ No hay tareas en proceso")
        return
    
    lineas = [f"🔄 {len(tickets)} tarea(s) en proceso:\n"]
    
    for ticket in tickets[:10]:  # Máximo 10
        prioridad_emoji = {
            "ALTA": "🔴",
            "MEDIA": "🟡",
            "BAJA": "🟢"
        }.get(ticket.get("prioridad", "MEDIA"), "🟡")
        
        trabajador = ticket.get("asignado_a_nombre", "?")
        tiempo = ticket.get("tiempo_sin_resolver_mins", 0)
        
        lineas.append(
            f"{prioridad_emoji} #{ticket['id']} · {trabajador} · "
            f"Hab. {ticket['habitacion']} · {tiempo} min"
        )
    
    if len(tickets) > 10:
        lineas.append(f"\n... y {len(tickets) - 10} más")
    
    lineas.append("\n💡 Di 'reasignar [#] a [nombre]'")
    
    send_whatsapp(from_phone, "\n".join(lineas))


def mostrar_retrasados(from_phone: str) -> None:
    """Muestra solo tickets retrasados (>10 min)."""
    from gateway_app.services.tickets_db import obtener_tickets_por_estado
    from datetime import datetime
    
    tickets = obtener_tickets_por_estado("EN_CURSO")
    now = datetime.now()
    retrasados = [
        t for t in tickets 
        if t.get("started_at") and (now - t["started_at"]).total_seconds() / 60 > 10
    ]
    
    if not retrasados:
        send_whatsapp(from_phone, "✅ No hay tickets retrasados")
        return
    
    lineas = [f"⏰ {len(retrasados)} tickets retrasados:\n"]
    
    for ticket in retrasados:
        lineas.append(
            f"⚠️ #{ticket['id']} · Hab. {ticket['habitacion']} · "
            f"{ticket['asignado_a_nombre']} · {ticket['tiempo_sin_resolver_mins']} min"
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
        f"🏨 Habitación: {ticket['habitacion']}",
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
            _, worker_name = huesped_wa.split("|", 1)
        else:
            worker_name = "Sin asignar"
        
        lineas.append(
            f"{prioridad_emoji} #{ticket['id']} · Hab.{ubicacion} · {worker_name}\n"
            f"   {detalle}..."
        )
    
    if len(tickets) > 10:
        lineas.append(f"\n... y {len(tickets) - 10} más")
    
    send_whatsapp(from_phone, "\n".join(lineas))

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
    
    # PRIMERO: Manejar selección pendiente (si hay confirmación esperando)
    if state.get("seleccion_mucamas"):
        seleccion_info = state["seleccion_mucamas"]
        candidatas = seleccion_info["candidatas"]
        ticket_id = seleccion_info["ticket_id"]
        
        mucama_seleccionada = manejar_seleccion_worker(text, candidatas)
        
        # Caso 1: Selección válida
        if mucama_seleccionada and mucama_seleccionada != "CANCEL":
            send_whatsapp(from_phone, texto_ticket_asignado_simple(ticket_id, mucama_seleccionada["nombre_completo"]))
            state.pop("seleccion_mucamas", None)
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
    
    # Si está esperando confirmación (sí/no)
    if state.get("confirmacion_pendiente"):
        conf = state["confirmacion_pendiente"]
        
        if text.lower().strip() in ['sí', 'si', 'yes', 'ok', 'confirmar', 'dale']:
            # Confirmar
            ticket_id = conf["ticket_id"]
            worker = conf["worker"]
            send_whatsapp(from_phone, texto_ticket_asignado_simple(ticket_id, worker["nombre_completo"]))
            state.pop("confirmacion_pendiente", None)
            return True
        elif text.lower().strip() in ['no', 'cancelar', 'nope']:
            send_whatsapp(from_phone, "❌ Asignación cancelada")
            state.pop("confirmacion_pendiente", None)
            return True
        # Si no es sí/no, procesar como nuevo comando
        state.pop("confirmacion_pendiente", None)
    
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
    
    # Caso 1: Asignar ticket existente
    if intent == "asignar_ticket":
        ticket_id = intent_data["ticket_id"]
        worker_nombre = intent_data["worker"]
        worker_nombre = normalizar_nombre(worker_nombre)
        
        # Buscar con sistema inteligente
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
            # Solo una: confirmar
            worker = candidatas[0]
            state["confirmacion_pendiente"] = {
                "tipo": "asignar",
                "ticket_id": ticket_id,
                "worker": worker
            }
            mensaje = formato_lista_workers([worker])
            send_whatsapp(from_phone, mensaje)
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
    
    # Caso 1.5: Reasignar ticket existente (NUEVO)
    if intent == "reasignar_ticket":
        ticket_id = intent_data["ticket_id"]
        worker_nombre = intent_data["worker"]
        worker_nombre = normalizar_nombre(worker_nombre)
        
        # Buscar con sistema inteligente
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
            # Solo una: confirmar reasignación
            worker = candidatas[0]
            worker_nombre_completo = worker.get("nombre_completo", worker.get("nombre"))
            send_whatsapp(
                from_phone,
                f"🔄 Tarea #{ticket_id} reasignada → {worker_nombre_completo}\n\n"
                "💡 En producción: se notificaría al nuevo trabajador"
            )
            return True
        else:
            # Múltiples: pedir que elija
            state["seleccion_mucamas"] = {
                "tipo": "reasignar",
                "ticket_id": ticket_id,
                "candidatas": candidatas
            }
            mensaje = formato_lista_workers(candidatas)
            send_whatsapp(from_phone, mensaje)
            return True
        
    # Caso 2: Crear y asignar
    if intent == "crear_y_asignar":
        habitacion = intent_data["habitacion"]
        detalle = intent_data["detalle"]
        prioridad = intent_data["prioridad"]
        nombre_trabajador = intent_data["worker"]
        
        # 1. Crear el ticket en BD
        from gateway_app.services.tickets_db import crear_ticket, asignar_ticket
        
        try:
            ticket = crear_ticket(
                habitacion=habitacion,
                detalle=detalle,
                prioridad=prioridad,
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
                # ✅ ASIGNACIÓN DIRECTA EN BD
                worker = coincidencias[0]
                worker_phone = worker.get("telefono")
                worker_nombre = worker.get("nombre_completo") or worker.get("username")
                
                # Asignar en BD
                if asignar_ticket(ticket_id, worker_phone, worker_nombre):
                    # Notificar al supervisor
                    send_whatsapp(
                        from_phone,
                        f"✅ Tarea #{ticket_id} creada y asignada\n\n"
                        f"🏨 Habitación: {habitacion}\n"
                        f"📝 Problema: {detalle}\n"
                        f"{prioridad_emoji} Prioridad: {prioridad}\n"
                        f"👤 Asignado a: {worker_nombre}"
                    )
                    
                    # ✅ NOTIFICAR AL TRABAJADOR
                    from gateway_app.services.whatsapp_client import send_whatsapp_text
                    send_whatsapp_text(
                        to=worker_phone,
                        body=f"📋 Nueva tarea asignada\n\n"
                             f"#{ticket_id} · Hab. {habitacion}\n"
                             f"{detalle}\n"
                             f"{prioridad_emoji} Prioridad: {prioridad}\n\n"
                             f"💡 Responde 'tomar' para aceptar"
                    )
                    
                    return True
                else:
                    send_whatsapp(from_phone, "❌ Error asignando. Intenta de nuevo.")
                    return True
            
            elif len(coincidencias) > 1:
                # Múltiples: mostrar opciones
                state["ticket_seleccionado"] = ticket_id
                state["esperando_asignacion"] = True
                
                send_whatsapp(
                    from_phone,
                    f"✅ Tarea #{ticket_id} creada\n\n"
                    f"🏨 Habitación: {habitacion}\n"
                    f"📝 Problema: {detalle}\n"
                    f"{prioridad_emoji} Prioridad: {prioridad}\n\n"
                    f"📋 Encontré {len(coincidencias)} personas con '{nombre_trabajador}':"
                )
                
                from .ticket_assignment import calcular_score_worker
                from .ui_simple import texto_recomendaciones_simple
                from gateway_app.services.workers_db import obtener_todos_workers
                
                all_workers = obtener_todos_workers()
                workers_con_score = []
                for worker in all_workers:
                    score = calcular_score_worker(worker)
                    workers_con_score.append({**worker, "score": score})
                
                workers_con_score.sort(key=lambda w: w["score"], reverse=True)
                mensaje_rec = texto_recomendaciones_simple(workers_con_score)
                send_whatsapp(from_phone, mensaje_rec)
                return True
            
            else:
                # No encontrado: mostrar todos
                state["ticket_seleccionado"] = ticket_id
                state["esperando_asignacion"] = True
                
                send_whatsapp(
                    from_phone,
                    f"✅ Tarea #{ticket_id} creada\n\n"
                    f"🏨 Habitación: {habitacion}\n"
                    f"📝 Problema: {detalle}\n"
                    f"{prioridad_emoji} Prioridad: {prioridad}\n\n"
                    f"⚠️ No encontré a '{nombre_trabajador}'\n"
                    f"Mostrando todas las opciones:"
                )
                
                from .ticket_assignment import calcular_score_worker
                from .ui_simple import texto_recomendaciones_simple
                from gateway_app.services.workers_db import obtener_todos_workers
                
                all_workers = obtener_todos_workers()
                workers_con_score = []
                for worker in all_workers:
                    score = calcular_score_worker(worker)
                    workers_con_score.append({**worker, "score": score})
                
                workers_con_score.sort(key=lambda w: w["score"], reverse=True)
                mensaje_rec = texto_recomendaciones_simple(workers_con_score)
                send_whatsapp(from_phone, mensaje_rec)
                return True
        
        except Exception as e:
            logger.exception(f"❌ Error en crear_y_asignar: {e}")
            send_whatsapp(from_phone, "❌ Error creando tarea. Intenta de nuevo.")
            return True

    # Caso 3: Solo crear
    if intent == "crear_ticket":
        habitacion = intent_data["habitacion"]
        detalle = intent_data["detalle"]
        prioridad = intent_data["prioridad"]
        
        # ✅ GUARDAR EN DB REAL
        from gateway_app.services.tickets_db import crear_ticket
        
        try:
            ticket = crear_ticket(
                habitacion=habitacion,
                detalle=detalle,
                prioridad=prioridad,
                creado_por=from_phone,
                origen="supervisor"
            )
            
            if ticket:
                ticket_id = ticket["id"]
                prioridad_emoji = {"ALTA": "🔴", "MEDIA": "🟡", "BAJA": "🟢"}.get(prioridad, "🟡")
                
                send_whatsapp(
                    from_phone,
                    f"✅ Tarea #{ticket_id} creada\n\n"
                    f"🏨 Habitación: {habitacion}\n"
                    f"📝 Problema: {detalle}\n"
                    f"{prioridad_emoji} Prioridad: {prioridad}\n\n"
                    f"💡 Di 'asignar {ticket_id} a [nombre]'"
                )
                
                # Guardar para asignación rápida
                state["ticket_seleccionado"] = ticket_id
                state["esperando_asignacion"] = True
                
                # Mostrar recomendaciones
                from gateway_app.services.workers_db import buscar_workers_por_nombre

                from .ticket_assignment import calcular_score_worker
                from .ui_simple import texto_recomendaciones_simple
                
                from gateway_app.services.workers_db import obtener_todos_workers
                all_workers = obtener_todos_workers()

                workers_con_score = []
                for worker in all_workers:
                    score = calcular_score_worker(worker)
                    workers_con_score.append({**worker, "score": score})
                
                workers_con_score.sort(key=lambda w: w["score"], reverse=True)
                
                mensaje_rec = texto_recomendaciones_simple(workers_con_score)
                send_whatsapp(from_phone, mensaje_rec)
                
                return True
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
        from gateway_app.services.tickets_db import obtener_tickets_por_estado
        
        worker = buscar_worker_por_nombre(worker_nombre)
        
        if worker:
            tickets = obtener_tickets_por_estado("PENDIENTE")

            if tickets:
                prioridad_order = {"ALTA": 0, "MEDIA": 1, "BAJA": 2}
                tickets_sorted = sorted(
                    tickets,
                    key=lambda t: prioridad_order.get(t.get("prioridad", "MEDIA"), 1)
                )
                ticket_id = tickets_sorted[0]["id"]
                worker_nombre_completo = worker.get("nombre_completo", worker.get("nombre"))
                send_whatsapp(from_phone, texto_ticket_asignado_simple(ticket_id, worker_nombre_completo))
                return True
        else:
            send_whatsapp(from_phone, f"❌ No encontré a '{worker_nombre}'")
            return True
    
    return False