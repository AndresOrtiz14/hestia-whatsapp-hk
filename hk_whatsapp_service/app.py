# app.py
from flask import Flask
import logging
import sys
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
    
    return app


app = create_app()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=Config.PORT, debug=True)