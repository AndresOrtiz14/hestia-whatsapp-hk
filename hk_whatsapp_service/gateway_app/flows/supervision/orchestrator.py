"""
Orquestador principal del bot de Supervisión.
Punto de entrada único que coordina todos los flujos.
"""

from datetime import date
from .state import (
    get_supervisor_state,
    MENU_PRINCIPAL,
    VER_PENDIENTES,
    VER_EN_PROGRESO,
    VER_MUCAMAS,
    CREAR_TICKET,
    ESTADISTICAS,
    ASIGNAR_ELIGIENDO_MUCAMA,
    ASIGNAR_CONFIRMANDO,
    CREAR_INGRESANDO_DETALLE,
    CREAR_CONFIRMANDO,
    CREAR_ELIGIENDO_PRIORIDAD,
    CREAR_ELIGIENDO_ASIGNACION
)
from .menu_flow import (
    handle_menu,
    mostrar_menu_principal,
    es_comando_menu
)
from .ui import texto_menu_principal
from .outgoing import send_whatsapp


def maybe_handle_global_navigation(from_phone: str, raw: str) -> bool:
    """
    Detecta y maneja comandos de navegación global.
    Permite ir directamente a cualquier sección desde cualquier parte.
    
    Args:
        from_phone: Número de teléfono del supervisor
        raw: Texto del mensaje (ya en minúsculas)
    
    Returns:
        True si se manejó un comando de navegación
    """
    state = get_supervisor_state(from_phone)
    
    # Comando: Ver pendientes
    if raw in ["1", "pendientes", "pendiente"]:
        from .monitoring import mostrar_tickets_pendientes
        mostrar_tickets_pendientes(from_phone)
        state["menu_state"] = VER_PENDIENTES
        return True
    
    # Comando: Ver en progreso
    if raw in ["2", "progreso", "en progreso", "en curso"]:
        from .monitoring import mostrar_tickets_en_progreso
        mostrar_tickets_en_progreso(from_phone)
        state["menu_state"] = VER_EN_PROGRESO
        return True
    
    # Comando: Ver mucamas
    if raw in ["3", "mucamas", "mucama", "empleados"]:
        from .monitoring import mostrar_estado_mucamas
        mostrar_estado_mucamas(from_phone)
        state["menu_state"] = VER_MUCAMAS
        return True
    
    # Comando: Crear ticket
    if raw in ["4", "crear", "nuevo"]:
        send_whatsapp(
            from_phone,
            "➕ Creación de tickets en desarrollo...\n\n"
            "Por ahora, usa las otras opciones del menú."
        )
        mostrar_menu_principal(from_phone)
        return True
    
    # Comando: Estadísticas
    if raw in ["5", "stats", "estadisticas", "estadística"]:
        from .monitoring import mostrar_estadisticas
        mostrar_estadisticas(from_phone)
        state["menu_state"] = ESTADISTICAS
        return True
    
    return False


