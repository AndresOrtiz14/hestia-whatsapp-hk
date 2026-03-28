"""
Integración de audio para Housekeeping.
Wrapper sobre gateway_app.services.audio para el flujo de trabajadores.
"""

import logging
from typing import Dict, Any, Optional

# Importar servicio de audio compartido
from gateway_app.services.audio import transcribe_whatsapp_audio

logger = logging.getLogger(__name__)


def transcribe_hk_audio(media_id: str, token: Optional[str] = None) -> Dict[str, Any]:
    """
    Transcribe un audio de WhatsApp para el flujo de Housekeeping.
    
    Args:
        media_id: ID del media de WhatsApp (viene en el webhook)
    
    Returns:
        {
            "success": bool,
            "text": str,              # Transcripción
            "error": str | None
        }
    
    Ejemplo:
        >>> result = transcribe_hk_audio("media_123")
        >>> if result["success"]:
        ...     print(result["text"])
        ...     # "habitación 305 necesita toallas"
    """
    if not media_id:
        return {
            "success": False,
            "text": "",
            "error": "media_id vacío"
        }
    
    try:
        # Usar el servicio compartido de audio
        # (ya maneja descarga, transcripción y limpieza)
        text = transcribe_whatsapp_audio(media_id, language="es", token=token)
        
        if not text:
            return {
                "success": False,
                "text": "",
                "error": "Transcripción vacía (audio sin contenido audible)"
            }
        
        if len(text) < 2:
            return {
                "success": False,
                "text": text,
                "error": "Transcripción muy corta (audio muy breve o poco claro)"
            }
        
        logger.info(
            "Audio transcrito exitosamente para HK",
            extra={"media_id": media_id, "text_length": len(text)}
        )
        
        return {
            "success": True,
            "text": text,
            "error": None
        }
        
    except Exception as e:
        logger.exception("Error transcribiendo audio HK (media_id=%s)", media_id)
        return {
            "success": False,
            "text": "",
            "error": f"Error de transcripción: {str(e)}"
        }


def format_transcription_confirmation(text: str) -> str:
    """
    Formatea mensaje de confirmación de transcripción para el usuario.
    
    Args:
        text: Texto transcrito
    
    Returns:
        Mensaje formateado para WhatsApp
    
    Ejemplo:
        >>> msg = format_transcription_confirmation("habitación 305 necesita toallas")
        >>> print(msg)
        🎤 Escuché: "habitación 305 necesita toallas"
    """
    return f'🎤 Escuché: "{text}"'


def format_transcription_error(error: Optional[str] = None) -> str:
    """
    Formatea mensaje de error amigable para el usuario.
    
    Args:
        error: Mensaje de error técnico (opcional)
    
    Returns:
        Mensaje de error user-friendly
    """
    if error and "vacía" in error.lower():
        return (
            "❌ No pude escuchar nada en el audio.\n\n"
            "Por favor intenta:\n"
            "• Grabar más cerca del micrófono\n"
            "• Hablar más fuerte\n"
            "• Verificar que el micrófono funcione"
        )
    
    if error and "muy corta" in error.lower():
        return (
            "⚠️ El audio es muy corto.\n\n"
            "Por favor graba un mensaje más largo\n"
            "o escribe lo que necesitas."
        )
    
    # Error genérico
    return (
        "❌ No pude procesar el audio.\n\n"
        "Por favor intenta:\n"
        "• Enviar el audio de nuevo\n"
        "• O escribir tu mensaje"
    )