# gateway_app/flows/housekeeping/media_handler.py
"""
Manejo de medios (fotos/videos) enviados por trabajadores Y supervisores.
VERSIÓN CORREGIDA: Usa el estado correcto según el rol del usuario.
"""

import logging
import re
import os
from typing import Optional, Dict, Any, Callable

logger = logging.getLogger(__name__)

# ============================================================
# HELPER: Detectar rol y obtener funciones de estado correctas
# ============================================================

def _get_state_functions(phone: str) -> tuple:
    """
    Retorna las funciones de estado correctas según el rol del usuario.
    
    Returns:
        (get_state_func, persist_state_func, is_supervisor)
    """
    supervisor_phones_str = os.getenv("SUPERVISOR_PHONES", "")
    supervisor_phones = [p.strip() for p in supervisor_phones_str.split(",") if p.strip()]
    
    is_supervisor = phone in supervisor_phones
    
    if is_supervisor:
        from gateway_app.flows.supervision.state import (
            get_supervisor_state,
            persist_supervisor_state
        )
        return get_supervisor_state, persist_supervisor_state, True
    else:
        from gateway_app.flows.housekeeping.state_simple import (
            get_user_state,
            persist_user_state
        )
        return get_user_state, persist_user_state, False


def _get_send_function(phone: str):
    """Retorna la función de envío correcta."""
    # Ambos usan el mismo cliente de WhatsApp
    from gateway_app.flows.housekeeping.outgoing import send_whatsapp
    return send_whatsapp


# ============================================================
# HANDLER PRINCIPAL
# ============================================================

def handle_media_message(
    from_phone: str,
    media_id: str,
    media_type: str,  # "image" o "video"
    caption: Optional[str] = None
) -> None:
    """
    Punto de entrada para mensajes con media.
    Funciona tanto para workers como supervisores.
    """
    get_state, persist_state, is_supervisor = _get_state_functions(from_phone)
    send_whatsapp = _get_send_function(from_phone)
    
    state = get_state(from_phone)
    caption_text = (caption or "").strip()
    caption_lower = caption_text.lower()
    
    rol_str = "SUP" if is_supervisor else "HK"
    logger.info(f"📸 {rol_str} | {from_phone} | Media: {media_type} | Caption: '{caption_text[:50] if caption_text else '(sin caption)'}'")
    
    # ─────────────────────────────────────────────────────────────
    # CASO 1: Hay un flujo de media pendiente esperando ubicación
    # ─────────────────────────────────────────────────────────────
    if state.get("media_pendiente"):
        logger.info(f"📸 {rol_str} | Reemplazando media pendiente anterior")
        state["media_pendiente"] = {
            "media_id": media_id,
            "media_type": media_type,
        }
        persist_state(from_phone, state)
        
        send_whatsapp(
            from_phone,
            f"📸 Nueva {'foto' if media_type == 'image' else 'video'} recibida.\n\n"
            "¿Dónde es el problema?\n"
            "• Número de habitación (ej: '305')\n"
            "• Área común (ej: 'Ascensor piso 2')\n"
            "• O 'foto [#]' para agregar a ticket existente"
        )
        return
    
    # ─────────────────────────────────────────────────────────────
    # CASO 2: Caption con "foto 123" → agregar a ticket existente
    # ─────────────────────────────────────────────────────────────
    ticket_match = re.search(r'(?:foto|video|adjuntar|agregar)\s*#?(\d+)', caption_lower)
    if ticket_match:
        ticket_id = int(ticket_match.group(1))
        _agregar_media_a_ticket(from_phone, media_id, media_type, ticket_id)
        return
    
    # ─────────────────────────────────────────────────────────────
    # CASO 3: Caption con ubicación → crear ticket con media
    # ─────────────────────────────────────────────────────────────
    if caption_text:
        ubicacion = _extraer_ubicacion(caption_text)
        
        if ubicacion:
            _crear_ticket_con_media(
                from_phone=from_phone,
                media_id=media_id,
                media_type=media_type,
                ubicacion=ubicacion,
                detalle=caption_text
            )
            return
    
    # ─────────────────────────────────────────────────────────────
    # CASO 4: Media sin contexto claro → preguntar
    # ─────────────────────────────────────────────────────────────
    state["media_pendiente"] = {
        "media_id": media_id,
        "media_type": media_type,
    }
    persist_state(from_phone, state)
    
    media_emoji = "📸" if media_type == "image" else "🎥"
    media_nombre = "Foto" if media_type == "image" else "Video"
    
    send_whatsapp(
        from_phone,
        f"{media_emoji} {media_nombre} recibido.\n\n"
        "¿Dónde es el problema?\n\n"
        "💡 Responde con:\n"
        "• Número de habitación (ej: '305')\n"
        "• Área común (ej: 'Ascensor', 'Lobby')\n"
        "• 'foto [#]' para agregar a ticket existente\n"
        "• 'cancelar' para descartar"
    )


