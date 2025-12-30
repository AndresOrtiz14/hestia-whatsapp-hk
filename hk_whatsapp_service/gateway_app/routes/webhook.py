"""
Webhook de WhatsApp con soporte para texto Y audio.
Versión actualizada que maneja notas de voz con transcripción automática.
"""

from flask import Blueprint, request, jsonify
import logging

from gateway_app.config import Config
from gateway_app.services.whatsapp_client import send_whatsapp_text

bp = Blueprint("whatsapp_webhook", __name__)
logger = logging.getLogger(__name__)

# Wire up the real WhatsApp sender BEFORE importing the handler
import gateway_app.flows.housekeeping.outgoing as outgoing
outgoing.SEND_IMPL = lambda to, body: send_whatsapp_text(to=to, body=body)

# Import NUEVO handler con soporte de audio
from gateway_app.flows.housekeeping.message_handler import handle_hk_message_with_audio


@bp.get("/webhook")
def verify():
    """
    Verificación del webhook (requerido por WhatsApp Cloud API).
    No cambió - mantiene la misma lógica.
    """
    mode = request.args.get("hub.mode")
    token = request.args.get("hub.verify_token")
    challenge = request.args.get("hub.challenge")

    if mode == "subscribe" and token == Config.VERIFY_TOKEN:
        logger.info("Webhook verificado correctamente")
        return challenge, 200
    
    logger.warning("Verificación fallida")
    return "Forbidden", 403


@bp.post("/webhook")
def inbound():
    """
    Webhook principal - ACTUALIZADO con soporte de audio.
    
    Ahora maneja:
    - Mensajes de texto (como antes)
    - Mensajes de audio/voz (NUEVO)
    """
    payload = request.get_json(silent=True) or {}

    try:
        entry = payload["entry"][0]
        change = entry["changes"][0]
        value = change["value"]
        messages = value.get("messages", [])

        if not messages:
            return jsonify(ok=True), 200

        msg = messages[0]
        from_phone = msg.get("from")
        msg_type = msg.get("type")  # ← NUEVO: detectar tipo de mensaje

        if not from_phone or not msg_type:
            logger.warning("Mensaje sin from o type")
            return jsonify(ok=True), 200

        # Preparar datos del mensaje
        message_data = {"type": msg_type}

        # CASO 1: Mensaje de texto (como antes)
        if msg_type == "text":
            text = (msg.get("text") or {}).get("body", "")
            if not text:
                return jsonify(ok=True), 200
            
            message_data["text"] = text
            logger.info(f"Mensaje de texto de {from_phone}: {text[:50]}...")

        # CASO 2: Mensaje de audio/voz (NUEVO)
        elif msg_type in ["audio", "voice"]:
            audio_data = msg.get("audio") or msg.get("voice") or {}
            media_id = audio_data.get("id")
            
            if not media_id:
                logger.warning("Audio sin media_id")
                return jsonify(ok=True), 200
            
            message_data["media_id"] = media_id
            logger.info(f"Mensaje de audio de {from_phone}, media_id={media_id}")

        # CASO 3: Otros tipos (imagen, video, documento, etc.)
        else:
            logger.info(f"Tipo de mensaje no soportado: {msg_type}")
            # Opcionalmente, puedes notificar al usuario:
            # send_whatsapp_text(
            #     to=from_phone,
            #     body="⚠️ Solo puedo procesar mensajes de texto y audio por ahora."
            # )
            return jsonify(ok=True), 200

        # Procesar mensaje (maneja texto Y audio automáticamente)
        handle_hk_message_with_audio(
            from_phone,
            message_data,
            show_transcription=True  # Mostrar "🎤 Escuché: ..."
        )

        return jsonify(ok=True), 200

    except Exception as e:
        logger.exception("Error procesando webhook")
        # Siempre retornar 200 para que WhatsApp no reintente
        return jsonify(ok=False, error=str(e)), 200