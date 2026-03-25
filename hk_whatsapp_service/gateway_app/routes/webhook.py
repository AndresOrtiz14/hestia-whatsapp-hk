"""
Webhook de WhatsApp con routing por rol (Supervisor vs Mucama).
"""

from flask import Blueprint, request, jsonify
import logging

from gateway_app.config import Config
from gateway_app.services.whatsapp_client import send_whatsapp_text

bp = Blueprint("whatsapp_webhook", __name__)
logger = logging.getLogger(__name__)

# Wire up WhatsApp sender para ambos bots (re-wired per-request con tenant.wa_token)
import gateway_app.flows.housekeeping.outgoing as hk_outgoing
import gateway_app.flows.supervision.outgoing as sup_outgoing

# Import handlers
from gateway_app.flows.housekeeping.message_handler import handle_hk_message_with_audio
from gateway_app.flows.supervision import handle_supervisor_message

import os

from gateway_app.services.wamid_cache import is_duplicate_wamid


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
def inbound_updated():
    """
    Webhook principal con routing por rol.
    VERSIÓN ACTUALIZADA con soporte para imágenes y videos.
    """
    payload = request.get_json(silent=True) or {}

    # Resolver tenant a partir del phone_number_id del webhook
    phone_number_id = (
        payload.get("entry", [{}])[0]
               .get("changes", [{}])[0]
               .get("value", {})
               .get("metadata", {})
               .get("phone_number_id", "")
    )
    from gateway_app.services.tenant_resolver import resolve_tenant
    tenant = resolve_tenant(phone_number_id)
    if not tenant:
        logger.warning(
            "webhook: phone_number_id=%s sin property configurada, ignorando",
            phone_number_id,
        )
        return jsonify(ok=True), 200

    # Wire outgoing con el token de este tenant
    _wa_token = tenant.wa_token or None
    hk_outgoing.SEND_IMPL = lambda to, body: send_whatsapp_text(to=to, body=body, token=_wa_token)
    sup_outgoing.SEND_IMPL = lambda to, body: send_whatsapp_text(to=to, body=body, token=_wa_token)

    try:
        entry = payload["entry"][0]
        change = entry["changes"][0]
        value = change["value"]
        messages = value.get("messages", [])

        if not messages:
            return jsonify(ok=True), 200

        msg = messages[0]
        
        # ✅ DEDUPE: ignorar retries/redelivery de Meta
        wamid = msg.get("id")
        if is_duplicate_wamid(wamid):
            return jsonify(ok=True), 200
        
        from_phone = msg.get("from")
        msg_type = msg.get("type")

        if not from_phone or not msg_type:
            logger.warning("⚠️ Mensaje sin from o type")
            return jsonify(ok=True), 200

        # Detectar rol del usuario via tenant
        from gateway_app.services.workers_db import obtener_supervisores_por_area
        _sups = obtener_supervisores_por_area("", property_id=tenant.property_id)
        _sup_phones = {s["telefono"] for s in _sups if s.get("telefono")}
        user_role = "supervisor" if from_phone in _sup_phones else "housekeeper"
        
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

        # ✅ CASO 3: Mensaje de imagen
        elif msg_type == "image":
            image_data = msg.get("image") or {}
            media_id = image_data.get("id")
            caption = image_data.get("caption", "")
            
            if not media_id:
                logger.warning("⚠️ Imagen sin media_id")
                return jsonify(ok=True), 200
            
            message_data["media_id"] = media_id
            message_data["caption"] = caption
            logger.info(f"   📸 Imagen ID: {media_id} | Caption: '{caption[:30] if caption else '(sin caption)'}'")

        # ✅ CASO 4: Mensaje de video
        elif msg_type == "video":
            video_data = msg.get("video") or {}
            media_id = video_data.get("id")
            caption = video_data.get("caption", "")
            
            if not media_id:
                logger.warning("⚠️ Video sin media_id")
                return jsonify(ok=True), 200
            
            message_data["media_id"] = media_id
            message_data["caption"] = caption
            logger.info(f"   🎥 Video ID: {media_id} | Caption: '{caption[:30] if caption else '(sin caption)'}'")

        # CASO 5: Otros tipos (ignorar)
        else:
            logger.info(f"   ⏭️ Tipo '{msg_type}' no soportado, ignorando")
            return jsonify(ok=True), 200

        # ROUTING POR ROL
        if user_role == "supervisor":
            logger.info(f"   🎯 Ruta: BOT SUPERVISIÓN")
            
            # Supervisor: Texto
            if msg_type == "text":
                try:
                    handle_supervisor_message(from_phone, message_data["text"], tenant=tenant)
                except Exception as e:
                    logger.exception("❌ ERROR procesando webhook: %s", e)
                return jsonify(ok=True), 200

            # Supervisor: Audio
            elif msg_type in ["audio", "voice"]:
                logger.info(f"   🔄 Transcribiendo audio...")
                from gateway_app.flows.housekeeping.audio_integration import transcribe_hk_audio

                result = transcribe_hk_audio(message_data["media_id"])

                if result["success"]:
                    logger.info(f"   ✅ Transcripción: '{result['text'][:50]}...'")
                    send_whatsapp_text(
                        to=from_phone,
                        body=f"🎤 Escuché: \"{result['text']}\"",
                        token=_wa_token,
                    )
                    handle_supervisor_message(from_phone, result["text"], tenant=tenant)
                else:
                    logger.error(f"   ❌ Error transcripción: {result.get('error')}")
                    send_whatsapp_text(
                        to=from_phone,
                        body="❌ No pude transcribir el audio. Intenta de nuevo.",
                        token=_wa_token,
                    )

            # ✅ Supervisor: Imagen/Video (opcional - crear tickets)
            elif msg_type in ["image", "video"]:
                from gateway_app.flows.housekeeping.media_handler import handle_media_message
                handle_media_message(
                    from_phone=from_phone,
                    media_id=message_data["media_id"],
                    media_type=msg_type,
                    caption=message_data.get("caption"),
                    tenant=tenant,
                )
        
        else:  # housekeeper
            logger.info(f"   🎯 Ruta: BOT HOUSEKEEPING")
            
            # ✅ NUEVO: Manejar imágenes y videos
            if msg_type in ["image", "video"]:
                from gateway_app.flows.housekeeping.media_handler import handle_media_message

                handle_media_message(
                    from_phone=from_phone,
                    media_id=message_data["media_id"],
                    media_type=msg_type,
                    caption=message_data.get("caption"),
                    tenant=tenant,
                )
            else:
                # Texto y audio se manejan con el handler existente
                handle_hk_message_with_audio(
                    from_phone,
                    message_data,
                    show_transcription=True,
                    tenant=tenant,
                )

        logger.info(f"   ✅ Procesado correctamente")
        logger.info("=" * 60)
        return jsonify(ok=True), 200
        
    
    except Exception as e:
        raise

