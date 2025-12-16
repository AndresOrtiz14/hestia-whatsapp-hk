import requests
from gateway_app.config import Config

GRAPH_BASE = "https://graph.facebook.com/v20.0"

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

    r = requests.post(url, headers=headers, json=payload, timeout=15)
    r.raise_for_status()
