from flask import Flask
from gateway_app.routes.webhook import bp as whatsapp_bp
from gateway_app.config import Config

def create_app() -> Flask:
    app = Flask(__name__)
    app.register_blueprint(whatsapp_bp)
    return app

app = create_app()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=Config.PORT, debug=True)