@bp.route("/db-status", methods=["GET"])
def db_status():
    """
    Endpoint para verificar estado de la base de datos.
    Muestra qué tablas existen y su contenido.
    Requiere ADMIN_TOKEN como query param.
    """
    # ✅Proteger con token
    admin_token = os.getenv("ADMIN_TOKEN", "")
    provided_token = request.args.get("token", "")
    if not admin_token or provided_token != admin_token:
        return jsonify({"error": "unauthorized"}), 403

    from gateway_app.services.db import fetchall, fetchone, using_pg
    
    status = {
        "database_type": "PostgreSQL (Supabase)" if using_pg() else "SQLite",
        "tables": {},
        "errors": []
    }
    
    try:
        # Listar todas las tablas
        if using_pg():
            tables_sql = """
                SELECT table_name 
                FROM information_schema.tables 
                WHERE table_schema = 'public'
                ORDER BY table_name
            """
        else:
            tables_sql = """
                SELECT name as table_name 
                FROM sqlite_master 
                WHERE type='table'
                ORDER BY name
            """
        
        tables = fetchall(tables_sql)
        
        for table in tables:
            table_name = table['table_name']
            
            # Ignorar tablas del sistema
            if table_name.startswith('_') or table_name in ['spatial_ref_sys']:
                continue
            
            try:
                # Contar registros
                count_sql = f"SELECT COUNT(*) as count FROM {table_name}"
                count_result = fetchone(count_sql)
                count = count_result['count'] if count_result else 0
                
                # Obtener columnas
                if using_pg():
                    columns_sql = f"""
                        SELECT column_name, data_type 
                        FROM information_schema.columns 
                        WHERE table_name = '{table_name}'
                        ORDER BY ordinal_position
                    """
                else:
                    columns_sql = f"PRAGMA table_info({table_name})"
                
                columns = fetchall(columns_sql)
                
                status["tables"][table_name] = {
                    "exists": True,
                    "row_count": count,
                    "columns": [
                        col.get('column_name') or col.get('name') 
                        for col in columns
                    ]
                }
                
            except Exception as e:
                status["tables"][table_name] = {
                    "exists": True,
                    "error": str(e)
                }
        
        # Verificar tabla específica 'tickets'
        tickets_exists = 'tickets' in status["tables"]
        
        if tickets_exists:
            # Obtener algunos ejemplos
            try:
                sample_sql = "SELECT * FROM tickets ORDER BY created_at DESC LIMIT 3"
                samples = fetchall(sample_sql)
                status["tables"]["tickets"]["sample_records"] = samples
            except Exception as e:
                status["errors"].append(f"Error obteniendo ejemplos: {e}")
        
        # Verificar tabla 'runtime_sessions'
        runtime_sessions_exists = 'runtime_sessions' in status["tables"]
        
        status["summary"] = {
            "total_tables": len(status["tables"]),
            "tickets_table_exists": tickets_exists,
            "runtime_sessions_exists": runtime_sessions_exists,
            "ready_for_migrations": not tickets_exists
        }
        
    except Exception as e:
        status["errors"].append(f"Error general: {str(e)}")
        logger.exception("Error en db-status")
    
    return jsonify(status), 200


@bp.route("/health", methods=["GET"])
def health_check():
    """
    Endpoint de health check para monitoreo.
    """
    import os
    
    whatsapp_token_configured = bool(os.getenv("WHATSAPP_TOKEN"))
    openai_key_configured = bool(os.getenv("OPENAI_API_KEY"))
    database_configured = bool(os.getenv("DATABASE_URL"))
    
    return jsonify({
        "status": "healthy",
        "whatsapp_configured": whatsapp_token_configured,
        "audio_support": openai_key_configured,
        "database_configured": database_configured,
        "bots": ["housekeeping", "supervision"],
        "message": "WhatsApp Multi-Bot is running"
    }), 200