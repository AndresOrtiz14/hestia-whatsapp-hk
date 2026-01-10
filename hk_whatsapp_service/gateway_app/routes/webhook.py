"""
Webhook de WhatsApp con routing por rol (Supervisor vs Mucama).
"""

from flask import Blueprint, request, jsonify
import logging

import logging

from gateway_app.config import Config
from gateway_app.services.whatsapp_client import send_whatsapp_text

bp = Blueprint("whatsapp_webhook", __name__)
logger = logging.getLogger(__name__)

# Wire up WhatsApp sender para ambos bots
import gateway_app.flows.housekeeping.outgoing as hk_outgoing
import gateway_app.flows.supervision.outgoing as sup_outgoing

hk_outgoing.SEND_IMPL = lambda to, body: send_whatsapp_text(to=to, body=body)
sup_outgoing.SEND_IMPL = lambda to, body: send_whatsapp_text(to=to, body=body)

# Import handlers
from gateway_app.flows.housekeeping.message_handler import handle_hk_message_with_audio
from gateway_app.flows.supervision import handle_supervisor_message


# Configuración: Detectar rol por número de teléfono
# Lee desde variable de entorno SUPERVISOR_PHONES
import os

# Leer y parsear números de supervisores desde environment
supervisor_phones_str = os.getenv("SUPERVISOR_PHONES", "")
SUPERVISOR_PHONES = [
    phone.strip() 
    for phone in supervisor_phones_str.split(",") 
    if phone.strip()
]

# Logging para debug
if not SUPERVISOR_PHONES:
    logger.warning("⚠️ SUPERVISOR_PHONES no configurado en environment variables")
else:
    logger.info(f"✅ {len(SUPERVISOR_PHONES)} supervisor(es) configurado(s)")


def get_user_role(phone: str) -> str:
    """
    Determina el rol del usuario basado en su número de teléfono.
    
    Args:
        phone: Número de teléfono
    
    Returns:
        "supervisor" o "housekeeper"
    """
    # Logging para debug
    logger.info(f"🔍 Detectando rol para: {phone}")
    logger.info(f"📋 Supervisores configurados: {SUPERVISOR_PHONES}")
    
    if phone in SUPERVISOR_PHONES:
        logger.info(f"✅ {phone} reconocido como SUPERVISOR")
        return "supervisor"
    
    logger.info(f"👷 {phone} reconocido como HOUSEKEEPER")
    return "housekeeper"


@bp.get("/webhook")
def verify():
    """
    Verificación del webhook (requerido por WhatsApp Cloud API).
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
    Webhook principal con routing por rol.
    
    Detecta si el mensaje viene de un supervisor o mucama
    y rutea al bot correspondiente.
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
        msg_type = msg.get("type")

        if not from_phone or not msg_type:
            logger.warning("⚠️ Mensaje sin from o type")
            return jsonify(ok=True), 200

        # Detectar rol del usuario
        user_role = get_user_role(from_phone)
        
        # Log informativo
        logger.info("=" * 60)
        logger.info(f"📨 MENSAJE RECIBIDO")
        logger.info(f"   📞 De: {from_phone}")
        logger.info(f"   👤 Rol: {user_role.upper()}")
        logger.info(f"   📝 Tipo: {msg_type}")

        # Preparar datos del mensaje
        message_data = {"type": msg_type}

        # CASO 1: Mensaje de texto
        if msg_type == "text":
            text = (msg.get("text") or {}).get("body", "")
            if not text:
                return jsonify(ok=True), 200
            
            message_data["text"] = text
            logger.info(f"   💬 Texto: '{text[:50]}{'...' if len(text) > 50 else ''}'")

        # CASO 2: Mensaje de audio/voz
        elif msg_type in ["audio", "voice"]:
            audio_data = msg.get("audio") or msg.get("voice") or {}
            media_id = audio_data.get("id")
            
            if not media_id:
                logger.warning("⚠️ Audio sin media_id")
                return jsonify(ok=True), 200
            
            message_data["media_id"] = media_id
            logger.info(f"   🎤 Audio ID: {media_id}")

        # CASO 3: Otros tipos (ignorar por ahora)
        else:
            logger.info(f"   ⏭️ Tipo no soportado, ignorando")
            return jsonify(ok=True), 200

        # ROUTING POR ROL
        if user_role == "supervisor":
            logger.info(f"   🎯 Ruta: BOT SUPERVISIÓN")
            
            # Supervisor: Texto + Audio
            if msg_type == "text":
                handle_supervisor_message(from_phone, message_data["text"])
            elif msg_type in ["audio", "voice"]:
                logger.info(f"   🔄 Transcribiendo audio...")
                from gateway_app.flows.housekeeping.audio_integration import transcribe_hk_audio
                
                result = transcribe_hk_audio(message_data["media_id"])
                
                if result["success"]:
                    logger.info(f"   ✅ Transcripción: '{result['text'][:50]}{'...' if len(result['text']) > 50 else ''}'")
                    send_whatsapp_text(
                        to=from_phone,
                        body=f"🎤 Escuché: \"{result['text']}\""
                    )
                    handle_supervisor_message(from_phone, result["text"])
                else:
                    logger.error(f"   ❌ Error transcripción: {result.get('error')}")
                    send_whatsapp_text(
                        to=from_phone,
                        body="❌ No pude transcribir el audio. Intenta de nuevo."
                    )
        
        else:  # housekeeper
            logger.info(f"   🎯 Ruta: BOT HOUSEKEEPING")
            handle_hk_message_with_audio(
                from_phone,
                message_data,
                show_transcription=True
            )

        logger.info(f"   ✅ Procesado correctamente")
        logger.info("=" * 60)
        return jsonify(ok=True), 200

    except Exception as e:
        logger.exception(f"❌ ERROR procesando webhook: {str(e)}")
        # Siempre retornar 200 para que WhatsApp no reintente
        return jsonify(ok=False, error=str(e)), 200