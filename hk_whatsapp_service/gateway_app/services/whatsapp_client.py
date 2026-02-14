import requests
from gateway_app.config import Config

GRAPH_BASE = "https://graph.facebook.com/v20.0"

import logging
logger = logging.getLogger(__name__)


def send_whatsapp_text(*, to: str, body: str) -> None:
    if not Config.WHATSAPP_TOKEN or not Config.PHONE_NUMBER_ID:
        raise RuntimeError("Missing WhatsApp env vars")

    url = f"{GRAPH_BASE}/{Config.PHONE_NUMBER_ID}/messages"
    headers = {
        "Authorization": f"Bearer {Config.WHATSAPP_TOKEN}",
        "Content-Type": "application/json",
    }
    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "text",
        "text": {"body": body},
    }

    logger.info("WA_SEND to=%s body_preview=%r", to, body[:120])

    r = requests.post(url, headers=headers, json=payload, timeout=15)

    logger.info("WA_SEND_RESP to=%s status=%s", to, r.status_code)

    r.raise_for_status()

def send_whatsapp_image(
    to: str,
    media_id: str = None,
    image_url: str = None,
    caption: str = ""
) -> dict:
    """
    Envía una imagen por WhatsApp.
    
    Puede enviar usando:
    - media_id: ID de un media ya subido a WhatsApp (más rápido, no expira durante la sesión)
    - image_url: URL pública de una imagen (WhatsApp la descarga)
    
    Args:
        to: Número de teléfono destino
        media_id: ID del media de WhatsApp (preferido)
        image_url: URL pública de la imagen (alternativa)
        caption: Texto que acompaña la imagen
    
    Returns:
        {"success": True, "message_id": str} o {"success": False, "error": str}
    """
    import requests
    from gateway_app.config import Config
    
    if not media_id and not image_url:
        return {"success": False, "error": "Se requiere media_id o image_url"}
    
    url = f"https://graph.facebook.com/v18.0/{Config.PHONE_NUMBER_ID}/messages"
    
    headers = {
        "Authorization": f"Bearer {Config.WHATSAPP_TOKEN}",
        "Content-Type": "application/json"
    }
    
    # Construir payload según el tipo de media
    if media_id:
        image_payload = {"id": media_id}
    else:
        image_payload = {"link": image_url}
    
    if caption:
        image_payload["caption"] = caption
    
    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": to,
        "type": "image",
        "image": image_payload
    }
    
    try:
        logger.info(f"📤 Enviando imagen a {to}")
        response = requests.post(url, headers=headers, json=payload, timeout=30)
        
        if response.status_code == 200:
            result = response.json()
            message_id = result.get("messages", [{}])[0].get("id")
            logger.info(f"✅ Imagen enviada a {to}: {message_id}")
            return {"success": True, "message_id": message_id}
        else:
            logger.error(f"❌ Error enviando imagen: {response.status_code} - {response.text}")
            return {"success": False, "error": response.text}
            
    except Exception as e:
        logger.exception(f"❌ Error enviando imagen: {e}")
        return {"success": False, "error": str(e)}


def send_whatsapp_video(
    to: str,
    media_id: str = None,
    video_url: str = None,
    caption: str = ""
) -> dict:
    """
    Envía un video por WhatsApp.
    
    Args:
        to: Número de teléfono destino
        media_id: ID del media de WhatsApp
        video_url: URL pública del video
        caption: Texto que acompaña el video
    
    Returns:
        {"success": True, "message_id": str} o {"success": False, "error": str}
    """
    import requests
    from gateway_app.config import Config
    
    if not media_id and not video_url:
        return {"success": False, "error": "Se requiere media_id o video_url"}
    
    url = f"https://graph.facebook.com/v18.0/{Config.PHONE_NUMBER_ID}/messages"
    
    headers = {
        "Authorization": f"Bearer {Config.WHATSAPP_TOKEN}",
        "Content-Type": "application/json"
    }
    
    if media_id:
        video_payload = {"id": media_id}
    else:
        video_payload = {"link": video_url}
    
    if caption:
        video_payload["caption"] = caption
    
    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": to,
        "type": "video",
        "video": video_payload
    }
    
    try:
        logger.info(f"📤 Enviando video a {to}")
        response = requests.post(url, headers=headers, json=payload, timeout=30)
        
        if response.status_code == 200:
            result = response.json()
            message_id = result.get("messages", [{}])[0].get("id")
            logger.info(f"✅ Video enviado a {to}: {message_id}")
            return {"success": True, "message_id": message_id}
        else:
            logger.error(f"❌ Error enviando video: {response.status_code} - {response.text}")
            return {"success": False, "error": response.text}
            
    except Exception as e:
        logger.exception(f"❌ Error enviando video: {e}")
        return {"success": False, "error": str(e)}

