# app.py
import logging
from flask import Flask
from gateway_app.routes.webhook import bp as whatsapp_bp
from gateway_app.config import Config

logging.basicConfig(level=logging.INFO)

def create_app() -> Flask:
    app = Flask(__name__)
    app.register_blueprint(whatsapp_bp)

    @app.get("/")
    def home():
        return "Hestia HK WhatsApp bot funcionando", 200

    @app.get("/healthz")
    def healthz():
        return "ok", 200

    return app

app = create_app()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=Config.PORT, debug=True)
