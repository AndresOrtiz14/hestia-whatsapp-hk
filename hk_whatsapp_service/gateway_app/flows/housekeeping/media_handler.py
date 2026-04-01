# gateway_app/flows/housekeeping/media_handler.py
"""
Manejo de medios (fotos/videos) enviados por trabajadores Y supervisores.
VERSIÓN CORREGIDA: Usa el estado correcto según el rol del usuario.
"""

import logging
import re
from typing import Optional, Dict, Any, Callable

logger = logging.getLogger(__name__)

# Detecta directivas de asignación al final de un caption/texto:
# "asígnalo a Pedro", "asignar a María", "asignarla a Carlos", etc.
_ASSIGN_PATTERN = re.compile(
    r'\s*\bas[ií]gn(?:a(?:lo|la|los|las)?|ar(?:lo|la|los|las)?)\s+a\s+(.+?)\.?\s*$',
    re.IGNORECASE,
)

# ============================================================
# HELPER: Detectar rol y obtener funciones de estado correctas
# ============================================================

def _get_state_functions(phone: str, tenant=None) -> tuple:
    """
    Retorna las funciones de estado correctas según el rol del usuario.

    Returns:
        (get_state_func, persist_state_func, is_supervisor)
    """
    from gateway_app.services.workers_db import obtener_supervisores_por_area
    _sups = obtener_supervisores_por_area("", property_id=tenant.property_id if tenant else "")
    supervisor_phones = {s["telefono"] for s in _sups if s.get("telefono")}
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
    caption: Optional[str] = None,
    tenant=None,
) -> None:
    """
    Punto de entrada para mensajes con media.
    Funciona tanto para workers como supervisores.
    """
    get_state, persist_state, is_supervisor = _get_state_functions(from_phone, tenant=tenant)
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
        
        # ── NUEVO: aunque haya media_pendiente, si el caption tiene
        # ubicación + detalle, procesarlo directo en lugar de preguntar ──
        if caption_text:
            ubicacion = _extraer_ubicacion(caption_text)
            if ubicacion:
                detalle = caption_text.strip()
                if detalle.startswith(ubicacion):
                    detalle = detalle[len(ubicacion):].strip(" .,:-")
                
                if detalle:
                    # Caption completo: crear ticket directo y limpiar state
                    state.pop("media_pendiente", None)
                    persist_state(from_phone, state)
                    worker_nombre_c1, detalle = _extract_assignment_from_caption(detalle)
                    _crear_ticket_con_media(
                        from_phone=from_phone,
                        media_id=media_id,
                        media_type=media_type,
                        ubicacion=ubicacion,
                        detalle=detalle,
                        tenant=tenant,
                        worker_nombre=worker_nombre_c1,
                    )
                    return
                else:
                    # Caption solo tiene ubicación: guardarla y pedir detalle
                    state["media_pendiente"] = {
                        "media_id": media_id,
                        "media_type": media_type,
                        "ubicacion": ubicacion,
                    }
                    persist_state(from_phone, state)
                    send_whatsapp(
                        from_phone,
                        f"📍 Ubicación: {ubicacion}\n\n"
                        "¿Cuál es el problema?\n"
                        "(Describe brevemente o envía audio)"
                    )
                    return
        # ────────────────────────────────────────────────────────────────

        # Sin caption útil: actualizar media y preguntar ubicación
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
        _agregar_media_a_ticket(from_phone, media_id, media_type, ticket_id, tenant=tenant)
        return
    
    # ─────────────────────────────────────────────────────────────
    # CASO 3: Caption con ubicación → crear ticket con media
    # ─────────────────────────────────────────────────────────────
    if caption_text:
        ubicacion = _extraer_ubicacion(caption_text)
        if ubicacion:
            detalle = caption_text.strip()
            if detalle.startswith(ubicacion):
                detalle = detalle[len(ubicacion):].strip(" .,:-")
            
            # ── NUEVO: si no quedó descripción, preguntar ──────────────
            if not detalle:
                state["media_pendiente"] = {
                    "media_id": media_id,
                    "media_type": media_type,
                    "ubicacion": ubicacion,   # ← ya la tenemos, no preguntar de nuevo
                }
                persist_state(from_phone, state)
                send_whatsapp(
                    from_phone,
                    f"📍 Ubicación: {ubicacion}\n\n"
                    "¿Cuál es el problema?\n"
                    "(Describe brevemente o envía audio)"
                )
                return
            # ──────────────────────────────────────────────────────────

            worker_nombre_c3, detalle = _extract_assignment_from_caption(detalle)
            _crear_ticket_con_media(
                from_phone=from_phone,
                media_id=media_id,
                media_type=media_type,
                ubicacion=ubicacion,
                detalle=detalle,
                tenant=tenant,
                worker_nombre=worker_nombre_c3,
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


def handle_media_context_response(from_phone: str, text: str, tenant=None) -> bool:
    """
    Maneja la respuesta cuando hay un media pendiente esperando contexto.
    Se llama desde el orchestrator (tanto de HK como de supervisión).

    Returns:
        True si se manejó, False si no había media pendiente
    """
    get_state, persist_state, is_supervisor = _get_state_functions(from_phone, tenant=tenant)
    send_whatsapp = _get_send_function(from_phone)
    
    state = get_state(from_phone)
    media_info = state.get("media_pendiente")
    ubicacion_guardada = media_info.get("ubicacion") if media_info else None
    if ubicacion_guardada:
    # Ya tenemos ubicación, el texto que llegó ES el detalle
        detalle_ctx = text.strip()
        worker_nombre_ctx, detalle_ctx = _extract_assignment_from_caption(detalle_ctx)
        _crear_ticket_con_media(
            from_phone=from_phone,
            media_id=media_info["media_id"],
            media_type=media_info["media_type"],
            ubicacion=ubicacion_guardada,
            detalle=detalle_ctx,
            tenant=tenant,
            worker_nombre=worker_nombre_ctx,
        )
        state.pop("media_pendiente", None)
        persist_state(from_phone, state)
        return True
    
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

            _agregar_media_a_ticket(from_phone, media_id, media_type, num, tenant=tenant)
            return True

    # ─────────────────────────────────────────────────────────────
    # Opción: Ubicación (habitación o área común)
    # ─────────────────────────────────────────────────────────────
    ubicacion = _extraer_ubicacion(text)
    
    if ubicacion:
        media_id = media_info["media_id"]
        media_type = media_info["media_type"]

        # Intentar extraer asignación y descripción del mismo mensaje
        worker_nombre_ctx, text_sin_asign = _extract_assignment_from_caption(text)
        detalle = _extraer_descripcion_sin_ubicacion(text_sin_asign, ubicacion)

        state.pop("media_pendiente", None)
        persist_state(from_phone, state)

        if detalle:
            # Tenemos todo: crear ticket directamente sin preguntar más
            _crear_ticket_con_media(
                from_phone=from_phone,
                media_id=media_id,
                media_type=media_type,
                ubicacion=ubicacion,
                detalle=detalle,
                tenant=tenant,
                worker_nombre=worker_nombre_ctx,
            )
        else:
            # Solo tenemos ubicación: pedir descripción
            state["media_para_ticket"] = {
                "media_id": media_id,
                "media_type": media_type,
                "ubicacion": ubicacion,
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


def handle_media_detail_response(from_phone: str, text: str, tenant=None) -> bool:
    """
    Maneja la respuesta con el detalle del problema (después de dar ubicación).

    Returns:
        True si se manejó, False si no había media_para_ticket
    """
    get_state, persist_state, is_supervisor = _get_state_functions(from_phone, tenant=tenant)
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
    worker_nombre_det, detalle = _extract_assignment_from_caption(detalle)

    state.pop("media_para_ticket", None)
    persist_state(from_phone, state)

    _crear_ticket_con_media(
        from_phone=from_phone,
        media_id=media_id,
        media_type=media_type,
        ubicacion=ubicacion,
        detalle=detalle,
        tenant=tenant,
        worker_nombre=worker_nombre_det,
    )
    return True


# ============================================================
# FUNCIONES AUXILIARES
# ============================================================

def _extraer_descripcion_sin_ubicacion(text: str, ubicacion: str) -> Optional[str]:
    """
    Dado el texto (ya sin directiva de asignación), elimina la referencia a la
    ubicación —incluyendo preposiciones de contexto como "en la", "hab"— y
    retorna el resto como descripción del problema.
    Retorna None si no queda texto significativo.
    """
    cleaned = re.sub(
        r'\b(?:en\s+(?:la\s+|el\s+|los?\s+|las?\s+)?|habitaci[oó]n\s+|hab\.?\s+)?'
        + re.escape(ubicacion) + r'\b',
        '',
        text,
        flags=re.IGNORECASE,
    ).strip(' .,:-')
    return cleaned if cleaned else None


def _extract_assignment_from_caption(text: str):
    """
    Detecta directiva de asignación al final del texto.
    Ejemplos: "No hay agua asígnalo a Pedro", "202 fuga asignar a María"

    Returns (worker_name, cleaned_text) — worker_name es None si no hay directiva.
    """
    m = _ASSIGN_PATTERN.search(text)
    if not m:
        return None, text
    worker_name = m.group(1).strip().rstrip(".,")
    cleaned = text[:m.start()].strip().rstrip(".,:-")
    return worker_name, cleaned


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

        # Fallback 1: número solo (mensaje es solo el número)
        text_clean = text.strip()
        if re.match(r'^\d{3,4}$', text_clean):
            return text_clean

        # ── NUEVO Fallback 2: número al INICIO del caption ────────
        # Cubre el caso "913 se salió el cable" o "204 fuga de agua"
        match = re.match(r'^(\d{3,4})\b', text_clean)
        if match:
            return match.group(1)
        
        # ── NUEVO Fallback 3: número al FINAL ─────────────────────────
        # Cubre "Sale agua 319", "Fuga 204", "Limpieza urgente 512"
        match = re.search(r'\b(\d{3,4})$', text_clean.rstrip(' .,!?'))
        if match:
            return match.group(1)

        return None
        
    except ImportError:
        text_clean = text.strip()
        if re.match(r'^\d{3,4}$', text_clean):
            return text_clean
        # NUEVO: mismo fallback en el except
        match = re.match(r'^(\d{3,4})\b', text_clean)
        if match:
            return match.group(1)
        return None


def _crear_ticket_con_media(
    from_phone: str,
    media_id: str,
    media_type: str,
    ubicacion: str,
    detalle: str,
    tenant=None,
    worker_nombre: Optional[str] = None,
) -> None:
    """Crea un ticket nuevo con media adjunto y notifica al supervisor."""
    from gateway_app.flows.housekeeping.outgoing import send_whatsapp
    from gateway_app.services.tickets_db import crear_ticket
    from gateway_app.services.media_storage import process_and_store_media
    from gateway_app.flows.housekeeping.state_simple import get_user_state

    from gateway_app.services.ticket_classifier import clasificar_ticket
    clasificacion = clasificar_ticket(
        detalle=detalle,
        ubicacion=str(ubicacion),
    )
    prioridad = clasificacion["prioridad"]
    area = clasificacion["area"]
    _state = get_user_state(from_phone)

    try:
        ticket = crear_ticket(
            habitacion=ubicacion,
            detalle=detalle,
            prioridad=prioridad,
            area=area,
            creado_por=from_phone,
            origen="supervisor",
            property_id=tenant.property_id if tenant else None,
            user_id=_state.get("user_id"),
            routing_source=clasificacion["routing_source"],
            routing_reason=clasificacion["routing_reason"],
            routing_confidence=clasificacion["routing_confidence"],
            routing_version=clasificacion["routing_source"],
        )
        
        if not ticket:
            send_whatsapp(from_phone, "❌ Error creando ticket. Intenta de nuevo.")
            return
        
        ticket_uuid = ticket["id"]                          # UUID para operaciones de DB/storage
        ticket_id = ticket.get("id_code") or ticket_uuid   # id_code para mostrar al usuario

        # Procesar y guardar media
        try:
            media_result = process_and_store_media(
                media_id=media_id,
                media_type=media_type,
                ticket_id=ticket_uuid,
                uploaded_by=from_phone,
                tenant=tenant,
            )
            if media_result and media_result.get("success"):
                storage_url = media_result.get("storage_url")
                logger.info("📦 Media guardada en storage | ticket=%s | url=%s", ticket_id, storage_url)
                if storage_url:
                    from gateway_app.services.tickets_db import guardar_photo_url_ticket
                    guardar_photo_url_ticket(ticket_uuid, storage_url)
            else:
                logger.warning("⚠️ Media NO guardada en storage | ticket=%s | error=%s", ticket_id, media_result.get("error") if media_result else "sin resultado")
                media_result = {}
        except Exception as e:
            logger.error("❌ Error guardando media en storage | ticket=%s | error=%s", ticket_id, e)
            media_result = {}
        
        media_emoji = "📸" if media_type == "image" else "🎥"
        prioridad_emoji = {"ALTA": "🔴", "MEDIA": "🟡", "BAJA": "🟢"}.get(prioridad, "🟡")
        
        send_whatsapp(
            from_phone,
            f"✅ Ticket #{ticket_id} creado {media_emoji}\n\n"
            f"📍 Ubicación: {ubicacion}\n"
            f"📝 {detalle}\n"
            f"{prioridad_emoji} Prioridad: {prioridad}"
        )

        # Auto-asignar si se detectó un nombre de trabajador en el caption
        if worker_nombre:
            try:
                from gateway_app.services.workers_db import buscar_worker_por_nombre
                from gateway_app.services.tickets_db import asignar_ticket as _asignar_ticket
                from gateway_app.services.whatsapp_client import send_whatsapp_text
                _property_id = tenant.property_id if tenant else None
                worker = buscar_worker_por_nombre(worker_nombre, property_id=_property_id or "")
                if worker:
                    worker_phone = worker.get("telefono")
                    worker_display = worker.get("nombre_completo") or worker.get("username")
                    if _asignar_ticket(ticket_uuid, worker_phone, worker_display, property_id=_property_id):
                        send_whatsapp(from_phone, f"👤 Asignado a {worker_display}")
                        prioridad_emoji_w = {"ALTA": "🔴", "MEDIA": "🟡", "BAJA": "🟢"}.get(prioridad, "🟡")
                        send_whatsapp_text(
                            to=worker_phone,
                            body=(
                                f"📋 Nueva tarea asignada\n\n"
                                f"#{ticket_id} · {ubicacion}\n"
                                f"{detalle}\n"
                                f"{prioridad_emoji_w} Prioridad: {prioridad}\n\n"
                                f"💡 Responde 'tomar' para aceptar"
                            ),
                            token=tenant.wa_token if tenant else None,
                            phone_number_id=tenant.phone_number_id if tenant else None,
                        )
                    else:
                        send_whatsapp(from_phone, f"⚠️ No pude asignar a {worker_nombre}. Asigna manualmente.")
                else:
                    send_whatsapp(from_phone, f"⚠️ No encontré a '{worker_nombre}'. Asigna manualmente.")
            except Exception as e:
                logger.error("❌ Error en auto-asignación desde caption | ticket=%s | worker=%s | error=%s", ticket_id, worker_nombre, e)
                send_whatsapp(from_phone, f"⚠️ Error al asignar a {worker_nombre}. Asigna manualmente.")

        # Notificar al supervisor (si quien envía no es supervisor)
        _, _, is_supervisor = _get_state_functions(from_phone, tenant=tenant)
        if not is_supervisor:
            _notificar_supervisor_nuevo_ticket(
                ticket_id=ticket_id,
                ubicacion=ubicacion,
                detalle=detalle,
                prioridad=prioridad,
                media_id=media_id,
                media_type=media_type,
                reportado_por=from_phone,
                storage_url=media_result.get("storage_url"),
                tenant=tenant,
                area=area,
            )
        
        logger.info(f"✅ Ticket #{ticket_id} creado con {media_type} por {from_phone}")
        
    except Exception as e:
        logger.exception(f"❌ Error creando ticket con media: {e}")
        send_whatsapp(from_phone, "❌ Error creando ticket. Intenta de nuevo.")


def _agregar_media_a_ticket(
    from_phone: str,
    media_id: str,
    media_type: str,
    ticket_id: int,
    tenant=None,
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
        uploaded_by=from_phone,
        tenant=tenant,
    )

    if media_result.get("success") and media_result.get("storage_url"):
        from gateway_app.services.tickets_db import guardar_photo_url_ticket
        guardar_photo_url_ticket(ticket_id, media_result["storage_url"])

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
        storage_url=media_result.get("storage_url"),
        tenant=tenant,
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
    storage_url: Optional[str] = None,
    tenant=None,
    area: str = "HOUSEKEEPING",
) -> None:
    """Notifica al supervisor sobre un nuevo ticket con foto/video."""
    from gateway_app.services.whatsapp_client import send_whatsapp_image, send_whatsapp_text
    from gateway_app.services.workers_db import obtener_supervisores_por_area

    _property_id = tenant.property_id if tenant else ""
    _sups = obtener_supervisores_por_area(area, property_id=_property_id)
    if not _sups:
        # Fallback: buscar supervisores sin filtro de área
        _sups = obtener_supervisores_por_area("", property_id=_property_id)
    supervisor_phones = [s["telefono"] for s in _sups if s.get("telefono")]

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
    
    _phone_number_id = tenant.phone_number_id if tenant else None
    _token = tenant.wa_token if tenant else None
    for sup_phone in supervisor_phones:
        try:
            if media_type == "image":
                result = send_whatsapp_image(
                    to=sup_phone,
                    media_id=media_id,
                    caption=caption,
                    token=_token,
                    phone_number_id=_phone_number_id,
                )
                if not result.get("success"):
                    send_whatsapp_text(to=sup_phone, body=caption, token=_token, phone_number_id=_phone_number_id)
            else:
                send_whatsapp_text(to=sup_phone, body=caption, token=_token, phone_number_id=_phone_number_id)

            logger.info(f"✅ Supervisor {sup_phone} notificado de ticket #{ticket_id}")
            
        except Exception as e:
            logger.exception(f"❌ Error notificando supervisor {sup_phone}: {e}")


def _notificar_supervisor_media_agregado(
    ticket_id: int,
    media_id: str,
    media_type: str,
    agregado_por: str,
    storage_url: Optional[str] = None,
    tenant=None,
) -> None:
    """Notifica al supervisor que se agregó una foto a un ticket existente."""
    from gateway_app.services.whatsapp_client import send_whatsapp_image, send_whatsapp_text
    from gateway_app.services.tickets_db import obtener_ticket_por_id
    from gateway_app.services.workers_db import obtener_supervisores_por_area

    _sups = obtener_supervisores_por_area("HOUSEKEEPING", property_id=tenant.property_id if tenant else "")
    supervisor_phones = [s["telefono"] for s in _sups if s.get("telefono")]

    if not supervisor_phones:
        return
    
    ticket = obtener_ticket_por_id(ticket_id)
    ubicacion = ticket.get("ubicacion") or ticket.get("habitacion", "?") if ticket else "?"
    
    media_emoji = "📸" if media_type == "image" else "🎥"
    
    caption = (
        f"{media_emoji} Nueva foto en Ticket #{ticket_id}\n\n"
        f"📍 {ubicacion}"
    )
    
    _phone_number_id = tenant.phone_number_id if tenant else None
    for sup_phone in supervisor_phones:
        try:
            if media_type == "image":
                send_whatsapp_image(to=sup_phone, media_id=media_id, caption=caption, phone_number_id=_phone_number_id)
            else:
                send_whatsapp_text(to=sup_phone, body=caption, phone_number_id=_phone_number_id)
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