def maybe_handle_audio_command(from_phone: str, text: str) -> bool:
    """
    Detecta y maneja comandos dados por audio.
    
    Args:
        from_phone: Número de teléfono del supervisor
        text: Texto transcrito del audio
    
    Returns:
        True si se manejó un comando de audio
    """
    from .audio_commands import detect_audio_intent
    from .ticket_assignment import iniciar_asignacion, confirmar_asignacion
    from .demo_data import get_mucama_by_nombre, get_demo_tickets_pendientes
    from .ui import recordatorio_menu
    
    # Detectar intención
    intent_data = detect_audio_intent(text)
    intent = intent_data.get("intent")
    
    # Caso 1: Asignar ticket existente
    if intent == "asignar_ticket":
        ticket_id = intent_data["ticket_id"]
        mucama_nombre = intent_data["mucama"]
        
        mucama = get_mucama_by_nombre(mucama_nombre)
        if mucama:
            confirmar_asignacion(from_phone, ticket_id, mucama)
            return True
        else:
            send_whatsapp(
                from_phone,
                f"❌ No encontré a la mucama '{mucama_nombre}'" +
                recordatorio_menu()
            )
            return True
    
    # Caso 2: Crear ticket y asignar
    if intent == "crear_y_asignar":
        habitacion = intent_data["habitacion"]
        detalle = intent_data["detalle"]
        prioridad = intent_data["prioridad"]
        mucama_nombre = intent_data["mucama"]
        
        mucama = get_mucama_by_nombre(mucama_nombre)
        if not mucama:
            send_whatsapp(
                from_phone,
                f"❌ No encontré a la mucama '{mucama_nombre}'" +
                recordatorio_menu()
            )
            return True
        
        # Simular creación de ticket (en producción sería en BD)
        import random
        ticket_id = random.randint(2000, 2999)
        
        send_whatsapp(
            from_phone,
            f"✅ Ticket #{ticket_id} creado\n"
            f"📋 Hab. {habitacion} - {detalle}\n"
            f"Prioridad: {prioridad}\n\n"
            f"Asignando a {mucama['nombre']}..."
        )
        
        # Asignar
        from .ui import mensaje_ticket_asignado
        mensaje = mensaje_ticket_asignado(ticket_id, mucama["nombre"])
        mensaje += "\n\n💡 En producción: ticket guardado en BD"
        mensaje += recordatorio_menu()
        send_whatsapp(from_phone, mensaje)
        
        return True
    
    # Caso 3: Solo crear ticket
    if intent == "crear_ticket":
        habitacion = intent_data["habitacion"]
        detalle = intent_data["detalle"]
        prioridad = intent_data["prioridad"]
        
        import random
        ticket_id = random.randint(2000, 2999)
        
        send_whatsapp(
            from_phone,
            f"✅ Ticket #{ticket_id} creado\n"
            f"📋 Hab. {habitacion} - {detalle}\n"
            f"Prioridad: {prioridad}\n\n"
            f"¿Asignar ahora?\n"
            f"• Escribe 'asignar' para elegir mucama\n"
            f"• O di: 'asignar a [nombre]'" +
            recordatorio_menu()
        )
        
        # Guardar ticket en estado para asignación rápida
        state = get_supervisor_state(from_phone)
        state["ticket_seleccionado"] = ticket_id
        
        return True
    
    # Caso 4: Asignar sin especificar ticket (usar el de mayor prioridad)
    if intent == "asignar_sin_ticket":
        mucama_nombre = intent_data["mucama"]
        mucama = get_mucama_by_nombre(mucama_nombre)
        
        if not mucama:
            send_whatsapp(
                from_phone,
                f"❌ No encontré a la mucama '{mucama_nombre}'" +
                recordatorio_menu()
            )
            return True
        
        # Buscar ticket de mayor prioridad
        tickets = get_demo_tickets_pendientes()
        if tickets:
            prioridad_order = {"ALTA": 0, "MEDIA": 1, "BAJA": 2}
            tickets_sorted = sorted(
                tickets,
                key=lambda t: prioridad_order.get(t.get("prioridad", "MEDIA"), 1)
            )
            ticket_id = tickets_sorted[0]["id"]
            
            confirmar_asignacion(from_phone, ticket_id, mucama)
            return True
        else:
            send_whatsapp(
                from_phone,
                "❌ No hay tickets pendientes" + recordatorio_menu()
            )
            return True
    
    # Caso 5: Ver estado
    if intent in ["ver_pendientes", "ver_progreso", "ver_mucamas"]:
        from .monitoring import (
            mostrar_tickets_pendientes,
            mostrar_tickets_en_progreso,
            mostrar_estado_mucamas
        )
        
        state = get_supervisor_state(from_phone)
        
        if intent == "ver_pendientes":
            mostrar_tickets_pendientes(from_phone)
            state["menu_state"] = VER_PENDIENTES
        elif intent == "ver_progreso":
            mostrar_tickets_en_progreso(from_phone)
            state["menu_state"] = VER_EN_PROGRESO
        elif intent == "ver_mucamas":
            mostrar_estado_mucamas(from_phone)
            state["menu_state"] = VER_MUCAMAS
        
        return True
    
    # No se reconoció comando de audio
    return False


