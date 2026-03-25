# app.py
from flask import Flask
import logging
import sys
import os
from gateway_app.routes.webhook import bp as whatsapp_bp
from gateway_app.config import Config

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)

logger = logging.getLogger(__name__)


def create_app() -> Flask:
    app = Flask(__name__)

    # Render health probes hit "/" (GET/HEAD). Return 200 to avoid noisy 404 logs.
    @app.route("/", methods=["GET", "HEAD"])
    def root():
        return "ok", 200

    app.register_blueprint(whatsapp_bp)
    
    logger.info("=" * 60)
    logger.info("🚀 WhatsApp Gateway iniciado correctamente")
    logger.info(f"📡 Puerto: {Config.PORT}")
    logger.info(f"🔧 Audio transcription: {Config.TRANSCRIBE_PROVIDER}")
    logger.info("=" * 60)
    
    # ✅ EJECUTAR MIGRACIONES (con flag de seguridad)
    # Para desactivar: agregar env var SKIP_MIGRATIONS=true
    skip_migrations = os.getenv("SKIP_MIGRATIONS", "").lower() == "true"
    
    if skip_migrations:
        logger.warning("⚠️ MIGRACIONES DESACTIVADAS (SKIP_MIGRATIONS=true)")
    else:
        try:
            from gateway_app.services.migrations import run_migrations
            run_migrations()
        except Exception as e:
            logger.error(f"❌ Error en migraciones: {e}")
            logger.warning("⚠️ La app continuará, pero puede haber problemas con DB")

    # ✅ Start ticket watcher (guest → supervisor notifications)
    try:
        from gateway_app.services.ticket_watch import start_ticket_watch
        start_ticket_watch()
    except Exception as e:
        logger.error(f"❌ Error starting ticket watcher: {e}")

    return app


app = create_app()

if __name__ == "__main__":
    # En desarrollo (python app.py) el scheduler corre en el único proceso.
    # En producción (Gunicorn) lo inicia gunicorn.conf.py solo en el worker 0.
    from gateway_app.services.daily_scheduler import start_daily_scheduler
    start_daily_scheduler()
    app.run(host="0.0.0.0", port=Config.PORT, debug=True)