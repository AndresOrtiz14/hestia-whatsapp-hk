# gateway_app/flows/housekeeping/__init__.py

"""
Bot de Housekeeping - Versión Simplificada
"""

# Exportar función principal (con soporte de audio)
from .message_handler import handle_hk_message_with_audio

# Exportar versión simple directa (solo texto)
from .orchestrator_hk_multiticket import handle_hk_message_simple

# Alias para compatibilidad con código existente
handle_hk_message = handle_hk_message_simple

# Exportar funciones de audio
from .audio_integration import (
    transcribe_hk_audio,
    format_transcription_confirmation,
    format_transcription_error
)

__all__ = [
    # Función principal (recomendada para webhook)
    'handle_hk_message_with_audio',
    
    # Función simple (solo texto)
    'handle_hk_message_simple',
    'handle_hk_message',  # Alias
    
    # Funciones de audio
    'transcribe_hk_audio',
    'format_transcription_confirmation',
    'format_transcription_error',
]