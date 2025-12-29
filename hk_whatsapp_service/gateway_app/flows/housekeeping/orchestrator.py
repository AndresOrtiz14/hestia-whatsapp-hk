"""
Orquestador principal del flujo de Housekeeping.
Punto de entrada único para todos los mensajes entrantes.
"""

from datetime import date, datetime
from typing import Dict, Any, Optional

from .state import get_user_state
from .outgoing import send_whatsapp
from .ui import texto_menu_principal
from .menu_flow import handle_menu
from .ticket_flow import _handle_ticket_flow
from .reminders import maybe_send_recordatorio_pendientes

def maybe_route_ticket_command_anywhere(phone: str, text: str, state: Dict[str, Any]) -> bool:
    """
    Permite manejar comandos del ticket activo desde cualquier parte del flujo.
    
    Si hay ticket_activo Y fue aceptado (tiene started_at), permite comandos 
    tipo 'fin/pausar/reanudar/supervisor' desde cualquier parte.
    
    Returns:
        True si el comando fue manejado, False en caso contrario.
    """
    ticket = state.get("ticket_activo")
    
    # Solo permitir comandos si el ticket fue realmente aceptado (tiene started_at)
    if ticket is None or ticket.get("started_at") is None:
        return False

    t = (text or "").strip().lower()
    if t in {"fin", "terminar", "cerrar", "finalizar", "completar", "listo", "hecho", "pausar", "reanudar", "supervisor"}:
        # Aseguramos que el ticket_flow lo procese como ejecución (S1)
        state["ticket_state"] = "S1"
        _handle_ticket_flow(phone, text, state)
        return True

    return False


def handle_hk_message(from_phone: str, text: str) -> None:
    """
    Punto de entrada único para:
    - Simulador CLI
    - Webhook (producción)

    Orquesta:
    - Saludo 1 vez al día
    - Ticket flow (S0/S1/S2) si hay ticket activo
    - Menú (M0/M1/M2/M3) si no hay ticket activo
    - Recordatorios opcionales
    
    Args:
        from_phone: Número de teléfono de la mucama
        text: Texto del mensaje recibido
    """
    state = get_user_state(from_phone)
    raw = (text or "").strip()

    # 0) Comandos globales del ticket activo (desde cualquier parte)
    if maybe_route_ticket_command_anywhere(from_phone, raw, state):
        return

    today_str = date.today().isoformat()

    # Saludo solo si NO hay ticket activo (ni conversacional ni en ejecución)
    if (
        state.get("ticket_state") is None
        and state.get("ticket_activo") is None
        and state.get("last_greet_date") != today_str
    ):
        state["last_greet_date"] = today_str
        send_whatsapp(
            from_phone,
            "Hola, soy el asistente de Housekeeping de Hestia.\n"
            "Te ayudaré a organizar y resolver tus tareas de hoy.\n\n"
            + texto_menu_principal(state)
        )
        return

    # 1) Si hay un flujo de ticket activo, tiene prioridad
    if state.get("ticket_state") is not None:
        _handle_ticket_flow(from_phone, raw, state)
        return

    # 2) Si no hay ticket activo, manejamos menú
    handle_menu(from_phone, raw, state)

    # 3) Recordatorio opcional (solo aplica si corresponde)
    # No enviar recordatorio si acabamos de iniciar turno
    if not state.get("_just_started_shift"):
        maybe_send_recordatorio_pendientes(from_phone, state)
    
    # Limpiar flag temporal después de usarlo
    if state.get("_just_started_shift"):
        state["_just_started_shift"] = False


# Alias por compatibilidad (por si algún módulo aún usa este nombre)
_handle_hk_message = handle_hk_message


# =========================
#   NOTIFICACIONES PUSH
# =========================

