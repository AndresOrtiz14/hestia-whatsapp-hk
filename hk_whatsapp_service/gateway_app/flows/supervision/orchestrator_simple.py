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
    
    # 2) Comandos de audio (asignar, crear)
    if maybe_handle_audio_command_simple(from_phone, text):
        return
    
    # 3) Comando: Ver pendientes
    if raw in ["pendientes", "pendiente", "ver", "lista"]:
        mostrar_pendientes_simple(from_phone)
        return
    
    # 4) Comando: Asignar urgente / más urgente / siguiente
    if raw in ["siguiente", "next", "proximo", "urgente", "asignar urgente", "mas urgente", "más urgente"]:
        asignar_siguiente(from_phone)
        return
    
    # 5) Comando: Urgente
    if raw in ["urgente", "urgentes", "critico"]:
        mostrar_urgentes(from_phone)
        return
    
    # 6) Comando: Retrasados
    if raw in ["retrasados", "retrasado", "atrasados"]:
        mostrar_retrasados(from_phone)
        return
    
    # 7) Comando: Reasignar
    if "reasignar" in raw or "cambiar" in raw:
        # TODO: Implementar reasignación
        send_whatsapp(from_phone, "🔄 Reasignación en desarrollo...")
        return
    
    # 8) No entendí - dar sugerencias
    send_whatsapp(
        from_phone,
        "🤔 No entendí.\n\n"
        "💡 Puedes decir:\n"
        "• 'pendientes' - ver todos\n"
        "• 'más urgente' - asignar el más importante\n"
        "• 'urgente' - ver solo urgentes\n"
        "• 'asignar [#] a [nombre]'\n"
        "• 'hab [#] [detalle]'"
    )


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
    from .demo_data import get_demo_tickets_pendientes, DEMO_MUCAMAS
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
    for mucama in DEMO_MUCAMAS:
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
    from .demo_data import get_mucama_by_nombre, get_demo_tickets_pendientes
    from .ui_simple import texto_ticket_asignado_simple, texto_ticket_creado_simple
    
    # Detectar intención
    intent_data = detect_audio_intent(text)
    intent = intent_data.get("intent")
    state = get_supervisor_state(from_phone)
    
    # Si está esperando asignación y dice un nombre
    if state.get("esperando_asignacion"):
        mucama_nombre = intent_data.get("components", {}).get("mucama") or text.strip()
        mucama = get_mucama_by_nombre(mucama_nombre)
        
        if mucama:
            ticket_id = state.get("ticket_seleccionado")
            if ticket_id:
                # Asignar
                send_whatsapp(from_phone, texto_ticket_asignado_simple(ticket_id, mucama["nombre"]))
                # Limpiar estado
                state["esperando_asignacion"] = False
                state["ticket_seleccionado"] = None
                return True
    
    # Caso 1: Asignar ticket existente
    if intent == "asignar_ticket":
        ticket_id = intent_data["ticket_id"]
        mucama_nombre = intent_data["mucama"]
        mucama = get_mucama_by_nombre(mucama_nombre)
        
        if mucama:
            send_whatsapp(from_phone, texto_ticket_asignado_simple(ticket_id, mucama["nombre"]))
            return True
    
    # Caso 2: Crear y asignar
    if intent == "crear_y_asignar":
        habitacion = intent_data["habitacion"]
        detalle = intent_data["detalle"]
        prioridad = intent_data["prioridad"]
        mucama_nombre = intent_data["mucama"]
        mucama = get_mucama_by_nombre(mucama_nombre)
        
        if mucama:
            import random
            ticket_id = random.randint(2000, 2999)
            
            send_whatsapp(
                from_phone,
                f"✅ #{ticket_id} creado y asignado a {mucama['nombre']}\n"
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
        from .demo_data import DEMO_MUCAMAS
        from .ticket_assignment import calcular_score_mucama
        from .ui_simple import texto_recomendaciones_simple
        
        mucamas_con_score = []
        for mucama in DEMO_MUCAMAS:
            score = calcular_score_mucama(mucama)
            mucamas_con_score.append({**mucama, "score": score})
        
        mucamas_con_score.sort(key=lambda m: m["score"], reverse=True)
        
        mensaje_rec = texto_recomendaciones_simple(mucamas_con_score)
        send_whatsapp(from_phone, mensaje_rec)
        
        return True
    
    # Caso 4: Asignar sin ticket (usar el de mayor prioridad)
    if intent == "asignar_sin_ticket":
        mucama_nombre = intent_data["mucama"]
        mucama = get_mucama_by_nombre(mucama_nombre)
        
        if mucama:
            tickets = get_demo_tickets_pendientes()
            if tickets:
                prioridad_order = {"ALTA": 0, "MEDIA": 1, "BAJA": 2}
                tickets_sorted = sorted(
                    tickets,
                    key=lambda t: prioridad_order.get(t.get("prioridad", "MEDIA"), 1)
                )
                ticket_id = tickets_sorted[0]["id"]
                send_whatsapp(from_phone, texto_ticket_asignado_simple(ticket_id, mucama["nombre"]))
                return True
    
    return False