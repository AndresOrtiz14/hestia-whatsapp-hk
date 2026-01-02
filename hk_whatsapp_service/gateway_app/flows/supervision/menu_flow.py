"""
Manejo del menú principal del supervisor.
"""

from .state import (
    get_supervisor_state,
    MENU_PRINCIPAL,
    VER_PENDIENTES,
    VER_EN_PROGRESO,
    VER_MUCAMAS,
    CREAR_TICKET,
    ESTADISTICAS
)
from .ui import texto_menu_principal, recordatorio_menu
from .outgoing import send_whatsapp


def handle_menu(from_phone: str, text: str) -> None:
    """
    Maneja las interacciones del menú principal.
    
    Args:
        from_phone: Número de teléfono del supervisor
        text: Texto del mensaje recibido
    """
    state = get_supervisor_state(from_phone)
    current_state = state.get("menu_state")
    raw = (text or "").strip().lower()
    
    # Si está en menú principal o es la primera vez
    if current_state == MENU_PRINCIPAL or current_state is None:
        handle_menu_principal(from_phone, raw)
        return
    
    # Si está en ver pendientes
    if current_state == VER_PENDIENTES:
        handle_ver_pendientes(from_phone, raw)
        return
    
    # Si está en ver en progreso
    if current_state == VER_EN_PROGRESO:
        handle_ver_en_progreso(from_phone, raw)
        return
    
    # Si está en ver mucamas
    if current_state == VER_MUCAMAS:
        handle_ver_mucamas(from_phone, raw)
        return
    
    # Si está en estadísticas
    if current_state == ESTADISTICAS:
        handle_estadisticas(from_phone, raw)
        return
    
    # Estado desconocido, volver al menú
    mostrar_menu_principal(from_phone)


def mostrar_menu_principal(from_phone: str) -> None:
    """
    Muestra el menú principal y actualiza el estado.
    
    Args:
        from_phone: Número de teléfono del supervisor
    """
    state = get_supervisor_state(from_phone)
    state["menu_state"] = MENU_PRINCIPAL
    
    # TODO: Obtener contadores reales de tickets
    # Por ahora usamos valores de ejemplo
    tickets_pendientes = 5  # get_tickets_pendientes_count()
    tickets_progreso = 3    # get_tickets_en_progreso_count()
    
    menu = texto_menu_principal(tickets_pendientes, tickets_progreso)
    send_whatsapp(from_phone, menu)


def handle_menu_principal(from_phone: str, raw: str) -> None:
    """
    Maneja la selección del menú principal.
    
    Args:
        from_phone: Número de teléfono del supervisor
        raw: Texto del mensaje (normalizado a minúsculas)
    """
    state = get_supervisor_state(from_phone)
    
    # Opción 1: Ver tickets pendientes
    if raw == "1" or "pendiente" in raw:
        from .monitoring import mostrar_tickets_pendientes
        mostrar_tickets_pendientes(from_phone)
        state["menu_state"] = MENU_PRINCIPAL
        return
    
    # Opción 2: Ver tickets en progreso
    if raw == "2" or "progreso" in raw or "en curso" in raw:
        from .monitoring import mostrar_tickets_en_progreso
        mostrar_tickets_en_progreso(from_phone)
        state["menu_state"] = MENU_PRINCIPAL
        return
    
    # Opción 3: Ver estado de mucamas
    if raw == "3" or "mucama" in raw or "empleado" in raw:
        from .monitoring import mostrar_estado_mucamas
        mostrar_estado_mucamas(from_phone)
        state["menu_state"] = MENU_PRINCIPAL
        return
    
    # Opción 4: Crear ticket manual
    if raw == "4" or "crear" in raw or "nuevo ticket" in raw:
        state["menu_state"] = CREAR_TICKET
        send_whatsapp(
            from_phone,
            "➕ Creación de tickets en desarrollo..." + recordatorio_menu()
        )
        state["menu_state"] = MENU_PRINCIPAL
        return
    
    # Opción 5: Estadísticas
    if raw == "5" or "estadistica" in raw or "stats" in raw:
        from .monitoring import mostrar_estadisticas
        mostrar_estadisticas(from_phone)
        state["menu_state"] = MENU_PRINCIPAL
        return
    
    # Opción no reconocida
    send_whatsapp(
        from_phone,
        "❌ Opción no reconocida.\n\n" + 
        texto_menu_principal(5, 3)  # TODO: contadores reales
    )


def handle_ver_pendientes(from_phone: str, raw: str) -> None:
    """
    Maneja las acciones cuando está viendo tickets pendientes.
    
    Args:
        from_phone: Número de teléfono del supervisor
        raw: Texto del mensaje
    """
    from .monitoring import mostrar_tickets_pendientes
    
    # Mostrar tickets
    mostrar_tickets_pendientes(from_phone)
    
    # Volver al menú (por ahora, en Fase 4 se implementará asignación)
    state = get_supervisor_state(from_phone)
    state["menu_state"] = MENU_PRINCIPAL


def handle_ver_en_progreso(from_phone: str, raw: str) -> None:
    """
    Maneja las acciones cuando está viendo tickets en progreso.
    
    Args:
        from_phone: Número de teléfono del supervisor
        raw: Texto del mensaje
    """
    from .monitoring import mostrar_tickets_en_progreso
    
    # Mostrar tickets
    mostrar_tickets_en_progreso(from_phone)
    
    # Volver al menú
    state = get_supervisor_state(from_phone)
    state["menu_state"] = MENU_PRINCIPAL


def handle_ver_mucamas(from_phone: str, raw: str) -> None:
    """
    Maneja las acciones cuando está viendo estado de mucamas.
    
    Args:
        from_phone: Número de teléfono del supervisor
        raw: Texto del mensaje
    """
    from .monitoring import mostrar_estado_mucamas
    
    # Mostrar mucamas
    mostrar_estado_mucamas(from_phone)
    
    # Volver al menú
    state = get_supervisor_state(from_phone)
    state["menu_state"] = MENU_PRINCIPAL


def handle_estadisticas(from_phone: str, raw: str) -> None:
    """
    Maneja las acciones cuando está viendo estadísticas.
    
    Args:
        from_phone: Número de teléfono del supervisor
        raw: Texto del mensaje
    """
    from .monitoring import mostrar_estadisticas
    
    # Mostrar estadísticas
    mostrar_estadisticas(from_phone)
    
    # Volver al menú
    state = get_supervisor_state(from_phone)
    state["menu_state"] = MENU_PRINCIPAL


def es_comando_menu(text: str) -> bool:
    """
    Detecta si el texto es un comando para volver al menú.
    
    Args:
        text: Texto del mensaje
    
    Returns:
        True si es comando de menú
    """
    if not text:
        return False
    
    raw = text.strip().lower()
    
    # Comandos de menú
    return raw in ["m", "menu", "menú", "volver"]