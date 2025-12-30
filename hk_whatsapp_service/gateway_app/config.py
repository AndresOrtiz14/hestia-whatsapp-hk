"""
Configuración actualizada con soporte para audio/transcripción.
"""

import os

class Config:
    # WhatsApp Cloud API (existentes)
    WHATSAPP_TOKEN = os.getenv("WHATSAPP_TOKEN", "")
    PHONE_NUMBER_ID = os.getenv("PHONE_NUMBER_ID", "")
    VERIFY_TOKEN = os.getenv("VERIFY_TOKEN", "")
    PORT = int(os.getenv("PORT", "10000"))
    
    # NUEVO: OpenAI para transcripción de audio
    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
    
    # NUEVO (Opcional): Modelo de transcripción
    # Opciones: "whisper-1" (clásico) o "gpt-4o-mini-transcribe" (más moderno)
    TRANSCRIBE_MODEL = os.getenv("TRANSCRIBE_MODEL", "gpt-4o-mini-transcribe")
    
    # NUEVO (Opcional): Proveedor de transcripción
    TRANSCRIBE_PROVIDER = os.getenv("TRANSCRIBE_PROVIDER", "openai")
    
    # Alias para compatibilidad con services/audio.py
    # (Tu audio.py usa WHATSAPP_CLOUD_TOKEN)
    WHATSAPP_CLOUD_TOKEN = WHATSAPP_TOKEN

    # CRÍTICO: Crear instancia 'cfg' para que audio.py pueda importarla
    cfg = Config()