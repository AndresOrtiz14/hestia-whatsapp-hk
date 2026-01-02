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
    raw = (text or "").strip()
    
    # 1) Comando global: Menú
    if es_comando_menu(raw):
        mostrar_menu_principal(from_phone)
        return
    
    # 2) Saludo inicial del día
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