def handle_supervisor_message(from_phone: str, text: str) -> None:
    """
    Punto de entrada principal para mensajes del supervisor.
    
    Orquesta:
    - Saludo inicial (1 vez al día)
    - Comandos globales (menú, asignar, crear)
    - Flujo de menú
    - Flujo de asignación
    - Flujo de creación de tickets
    
    Args:
        from_phone: Número de teléfono del supervisor
        text: Texto del mensaje recibido
    """
    state = get_supervisor_state(from_phone)
    raw = (text or "").strip().lower()  # Normalizar a minúsculas
    
    # 1) Comando global: Menú
    if es_comando_menu(raw):
        mostrar_menu_principal(from_phone)
        return
    
    # 2) Comandos globales de navegación directa
    if maybe_handle_global_navigation(from_phone, raw):
        return
    
    # 2.5) Detectar comandos de audio (asignar, crear con voz)
    if maybe_handle_audio_command(from_phone, text):
        return
    
    # 3) Saludo inicial del día
    today_str = date.today().isoformat()
    current_state = state.get("menu_state")
    
    if state.get("last_greet_date") != today_str and current_state is None:
        state["last_greet_date"] = today_str
        send_whatsapp(
            from_phone,
            "👋 Hola, soy el asistente de Supervisión de Hestia.\n"
            "Te ayudaré a coordinar y asignar tickets de housekeeping.\n\n" +
            texto_menu_principal(5, 3)  # TODO: contadores reales
        )
        state["menu_state"] = MENU_PRINCIPAL
        return
    
    # 3) Routing por estado actual (ANTES de detectar IDs)
    
    # Estados de menú (M0-M5)
    if current_state in [
        MENU_PRINCIPAL,
        VER_PENDIENTES,
        VER_EN_PROGRESO,
        VER_MUCAMAS,
        ESTADISTICAS
    ]:
        handle_menu(from_phone, raw)
        return
    
    # Estados de creación de ticket (C0-C3)
    if current_state in [
        CREAR_TICKET,
        CREAR_INGRESANDO_DETALLE,
        CREAR_CONFIRMANDO,
        CREAR_ELIGIENDO_PRIORIDAD,
        CREAR_ELIGIENDO_ASIGNACION
    ]:
        # TODO: Implementar en Fase 3
        handle_ticket_creation_flow(from_phone, raw)
        return
    
    # Estados de asignación (A0-A2)
    if current_state in [
        ASIGNAR_ELIGIENDO_MUCAMA,
        ASIGNAR_CONFIRMANDO
    ]:
        # TODO: Implementar en Fase 3
        handle_ticket_assignment_flow(from_phone, raw)
        return
    
    # 4) Comando global: Ver ID de ticket específico (solo si no está en menú)
    if maybe_handle_ticket_id(from_phone, raw):
        return
    
    # Estado desconocido o primera interacción
    mostrar_menu_principal(from_phone)