def handle_media_context_response(from_phone: str, text: str) -> bool:
    """
    Maneja la respuesta cuando hay un media pendiente esperando contexto.
    Se llama desde el orchestrator (tanto de HK como de supervisión).
    
    Returns:
        True si se manejó, False si no había media pendiente
    """
    get_state, persist_state, is_supervisor = _get_state_functions(from_phone)
    send_whatsapp = _get_send_function(from_phone)
    
    state = get_state(from_phone)
    media_info = state.get("media_pendiente")
    
    if not media_info:
        return False
    
    text_lower = text.strip().lower()
    
    # ─────────────────────────────────────────────────────────────
    # Opción: Cancelar
    # ─────────────────────────────────────────────────────────────
    if text_lower in ["cancelar", "cancel", "no", "descartar"]:
        state.pop("media_pendiente", None)
        persist_state(from_phone, state)
        send_whatsapp(from_phone, "❌ Foto descartada")
        return True
    
    # ─────────────────────────────────────────────────────────────
    # Opción: Agregar a ticket existente "foto 123" o solo número pequeño
    # ─────────────────────────────────────────────────────────────
    ticket_match = re.search(r'(?:foto|video|adjuntar|agregar|ticket)?\s*#?(\d+)', text_lower)
    if ticket_match:
        num = int(ticket_match.group(1))
        
        # Heurística: Si el número es < 200, probablemente es un ticket ID
        # Si es >= 200 (como 305, 420), probablemente es una habitación
        if num < 200 and not text_lower.replace(" ", "").isdigit():
            # Parece un ticket ID con contexto (ej: "foto 123", "ticket 45")
            media_id = media_info["media_id"]
            media_type = media_info["media_type"]
            
            state.pop("media_pendiente", None)
            persist_state(from_phone, state)
            
            _agregar_media_a_ticket(from_phone, media_id, media_type, num)
            return True
    
    # ─────────────────────────────────────────────────────────────
    # Opción: Ubicación (habitación o área común)
    # ─────────────────────────────────────────────────────────────
    ubicacion = _extraer_ubicacion(text)
    
    if ubicacion:
        media_id = media_info["media_id"]
        media_type = media_info["media_type"]
        
        state.pop("media_pendiente", None)
        persist_state(from_phone, state)
        
        # Guardar para el siguiente paso (esperar descripción)
        state["media_para_ticket"] = {
            "media_id": media_id,
            "media_type": media_type,
            "ubicacion": ubicacion
        }
        persist_state(from_phone, state)
        
        send_whatsapp(
            from_phone,
            f"📍 Ubicación: {ubicacion}\n\n"
            "¿Cuál es el problema?\n"
            "(Describe brevemente o envía audio)"
        )
        return True
    
    # ─────────────────────────────────────────────────────────────
    # No entendido
    # ─────────────────────────────────────────────────────────────
    send_whatsapp(
        from_phone,
        "🤔 No entendí la ubicación.\n\n"
        "💡 Ejemplos:\n"
        "• '305' (habitación)\n"
        "• 'Ascensor piso 2'\n"
        "• 'Lobby'\n"
        "• 'foto 15' (agregar a ticket #15)\n"
        "• 'cancelar'"
    )
    return True


def handle_media_detail_response(from_phone: str, text: str) -> bool:
    """
    Maneja la respuesta con el detalle del problema (después de dar ubicación).
    
    Returns:
        True si se manejó, False si no había media_para_ticket
    """
    get_state, persist_state, is_supervisor = _get_state_functions(from_phone)
    send_whatsapp = _get_send_function(from_phone)
    
    state = get_state(from_phone)
    media_info = state.get("media_para_ticket")
    
    if not media_info:
        return False
    
    text_lower = text.strip().lower()
    
    # Cancelar
    if text_lower in ["cancelar", "cancel"]:
        state.pop("media_para_ticket", None)
        persist_state(from_phone, state)
        send_whatsapp(from_phone, "❌ Reporte cancelado")
        return True
    
    # Crear el ticket con el media
    media_id = media_info["media_id"]
    media_type = media_info["media_type"]
    ubicacion = media_info["ubicacion"]
    detalle = text.strip()
    
    state.pop("media_para_ticket", None)
    persist_state(from_phone, state)
    
    _crear_ticket_con_media(
        from_phone=from_phone,
        media_id=media_id,
        media_type=media_type,
        ubicacion=ubicacion,
        detalle=detalle
    )
    return True


