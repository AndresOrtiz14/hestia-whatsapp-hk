"""
Orquestador SIMPLE para supervisión - Sin menú, solo comandos.
"""

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
    raw = (text or "").strip().lower()
    
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
    
    # 5) Comando: Asignar urgente / más urgente / siguiente
    if raw in ["siguiente", "next", "proximo", "urgente", "asignar urgente", "mas urgente", "más urgente"]:
        asignar_siguiente(from_phone)
        return
    
    # 6) Comando: Urgente
    if raw in ["urgente", "urgentes", "critico"]:
        mostrar_urgentes(from_phone)
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
    
    # 8) Comando: Reasignar
    if "reasignar" in raw or "cambiar" in raw:
        # TODO: Implementar reasignación
        send_whatsapp(from_phone, "🔄 Reasignación en desarrollo...")
        return
    
    # 8) Comando: Cancelar (cuando no hay nada que cancelar)
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


def handle_respuesta_asignacion(from_phone: str, text: str) -> bool:
    """
    Maneja la respuesta cuando está esperando asignación.
    
    Args:
        from_phone: Número del supervisor
        text: Respuesta (nombre, número, o cancelar)
    
    Returns:
        True si se manejó la asignación
    """
    from .demo_data import DEMO_WORKERS, get_worker_by_nombre
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
        workers_con_score = []
        for w in DEMO_WORKERS:
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
        worker = get_worker_by_nombre(raw)
    
    # Verificar que se encontró
    if worker:
        confirmar_asignacion(from_phone, ticket_id, worker)
        state["esperando_asignacion"] = False
        state["ticket_seleccionado"] = None
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
    from .demo_data import get_demo_tickets_pendientes
    
    tickets = get_demo_tickets_pendientes()
    
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
    from .demo_data import get_demo_tickets_pendientes, DEMO_WORKERS
    from .ticket_assignment import calcular_score_mucama
    from .ui_simple import texto_recomendaciones_simple
    
    tickets = get_demo_tickets_pendientes()
    
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
    mucamas_con_score = []
    for mucama in DEMO_WORKERS:
        score = calcular_score_mucama(mucama)
        mucamas_con_score.append({**mucama, "score": score})
    
    mucamas_con_score.sort(key=lambda m: m["score"], reverse=True)
    
    mensaje = texto_recomendaciones_simple(mucamas_con_score)
    send_whatsapp(from_phone, mensaje)
    
    # Guardar estado de asignación
    state["esperando_asignacion"] = True


def mostrar_urgentes(from_phone: str) -> None:
    """Muestra solo tickets urgentes."""
    from .demo_data import get_demo_tickets_pendientes, get_demo_tickets_en_progreso
    
    # Pendientes hace >5 min
    pendientes = get_demo_tickets_pendientes()
    pendientes_urgentes = [
        t for t in pendientes 
        if t.get("tiempo_sin_resolver_mins", 0) > 5
    ]
    
    # En progreso hace >10 min
    progreso = get_demo_tickets_en_progreso()
    retrasados = [
        t for t in progreso 
        if t.get("tiempo_sin_resolver_mins", 0) > 10
    ]
    
    mensaje = texto_urgentes(pendientes_urgentes, retrasados)
    send_whatsapp(from_phone, mensaje)


def mostrar_retrasados(from_phone: str) -> None:
    """Muestra solo tickets retrasados (>10 min)."""
    from .demo_data import get_demo_tickets_en_progreso
    
    tickets = get_demo_tickets_en_progreso()
    retrasados = [
        t for t in tickets 
        if t.get("tiempo_sin_resolver_mins", 0) > 10
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
    from .demo_data import get_worker_by_nombre, get_demo_tickets_pendientes, DEMO_WORKERS
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
            worker = conf["mucama"]
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
        worker_nombre = intent_data.get("components", {}).get("mucama") or text.strip()
        worker_nombre = normalizar_nombre(mucama_nombre)
        
        candidatas = buscar_workers(mucama_nombre, DEMO_WORKERS)
        
        if not candidatas:
            send_whatsapp(
                from_phone,
                f"❌ No encontré a '{mucama_nombre}'\n\n"
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
        worker_nombre = intent_data["mucama"]
        worker_nombre = normalizar_nombre(mucama_nombre)
        
        # Buscar con sistema inteligente
        candidatas = buscar_workers(mucama_nombre, DEMO_WORKERS)
        
        if not candidatas:
            send_whatsapp(
                from_phone,
                f"❌ No encontré a '{mucama_nombre}'\n\n"
                "💡 Verifica el nombre"
            )
            return True
        
        if len(candidatas) == 1:
            # Solo una: confirmar
            worker = candidatas[0]
            state["confirmacion_pendiente"] = {
                "tipo": "asignar",
                "ticket_id": ticket_id,
                "mucama": mucama
            }
            mensaje = formato_lista_workers([mucama])
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
    
    # Caso 2: Crear y asignar
    if intent == "crear_y_asignar":
        habitacion = intent_data["habitacion"]
        detalle = intent_data["detalle"]
        prioridad = intent_data["prioridad"]
        worker_nombre = intent_data["mucama"]
        worker = get_worker_by_nombre(mucama_nombre)
        
        if mucama:
            import random
            ticket_id = random.randint(2000, 2999)
            
            send_whatsapp(
                from_phone,
                f"✅ #{ticket_id} creado y asignado a {worker['nombre']}\n"
                f"📋 Hab. {habitacion} · {detalle}"
            )
            return True
    
    # Caso 3: Solo crear
    if intent == "crear_ticket":
        habitacion = intent_data["habitacion"]
        detalle = intent_data["detalle"]
        prioridad = intent_data["prioridad"]
        
        import random
        ticket_id = random.randint(2000, 2999)
        
        mensaje = texto_ticket_creado_simple(ticket_id, habitacion, prioridad)
        send_whatsapp(from_phone, mensaje)
        
        # Guardar para asignación rápida
        state["ticket_seleccionado"] = ticket_id
        state["esperando_asignacion"] = True
        
        # Mostrar recomendaciones inline
        from .demo_data import DEMO_WORKERS
        from .ticket_assignment import calcular_score_mucama
        from .ui_simple import texto_recomendaciones_simple
        
        mucamas_con_score = []
        for mucama in DEMO_WORKERS:
            score = calcular_score_mucama(mucama)
            mucamas_con_score.append({**mucama, "score": score})
        
        mucamas_con_score.sort(key=lambda m: m["score"], reverse=True)
        
        mensaje_rec = texto_recomendaciones_simple(mucamas_con_score)
        send_whatsapp(from_phone, mensaje_rec)
        
        return True
    
    # Caso 4: Asignar sin ticket (usar el de mayor prioridad)
    if intent == "asignar_sin_ticket":
        worker_nombre = intent_data.get("worker")
        
        if not worker_nombre:
            send_whatsapp(from_phone, "❌ No entendí el nombre del trabajador")
            return True
        
        worker = get_worker_by_nombre(worker_nombre)
        
        if worker:
            tickets = get_demo_tickets_pendientes()
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