"""
Envío de mensajes salientes para el bot de Supervisión.
Similar a housekeeping/outgoing.py
"""

from typing import Callable

# Implementación real se inyecta desde el webhook
# Default: print para testing local
SEND_IMPL: Callable[[str, str], None] = lambda to, body: print(f"TO: {to}\n{body}\n")


def send_whatsapp(to: str, body: str) -> None:
    """
    Envía un mensaje de WhatsApp al supervisor.
    
    Args:
        to: Número de teléfono del supervisor
        body: Cuerpo del mensaje
    """
    SEND_IMPL(to, body)