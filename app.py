from flask import Flask

app = Flask(__name__)

@app.route("/")
def home():
    return "Hestia HK WhatsApp bot funcionando"

if __name__ == "__main__":
    app.run(port=5000, debug=True)

from dotenv import load_dotenv
load_dotenv()

WHATSAPP_VERIFY_TOKEN = os.getenv("WHATSAPP_VERIFY_TOKEN")

@app.route("/webhook/whatsapp", methods=["GET", "POST"])
def whatsapp_webhook():
    if request.method == "GET":
        mode = request.args.get("hub.mode")
        token = request.args.get("hub.verify_token")
        challenge = request.args.get("hub.challenge")

        if mode == "subscribe" and token == WHATSAPP_VERIFY_TOKEN:
            return challenge, 200
        return "Verification failed", 403
    
    if request.method == "POST":
        raw_body = request.get_data(as_text=True)
        print(f"[DEBUG] Raw inbound body: {raw_body}", flush=True)
        # aquí luego llamamos a tu lógica de mucamas
        return "OK", 200