# ============================================================
# FUNCIONES AUXILIARES
# ============================================================

def _extraer_ubicacion(text: str) -> Optional[str]:
    """Extrae ubicación (habitación o área común) del texto."""
    try:
        from gateway_app.flows.supervision.audio_commands import (
            extract_habitacion,
            extract_area_comun
        )
        
        habitacion = extract_habitacion(text)
        if habitacion:
            return habitacion
        
        area = extract_area_comun(text)
        if area:
            return area
        
        # Fallback: si es solo un número de 3-4 dígitos, es habitación
        text_clean = text.strip()
        if re.match(r'^\d{3,4}$', text_clean):
            return text_clean
        
        return None
        
    except ImportError:
        text_clean = text.strip()
        if re.match(r'^\d{3,4}$', text_clean):
            return text_clean
        return None


def _crear_ticket_con_media(
    from_phone: str,
    media_id: str,
    media_type: str,
    ubicacion: str,
    detalle: str
) -> None:
    """Crea un ticket nuevo con media adjunto y notifica al supervisor."""
    from gateway_app.flows.housekeeping.outgoing import send_whatsapp
    from gateway_app.services.tickets_db import crear_ticket
    from gateway_app.services.media_storage import process_and_store_media
    
    from gateway_app.services.ticket_classifier import clasificar_ticket
    clasificacion = clasificar_ticket(
        detalle=detalle,
        ubicacion=str(ubicacion),
    )
    prioridad = clasificacion["prioridad"]
    area = clasificacion["area"]
    
    try:
        ticket = crear_ticket(
            habitacion=ubicacion,
            detalle=detalle,
            prioridad=prioridad,
            area=area,
            creado_por=from_phone,
            origen="supervisor",
            routing_source=clasificacion["routing_source"],
            routing_reason=clasificacion["routing_reason"],
            routing_confidence=clasificacion["routing_confidence"],
            routing_version=clasificacion["routing_source"],  
        )
        
        if not ticket:
            send_whatsapp(from_phone, "❌ Error creando ticket. Intenta de nuevo.")
            return
        
        ticket_id = ticket["id"]
        
        # Procesar y guardar media
        media_result = process_and_store_media(
            media_id=media_id,
            media_type=media_type,
            ticket_id=ticket_id,
            uploaded_by=from_phone
        )
        
        media_emoji = "📸" if media_type == "image" else "🎥"
        prioridad_emoji = {"ALTA": "🔴", "MEDIA": "🟡", "BAJA": "🟢"}.get(prioridad, "🟡")
        
        send_whatsapp(
            from_phone,
            f"✅ Ticket #{ticket_id} creado {media_emoji}\n\n"
            f"📍 Ubicación: {ubicacion}\n"
            f"📝 {detalle}\n"
            f"{prioridad_emoji} Prioridad: {prioridad}"
        )
        
        # Notificar al supervisor (si quien envía no es supervisor)
        _, _, is_supervisor = _get_state_functions(from_phone)
        if not is_supervisor:
            _notificar_supervisor_nuevo_ticket(
                ticket_id=ticket_id,
                ubicacion=ubicacion,
                detalle=detalle,
                prioridad=prioridad,
                media_id=media_id,
                media_type=media_type,
                reportado_por=from_phone,
                storage_url=media_result.get("storage_url")
            )
        
        logger.info(f"✅ Ticket #{ticket_id} creado con {media_type} por {from_phone}")
        
    except Exception as e:
        logger.exception(f"❌ Error creando ticket con media: {e}")
        send_whatsapp(from_phone, "❌ Error creando ticket. Intenta de nuevo.")


def _agregar_media_a_ticket(
    from_phone: str,
    media_id: str,
    media_type: str,
    ticket_id: int
) -> None:
    """Agrega un media a un ticket existente."""
    from gateway_app.flows.housekeeping.outgoing import send_whatsapp
    from gateway_app.services.tickets_db import obtener_ticket_por_id
    from gateway_app.services.media_storage import process_and_store_media
    
    ticket = obtener_ticket_por_id(ticket_id)
    
    if not ticket:
        send_whatsapp(from_phone, f"❌ No encontré el ticket #{ticket_id}")
        return
    
    media_result = process_and_store_media(
        media_id=media_id,
        media_type=media_type,
        ticket_id=ticket_id,
        uploaded_by=from_phone
    )
    
    if not media_result["success"]:
        send_whatsapp(from_phone, f"❌ Error guardando {'foto' if media_type == 'image' else 'video'}")
        return
    
    media_emoji = "📸" if media_type == "image" else "🎥"
    
    send_whatsapp(
        from_phone,
        f"✅ {media_emoji} agregado al ticket #{ticket_id}\n\n"
        f"📍 {ticket.get('ubicacion') or ticket.get('habitacion', '?')}\n"
        f"📝 {ticket.get('detalle', '')[:50]}"
    )
    
    # Notificar al supervisor
    _notificar_supervisor_media_agregado(
        ticket_id=ticket_id,
        media_id=media_id,
        media_type=media_type,
        agregado_por=from_phone,
        storage_url=media_result.get("storage_url")
    )
    
    logger.info(f"✅ {media_type} agregado a ticket #{ticket_id} por {from_phone}")


