# gateway_app/routes/webhook.py
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Tuple

from flask import Blueprint, jsonify, request

from gateway_app.config import Config
from gateway_app.services.whatsapp_client import send_whatsapp_text
from gateway_app.flows.housekeeping_flows import hk_handle_incoming

logger = logging.getLogger(__name__)

bp = Blueprint("whatsapp_webhook", __name__)

def _parse_inbound(payload: Dict[str, Any]) -> Tuple[
    Optional[str],  # wa_id
    Optional[str],  # from_number
    Optional[str],  # guest_name
    Dict[str, Any],  # msg_data (may be {})
]:
    """
    Extract basic fields from a WhatsApp Cloud API webhook payload.
    Returns (wa_id, from_number, guest_name, info)
    """
    try:
        entry = (payload.get("entry") or [])[0]
        change = (entry.get("changes") or [])[0]
        value = change.get("value") or {}
    except Exception:
        return None, None, None, {}

    contacts = value.get("contacts") or []
    wa_id = None
    guest_name = None
    if contacts:
        contact = contacts[0]
        wa_id = contact.get("wa_id") or contact.get("id")
        profile = contact.get("profile") or {}
        guest_name = profile.get("name")

    messages = value.get("messages") or []
    if not messages:
        return wa_id, None, guest_name, {"value": value}

    msg = messages[0]
    from_number = msg.get("from")
    msg_type = msg.get("type")

    return wa_id or from_number, from_number, guest_name, {
        "msg": msg,
        "value": value,
        "type": msg_type,
    }

@bp.route("/webhook", methods=["GET", "POST"], strict_slashes=False)
def whatsapp_webhook():
    # -----------------------------
    # 1) Verification handshake (GET)
    # -----------------------------
    if request.method == "GET":
        mode = request.args.get("hub.mode")
        token = request.args.get("hub.verify_token")
        challenge = request.args.get("hub.challenge")

        expected = (Config.VERIFY_TOKEN or "").strip()
        logger.info(
            "[WEBHOOK] GET verify mode=%s token_match=%s expected_set=%s",
            mode,
            token == expected,
            bool(expected),
        )

        if mode == "subscribe" and token == expected and challenge:
            return challenge, 200
        return "Verification failed", 403

    # -----------------------------
    # 2) Incoming messages (POST)
    # -----------------------------
    raw_body = request.get_data(as_text=True)
    logger.info("[WEBHOOK] POST raw=%s", raw_body)

    data = request.get_json(force=True, silent=True) or {}
    wa_id, from_number, guest_name, info = _parse_inbound(data)

    if not from_number:
        logger.info("[WEBHOOK] No user message in payload; ack as status/other.")
        return jsonify({"status": "ignored", "reason": "no_message"}), 200

    msg = info.get("msg") or {}
    msg_type = info.get("type")
    msg_id = msg.get("id")
    timestamp_str = msg.get("timestamp")

    # parse timestamp
    try:
        ts = (
            datetime.fromtimestamp(int(timestamp_str), tz=timezone.utc)
            if timestamp_str else datetime.now(timezone.utc)
        )
    except Exception:
        ts = datetime.now(timezone.utc)

    text = ""
    if msg_type == "text":
        text = (msg.get("text") or {}).get("body") or ""

    logger.info(
        "[WEBHOOK] Parsed inbound wa_id=%s from=%s name=%s type=%s text=%r ts=%s msg_id=%s",
        wa_id,
        from_number,
        guest_name,
        msg_type,
        text,
        ts.isoformat(),
        msg_id,
    )

    if msg_type == "text" and from_number and text:
        hk_handle_incoming(
            from_phone=from_number,
            text=text,
            send=lambda to, body: send_whatsapp_text(to=to, body=body),
        )

    return jsonify({"status": "ok"}), 200

@bp.route("/webhook/test", methods=["POST"], strict_slashes=False)
def webhook_test():
    """
    Simulator endpoint:
    POST /webhook/test
    { "phone": "4915...", "text": "hola" }
    """
    data = request.get_json(force=True, silent=True) or {}
    phone = data.get("phone")
    text = data.get("text", "")

    if not phone:
        return jsonify({"error": "phone is required"}), 400
    if not text:
        return jsonify({"error": "text is required"}), 400

    captured = []
    def fake_send(to: str, body: str):
        captured.append({"to": to, "body": body})

    hk_handle_incoming(from_phone=phone, text=text, send=fake_send)

    return jsonify({"status": "ok", "outbound": captured}), 200
