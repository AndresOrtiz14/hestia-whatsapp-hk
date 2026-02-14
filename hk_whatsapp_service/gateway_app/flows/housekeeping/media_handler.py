# gateway_app/flows/housekeeping/media_handler.py
"""
Manejo de medios (fotos/videos) enviados por trabajadores.
Soporta:
- Foto con nuevo reporte (ubicación + descripción)
- Foto para ticket existente
- Foto sin contexto (el bot pregunta)
"""

import logging
import re
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)


def handle_media_message(
    from_phone: str,
    media_id: str,
    media_type: str,  # "image" o "video"
    caption: Optional[str] = None
) -> None:
    """
    Punto de entrada para mensajes con media.
    
    Flujos posibles:
    1. Media con caption que incluye ubicación → crear ticket con media
    2. Media con caption "foto 123" → agregar a ticket existente
    3. Media con caption pero sin ubicación → preguntar contexto
    4. Media sin caption → preguntar contexto
    5. Media cuando hay media_pendiente en estado → asociar al contexto
    
    Args:
        from_phone: Teléfono del trabajador
        media_id: ID del media de WhatsApp
        media_type: "image" o "video"
        caption: Texto que acompaña al media (puede ser None)
    """
    from .state_simple import get_state, persist_state
    from .outgoing import send_whatsapp
    from gateway_app.services.media_storage import process_and_store_media
    
    state = get_state(from_phone)
    caption_text = (caption or "").strip()
    caption_lower = caption_text.lower()
    
    logger.info(f"📸 HK | {from_phone} | Media: {media_type} | Caption: '{caption_text[:50] if caption_text else '(sin caption)'}'")
    
    # ─────────────────────────────────────────────────────────────
    # CASO 1: Hay un flujo de media pendiente esperando ubicación
    # ─────────────────────────────────────────────────────────────
    if state.get("media_pendiente"):
        # El trabajador ya envió una foto antes y estamos esperando contexto
        # Ahora envió OTRA foto - reemplazamos la anterior
        logger.info(f"📸 HK | Reemplazando media pendiente anterior")
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
            # Crear ticket con el media adjunto
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
    Se llama desde el orchestrator principal cuando detecta media_pendiente.
    
    Args:
        from_phone: Teléfono del trabajador
        text: Respuesta del trabajador
    
    Returns:
        True si se manejó, False si no había media pendiente
    """
    from .state_simple import get_state, persist_state
    from .outgoing import send_whatsapp
    
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
    # Opción: Agregar a ticket existente "foto 123"
    # ─────────────────────────────────────────────────────────────
    ticket_match = re.search(r'(?:foto|video|adjuntar|agregar|ticket)?\s*#?(\d+)', text_lower)
    if ticket_match and text_lower.replace(" ", "").isdigit() is False:
        # Verificar que no sea solo un número de habitación (3-4 dígitos típicos de hab)
        num = int(ticket_match.group(1))
        
        # Heurística: tickets suelen ser < 1000, habitaciones 100-999 o 1000-9999
        # Si el número es pequeño (< 200), probablemente es un ticket
        if num < 200:
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
        
        # Preguntar por el detalle del problema
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
    
    Args:
        from_phone: Teléfono del trabajador
        text: Descripción del problema
    
    Returns:
        True si se manejó, False si no había media_para_ticket
    """
    from .state_simple import get_state, persist_state
    from .outgoing import send_whatsapp
    
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


def _extraer_ubicacion(text: str) -> Optional[str]:
    """
    Extrae ubicación (habitación o área común) del texto.
    
    Returns:
        Ubicación formateada o None
    """
    # Importar funciones de audio_commands de supervisión (reutilizar lógica)
    try:
        from gateway_app.flows.supervision.audio_commands import (
            extract_habitacion,
            extract_area_comun
        )
        
        # Intentar habitación primero
        habitacion = extract_habitacion(text)
        if habitacion:
            return habitacion
        
        # Intentar área común
        area = extract_area_comun(text)
        if area:
            return area
        
        # Fallback: si es solo un número de 3-4 dígitos, es habitación
        text_clean = text.strip()
        if re.match(r'^\d{3,4}$', text_clean):
            return text_clean
        
        return None
        
    except ImportError:
        # Fallback si no existe el módulo
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
    """
    Crea un ticket nuevo con media adjunto y notifica al supervisor.
    """
    from .outgoing import send_whatsapp
    from gateway_app.services.tickets_db import crear_ticket
    from gateway_app.services.media_storage import process_and_store_media
    
    # Detectar prioridad del texto
    prioridad = _detectar_prioridad(detalle)
    
    # Detectar área
    area = "HOUSEKEEPING"
    if not ubicacion.isdigit():
        area = "AREAS_COMUNES"
    
    # Crear ticket en BD
    try:
        ticket = crear_ticket(
            habitacion=ubicacion,
            detalle=detalle,
            prioridad=prioridad,
            area=area,
            creado_por=from_phone,
            origen="trabajador"
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
        
        # Confirmar al trabajador
        send_whatsapp(
            from_phone,
            f"✅ Ticket #{ticket_id} creado {media_emoji}\n\n"
            f"📍 Ubicación: {ubicacion}\n"
            f"📝 {detalle}\n"
            f"{prioridad_emoji} Prioridad: {prioridad}\n\n"
            f"El supervisor será notificado."
        )
        
        # Notificar al supervisor
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
    """
    Agrega un media a un ticket existente.
    """
    from .outgoing import send_whatsapp
    from gateway_app.services.tickets_db import obtener_ticket_por_id
    from gateway_app.services.media_storage import process_and_store_media
    
    # Verificar que el ticket existe
    ticket = obtener_ticket_por_id(ticket_id)
    
    if not ticket:
        send_whatsapp(from_phone, f"❌ No encontré el ticket #{ticket_id}")
        return
    
    # Procesar y guardar media
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
    """
    Notifica al supervisor sobre un nuevo ticket con foto/video.
    Envía la imagen por WhatsApp.
    """
    from gateway_app.services.whatsapp_client import send_whatsapp_image, send_whatsapp_text
    import os
    
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
            # Enviar imagen con caption
            if media_type == "image":
                result = send_whatsapp_image(
                    to=sup_phone,
                    media_id=media_id,
                    caption=caption
                )
                if not result.get("success"):
                    # Fallback: enviar texto + link
                    send_whatsapp_text(to=sup_phone, body=caption)
            else:
                # Para videos, enviar texto (más pesado)
                send_whatsapp_text(to=sup_phone, body=caption)
                # TODO: Implementar send_whatsapp_video si es necesario
            
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
    """
    Notifica al supervisor que se agregó una foto a un ticket existente.
    """
    from gateway_app.services.whatsapp_client import send_whatsapp_image, send_whatsapp_text
    from gateway_app.services.tickets_db import obtener_ticket_por_id
    import os
    
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