def _notificar_supervisor_nuevo_ticket(
    ticket_id: int,
    ubicacion: str,
    detalle: str,
    prioridad: str,
    media_id: str,
    media_type: str,
    reportado_por: str,
    storage_url: Optional[str] = None
) -> None:
    """Notifica al supervisor sobre un nuevo ticket con foto/video."""
    from gateway_app.services.whatsapp_client import send_whatsapp_image, send_whatsapp_text
    
    supervisor_phones_str = os.getenv("SUPERVISOR_PHONES", "")
    supervisor_phones = [p.strip() for p in supervisor_phones_str.split(",") if p.strip()]
    
    if not supervisor_phones:
        logger.warning("⚠️ No hay supervisores configurados para notificar")
        return
    
    prioridad_emoji = {"ALTA": "🔴", "MEDIA": "🟡", "BAJA": "🟢"}.get(prioridad, "🟡")
    media_emoji = "📸" if media_type == "image" else "🎥"
    
    caption = (
        f"📋 Nuevo Ticket #{ticket_id} {media_emoji}\n\n"
        f"📍 Ubicación: {ubicacion}\n"
        f"📝 {detalle}\n"
        f"{prioridad_emoji} Prioridad: {prioridad}\n\n"
        f"💡 Responde 'asignar {ticket_id} a [nombre]'"
    )
    
    for sup_phone in supervisor_phones:
        try:
            if media_type == "image":
                result = send_whatsapp_image(
                    to=sup_phone,
                    media_id=media_id,
                    caption=caption
                )
                if not result.get("success"):
                    send_whatsapp_text(to=sup_phone, body=caption)
            else:
                send_whatsapp_text(to=sup_phone, body=caption)
            
            logger.info(f"✅ Supervisor {sup_phone} notificado de ticket #{ticket_id}")
            
        except Exception as e:
            logger.exception(f"❌ Error notificando supervisor {sup_phone}: {e}")


def _notificar_supervisor_media_agregado(
    ticket_id: int,
    media_id: str,
    media_type: str,
    agregado_por: str,
    storage_url: Optional[str] = None
) -> None:
    """Notifica al supervisor que se agregó una foto a un ticket existente."""
    from gateway_app.services.whatsapp_client import send_whatsapp_image, send_whatsapp_text
    from gateway_app.services.tickets_db import obtener_ticket_por_id
    
    supervisor_phones_str = os.getenv("SUPERVISOR_PHONES", "")
    supervisor_phones = [p.strip() for p in supervisor_phones_str.split(",") if p.strip()]
    
    if not supervisor_phones:
        return
    
    ticket = obtener_ticket_por_id(ticket_id)
    ubicacion = ticket.get("ubicacion") or ticket.get("habitacion", "?") if ticket else "?"
    
    media_emoji = "📸" if media_type == "image" else "🎥"
    
    caption = (
        f"{media_emoji} Nueva foto en Ticket #{ticket_id}\n\n"
        f"📍 {ubicacion}"
    )
    
    for sup_phone in supervisor_phones:
        try:
            if media_type == "image":
                send_whatsapp_image(to=sup_phone, media_id=media_id, caption=caption)
            else:
                send_whatsapp_text(to=sup_phone, body=caption)
        except Exception as e:
            logger.exception(f"❌ Error notificando supervisor: {e}")


def _detectar_prioridad(texto: str) -> str:
    """Detecta prioridad del texto."""
    texto_lower = texto.lower()
    
    palabras_alta = ["urgente", "emergencia", "ya", "ahora", "rápido", "grave", "peligro"]
    palabras_baja = ["cuando puedas", "no urgente", "después", "menor"]
    
    if any(p in texto_lower for p in palabras_alta):
        return "ALTA"
    if any(p in texto_lower for p in palabras_baja):
        return "BAJA"
    
    return "MEDIA"