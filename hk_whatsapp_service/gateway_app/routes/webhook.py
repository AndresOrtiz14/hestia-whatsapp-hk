"""
Webhook de WhatsApp con routing por rol (Supervisor vs Mucama).
"""

from flask import Blueprint, request, jsonify
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

from gateway_app.services.db import fetchone, execute, using_pg

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

def is_duplicate_wamid(wamid: str) -> bool:
    """
    Retorna True si ya habíamos procesado este mensaje (dedupe por wamid).
    Inserta el wamid en runtime_wamids si es primera vez.
    """
    if not wamid:
        return False

    try:
        if using_pg():
            # Si inserta -> retorna fila; si ya existía -> retorna None
            row = fetchone(
                """
                INSERT INTO public.runtime_wamids (id)
                VALUES (?)
                ON CONFLICT (id) DO NOTHING
                RETURNING id
                """,
                (wamid,),
            )
            return row is None
        else:
            # SQLite fallback (sin RETURNING)
            row = fetchone("SELECT id FROM runtime_wamids WHERE id = ?", (wamid,))
            if row:
                return True
            execute("INSERT INTO runtime_wamids (id) VALUES (?)", (wamid,))
            return False

    except Exception:
        logger.exception("⚠️ Error deduplicando wamid=%s (continuando sin dedupe)", wamid)
        return False


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
    wamid = None  # Para dedupe y manejo de errores
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
                try:
                    handle_supervisor_message(from_phone, message_data["text"])
                except Exception as e:
                    logger.exception("❌ ERROR procesando webhook (pero respondo 200 para evitar retries): %s", e)
                    # Opcional: avisar al supervisor
                    # send_whatsapp(from_phone, "⚠️ Ocurrió un error interno. Intenta de nuevo.")
                return jsonify(ok=True), 200

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
        # permitir reintento si falló el procesamiento
        if wamid:
            from gateway_app.services.db import execute
            execute("DELETE FROM public.runtime_wamids WHERE id = ?", (wamid,), commit=True)
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