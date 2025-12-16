import os

class Config:
    WHATSAPP_TOKEN = os.getenv("WHATSAPP_TOKEN", "")
    PHONE_NUMBER_ID = os.getenv("PHONE_NUMBER_ID", "")
    VERIFY_TOKEN = os.getenv("VERIFY_TOKEN", "")
    PORT = int(os.getenv("PORT", "10000"))
