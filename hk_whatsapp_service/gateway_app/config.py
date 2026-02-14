import os

class Config:
    # WhatsApp Cloud API
    WHATSAPP_TOKEN = os.getenv("WHATSAPP_TOKEN", "")
    PHONE_NUMBER_ID = os.getenv("PHONE_NUMBER_ID", "")
    VERIFY_TOKEN = os.getenv("VERIFY_TOKEN", "")
    PORT = int(os.getenv("PORT", "10000"))
    
    # OpenAI para transcripción
    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
    TRANSCRIBE_MODEL = os.getenv("TRANSCRIBE_MODEL", "gpt-4o-mini-transcribe")
    TRANSCRIBE_PROVIDER = os.getenv("TRANSCRIBE_PROVIDER", "openai")
    
    # Alias para audio.py (mismo valor que WHATSAPP_TOKEN)
    WHATSAPP_CLOUD_TOKEN = WHATSAPP_TOKEN
    
    # Database
    DATABASE_URL = os.getenv("DATABASE_URL", "")
    
    # Admin (para endpoints protegidos)
    ADMIN_TOKEN = os.getenv("ADMIN_TOKEN", "")

cfg = Config()