def maybe_handle_ticket_id(from_phone: str, text: str) -> bool:
    """
    Detecta y maneja si el usuario escribió un ID de ticket.
    
    Args:
        from_phone: Número de teléfono del supervisor
        text: Texto del mensaje
    
    Returns:
        True si se manejó un ID de ticket
    """
    if not text:
        return False
    
    raw = text.strip().lower()
    
    # Detectar formato #1234 o 1234
    if raw.startswith("#"):
        raw = raw[1:]
    
    # Verificar si es número
    if raw.isdigit():
        ticket_id = int(raw)
        
        # Buscar ticket
        from .demo_data import get_ticket_by_id
        ticket = get_ticket_by_id(ticket_id)
        
        if not ticket:
            send_whatsapp(
                from_phone,
                f"❌ No encontré el ticket #{ticket_id}\n\n"
                "Verifica el número e intenta de nuevo."
            )
            from .menu_flow import mostrar_menu_principal
            mostrar_menu_principal(from_phone)
            return True
        
        # Mostrar detalles del ticket
        from .ui import formato_ticket_detallado, recordatorio_menu
        
        # Determinar si mostrar versión simple o detallada
        tiempo = ticket.get("tiempo_sin_resolver_mins", 0)
        if tiempo > 10:
            mensaje = formato_ticket_detallado(ticket)
        else:
            from .ui import formato_ticket_simple
            prioridad_emoji = {"ALTA": "🔴", "MEDIA": "🟡", "BAJA": "🟢"}.get(
                ticket.get("prioridad", "MEDIA"), "🟡"
            )
            
            mensaje = f"""📋 Detalles del Ticket

{formato_ticket_simple(ticket)}

Estado: {ticket.get('estado', 'desconocido')}
Origen: {ticket.get('origen', 'desconocido')}"""
            
            # Si está asignado, mostrar a quién
            if ticket.get("asignado_a_nombre"):
                mensaje += f"\nAsignado a: {ticket['asignado_a_nombre']}"
        
        mensaje += recordatorio_menu()
        send_whatsapp(from_phone, mensaje)
        
        # Volver al menú
        from .menu_flow import mostrar_menu_principal
        mostrar_menu_principal(from_phone)
        return True
    
    return False


def handle_ticket_creation_flow(from_phone: str, text: str) -> None:
    """
    Maneja el flujo de creación de tickets.
    
    Args:
        from_phone: Número de teléfono del supervisor
        text: Texto del mensaje
    """
    # TODO: Implementar en Fase 3 con ticket_creation.py
    send_whatsapp(
        from_phone,
        "📝 Creación de tickets en desarrollo...\n\n"
        "Por ahora, usa el menú para otras opciones."
    )
    mostrar_menu_principal(from_phone)


def handle_ticket_assignment_flow(from_phone: str, text: str) -> None:
    """
    Maneja el flujo de asignación de tickets.
    
    Args:
        from_phone: Número de teléfono del supervisor
        text: Texto del mensaje
    """
    from .ticket_assignment import handle_seleccion_mucama
    
    # Manejar selección de mucama
    handle_seleccion_mucama(from_phone, text)


# Función de notificación para cuando llega ticket de huésped
def notify_new_ticket_from_guest(supervisor_phone: str, ticket: dict) -> None:
    """
    Notifica al supervisor cuando llega un nuevo ticket de huésped.
    
    Args:
        supervisor_phone: Número de teléfono del supervisor
        ticket: Datos del ticket
    """
    from .ui import mensaje_nuevo_ticket_huesped
    
    mensaje = mensaje_nuevo_ticket_huesped(ticket)
    send_whatsapp(supervisor_phone, mensaje)


# Función de notificación para cuando mucama completa ticket
def notify_ticket_completed(supervisor_phone: str, ticket: dict) -> None:
    """
    Notifica al supervisor cuando una mucama completa un ticket.
    
    Args:
        supervisor_phone: Número de teléfono del supervisor
        ticket: Datos del ticket
    """
    from .ui import mensaje_ticket_completado
    
    mensaje = mensaje_ticket_completado(ticket)
    send_whatsapp(supervisor_phone, mensaje)


# Función de notificación para tickets retrasados
def notify_ticket_delayed(supervisor_phone: str, ticket: dict) -> None:
    """
    Notifica al supervisor cuando un ticket lleva >10 min sin resolver.
    
    Args:
        supervisor_phone: Número de teléfono del supervisor
        ticket: Datos del ticket
    """
    from .ui import mensaje_ticket_retrasado
    
    mensaje = mensaje_ticket_retrasado(ticket)
    send_whatsapp(supervisor_phone, mensaje)