# hk_whatsapp_service/app.py
from flask import Flask
from gateway_app.routes.webhook import bp as whatsapp_bp

def create_app() -> Flask:
    app = Flask(__name__)
    app.register_blueprint(whatsapp_bp)

    @app.get("/healthz")
    def healthz():
        return "ok", 200

    return app

app = create_app()
