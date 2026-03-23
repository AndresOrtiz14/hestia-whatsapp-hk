"""
Envío de mensajes salientes para el bot de Supervisión.
Similar a housekeeping/outgoing.py
"""

import logging
from typing import Callable

from gateway_app.core.utils.message_constants import msg_notif_ticket_a_supervisor
from gateway_app.services.whatsapp_client import send_whatsapp_text

logger = logging.getLogger(__name__)

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


def notificar_supervisor_de_area(
    area: str,
    ticket_id: int,
    ubicacion: str,
    detalle: str,
    prioridad: str,
    creado_por_phone: str = "",
    property_id: str = "",
) -> None:
    from gateway_app.services.workers_db import obtener_supervisores_por_area

    supervisores = obtener_supervisores_por_area(area, property_id=property_id)
    phones = [s["telefono"] for s in supervisores if s.get("telefono")]
    phones = [p for p in phones if p != creado_por_phone]

    if not phones:
        logger.warning(
            "notificar_supervisor_de_area: sin destinatarios para area='%s' property='%s'",
            area, property_id,
        )
        return

    mensaje = msg_notif_ticket_a_supervisor(
        ticket_id=ticket_id,
        ubicacion=ubicacion,
        detalle=detalle,
        prioridad=prioridad,
        area=area,
        creado_por_phone=creado_por_phone,
    )

    for phone in phones:
        try:
            send_whatsapp_text(to=phone, body=mensaje)
        except Exception as exc:
            logger.error(
                "notificar_supervisor_de_area: fallo al enviar a %s: %s", phone, exc
            )