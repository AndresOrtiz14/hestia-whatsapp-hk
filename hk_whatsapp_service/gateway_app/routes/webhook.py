from flask import Blueprint, request, jsonify
from gateway_app.config import Config
from gateway_app.services.whatsapp_client import send_whatsapp_text
from gateway_app.flows.housekeeping_flows import hk_handle_incoming

bp = Blueprint("whatsapp_webhook", __name__)

@bp.get("/webhook")
def verify():
    mode = request.args.get("hub.mode")
    token = request.args.get("hub.verify_token")
    challenge = request.args.get("hub.challenge")

    if mode == "subscribe" and token == Config.VERIFY_TOKEN:
        return challenge, 200
    return "Forbidden", 403


@bp.post("/webhook")
def inbound():
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
        text = (msg.get("text") or {}).get("body", "")

        if from_phone and text:
            hk_handle_incoming(
                from_phone=from_phone,
                text=text,
                send=lambda to, body: send_whatsapp_text(to=to, body=body),
            )

        return jsonify(ok=True), 200

    except Exception as e:
        return jsonify(ok=False, error=str(e)), 500