def notify_new_ticket(
    phone: str,
    ticket_data: Dict[str, Any],
    auto_start_shift: bool = True
) -> Dict[str, Any]:
    """
    Notifica a una mucama sobre un ticket nuevo asignado automáticamente (flujo PUSH).
    
    Este es el flujo PUSH: el ticket viene del sistema backend (creado por un huésped)
    y se notifica directamente a la mucama asignada, entrando en estado S1 automáticamente.
    
    Args:
        phone: Número de teléfono de la mucama asignada
        ticket_data: Diccionario con datos del ticket:
            {
                "id": int,                    # ID del ticket (requerido)
                "room": str,                  # Número de habitación (requerido)
                "detalle": str,               # Descripción del problema (requerido)
                "prioridad": str,             # "ALTA"|"MEDIA"|"BAJA" (opcional, default: "MEDIA")
                "created_at": datetime,       # Fecha de creación (opcional)
                "guest_name": str,            # Nombre del huésped (opcional)
                "esfuerzo": str               # "FACIL"|"MEDIO"|"DIFICIL" (opcional)
            }
        auto_start_shift: Si True, inicia automáticamente el turno si no está activo
    
    Returns:
        Dict con resultado de la operación:
        {
            "success": bool,
            "ticket_id": int,
            "action": str,              # "assigned" | "queued" | "rejected"
            "message": str,             # Mensaje descriptivo
            "current_ticket_id": int    # Si fue rechazado, ID del ticket actual
        }
    
    Example:
        >>> ticket = {
        ...     "id": 2050,
        ...     "room": "405",
        ...     "detalle": "Necesito toallas limpias",
        ...     "prioridad": "ALTA",
        ...     "guest_name": "Juan Pérez"
        ... }
        >>> result = notify_new_ticket("56912345678", ticket)
        >>> print(result)
        {"success": True, "ticket_id": 2050, "action": "assigned"}
    """
    state = get_user_state(phone)
    
    # Validar datos mínimos requeridos
    if not all(k in ticket_data for k in ["id", "room", "detalle"]):
        return {
            "success": False,
            "ticket_id": ticket_data.get("id"),
            "action": "rejected",
            "message": "Datos de ticket incompletos (requiere: id, room, detalle)"
        }
    
    # ====================================
    # EDGE CASE 1: Mucama ya tiene ticket activo
    # ====================================
    existing_ticket = state.get("ticket_activo")
    
    if existing_ticket is not None:
        # Verificar si el ticket está realmente en ejecución (tiene started_at)
        if existing_ticket.get("started_at") is not None:
            # Opción A: Encolar para después
            pending = state.setdefault("pending_tickets", [])
            pending.append(ticket_data)
            
            send_whatsapp(
                phone,
                f"⏳ TICKET EN ESPERA\n\n"
                f"Ticket #{ticket_data['id']} · Hab. {ticket_data['room']}\n"
                f"Solicitud: {ticket_data['detalle']}\n\n"
                f"Actualmente estás trabajando en el ticket #{existing_ticket.get('id')}.\n"
                f"Este nuevo ticket se asignará automáticamente cuando termines el actual."
            )
            
            return {
                "success": True,
                "ticket_id": ticket_data["id"],
                "action": "queued",
                "message": f"Ticket encolado (mucama ocupada con ticket #{existing_ticket.get('id')})",
                "current_ticket_id": existing_ticket.get("id"),
                "queue_position": len(pending)
            }
    
    # ====================================
    # EDGE CASE 2: Auto-iniciar turno si está inactivo
    # ====================================
    turno_iniciado = False
    if not state["turno_activo"] and auto_start_shift:
        state["turno_activo"] = True
        state["menu_state"] = "M1"
        turno_iniciado = True
    
    # ====================================
    # ASIGNAR TICKET (Estado S1 - Ejecución directa)
    # ====================================
    state["ticket_state"] = "S1"
    state["ticket_activo"] = {
        "id": ticket_data["id"],
        "room": ticket_data["room"],
        "detalle": ticket_data["detalle"],
        "prioridad": ticket_data.get("prioridad", "MEDIA"),
        "paused": False,
        "started_at": datetime.now(),
        "auto_assigned": True,  # Flag para saber que fue PUSH
        "guest_name": ticket_data.get("guest_name"),
        "esfuerzo": ticket_data.get("esfuerzo"),
    }
    
    # ====================================
    # CONSTRUIR MENSAJE DE NOTIFICACIÓN
    # ====================================
    
    # Emoji según prioridad
    prioridad = ticket_data.get("prioridad", "MEDIA").upper()
    prioridad_emoji = {
        "ALTA": "🔴",
        "MEDIA": "🟡",
        "BAJA": "🟢"
    }.get(prioridad, "🟡")
    
    # Información del huésped (opcional)
    guest_info = ""
    if ticket_data.get("guest_name"):
        guest_info = f"Huésped: {ticket_data['guest_name']}\n"
    
    # Mensaje de auto-inicio de turno (si aplicó)
    turno_msg = ""
    if turno_iniciado:
        turno_msg = "🔄 He iniciado tu turno automáticamente.\n\n"
    
    # Mensaje principal
    mensaje = (
        f"{turno_msg}"
        f"🔔 NUEVO TICKET ASIGNADO {prioridad_emoji}\n\n"
        f"Ticket #{ticket_data['id']} · Hab. {ticket_data['room']}\n"
        f"{guest_info}"
        f"Solicitud: {ticket_data['detalle']}\n"
        f"Prioridad: {prioridad}\n\n"
        f"Este ticket ha sido asignado automáticamente.\n"
        f"Puedes gestionarlo con:\n"
        f"• 'pausar' - Pausar temporalmente\n"
        f"• 'fin' / 'finalizar' / 'listo' - Marcar como completado\n"
        f"• 'supervisor' - Pedir ayuda\n"
        f"• 'M' - Ver menú completo"
    )
    
    send_whatsapp(phone, mensaje)
    
    return {
        "success": True,
        "ticket_id": ticket_data["id"],
        "action": "assigned",
        "message": f"Ticket #{ticket_data['id']} asignado correctamente a {phone}",
        "auto_started_shift": turno_iniciado
    }


def check_and_assign_pending_tickets(phone: str) -> Optional[Dict[str, Any]]:
    """
    Verifica si hay tickets pendientes en cola y asigna el siguiente automáticamente.
    
    Esta función debe llamarse después de que una mucama finaliza un ticket,
    para asignarle automáticamente el siguiente de su cola si existe.
    
    Args:
        phone: Número de teléfono de la mucama
    
    Returns:
        Dict con info del ticket asignado, o None si no hay tickets pendientes
    """
    state = get_user_state(phone)
    pending = state.get("pending_tickets", [])
    
    if not pending:
        return None
    
    # Tomar el primer ticket de la cola
    next_ticket = pending.pop(0)
    state["pending_tickets"] = pending
    
    # Asignar automáticamente
    result = notify_new_ticket(phone, next_ticket, auto_start_shift=False)
    
    return result