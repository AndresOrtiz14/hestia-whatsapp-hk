"""
Wrapper de entrada de mensajes con soporte para audio/voz.
Punto de entrada unificado que maneja texto y audio.
"""

from typing import Dict, Any
from .orchestrator_hk_multiticket import handle_hk_message_simple as _handle_hk_message_text
from .audio_integration import (
    transcribe_hk_audio,
    format_transcription_confirmation,
    format_transcription_error
)
from .outgoing import send_whatsapp


def handle_hk_message_with_audio(
    from_phone: str,
    message_data: Dict[str, Any],
    show_transcription: bool = True
) -> None:
    """
    Punto de entrada unificado para mensajes de WhatsApp (texto o audio).
    
    Args:
        from_phone: Número de teléfono del usuario
        message_data: Datos del mensaje, puede contener:
            - type: "text" | "audio" | "voice"
            - text: Contenido de texto (si type=text)
            - media_id: ID del media de WhatsApp (si type=audio/voice)
        show_transcription: Si mostrar confirmación de transcripción
    
    Ejemplos:
        # Mensaje de texto
        >>> handle_hk_message_with_audio(
        ...     "56912345678",
        ...     {"type": "text", "text": "hola"}
        ... )
        
        # Mensaje de audio (WhatsApp Cloud API format)
        >>> handle_hk_message_with_audio(
        ...     "56912345678",
        ...     {"type": "audio", "media_id": "123456789"}
        ... )
    """
    msg_type = message_data.get("type", "text")
    
    # CASO 1: Mensaje de texto (flujo normal)
    if msg_type == "text":
        text = message_data.get("text", "").strip()
        _handle_hk_message_text(from_phone, text)
        return
    
    # CASO 2: Mensaje de audio/voz
    if msg_type in ["audio", "voice"]:
        media_id = message_data.get("media_id")
        
        if not media_id:
            send_whatsapp(
                from_phone,
                "❌ No pude recibir el audio.\n"
                "Por favor intenta enviarlo de nuevo."
            )
            return
        
        # Transcribir audio usando el servicio existente
        result = transcribe_hk_audio(media_id)
        
        if not result["success"]:
            # Error en transcripción
            error_msg = format_transcription_error(result.get("error"))
            send_whatsapp(from_phone, error_msg)
            return
        
        # Transcripción exitosa
        transcribed_text = result["text"]
        
        # Opcional: Mostrar confirmación de lo que se escuchó
        if show_transcription:
            confirmation = format_transcription_confirmation(transcribed_text)
            send_whatsapp(from_phone, confirmation)
        
        # Procesar como texto normal
        _handle_hk_message_text(from_phone, transcribed_text)
        return
    
    # CASO 3: Tipo de mensaje no soportado
    send_whatsapp(
        from_phone,
        f"⚠️ Tipo de mensaje no soportado: {msg_type}\n\n"
        "Por favor envía:\n"
        "• Mensajes de texto\n"
        "• Notas de voz"
    )


# Para compatibilidad con código existente que usa handle_hk_message directamente
def handle_hk_message(from_phone: str, text: str) -> None:
    """
    Función de compatibilidad para código existente.
    Maneja solo mensajes de texto.
    
    Args:
        from_phone: Número de teléfono
        text: Texto del mensaje
    """
    _handle_hk_message_text(from_phone, text)