from typing import Callable, Optional

SEND_IMPL: Optional[Callable[[str, str], None]] = None


def send_whatsapp(to: str, body: str) -> None:
    """
    En producción: aquí va el envío real (WhatsApp API).
    En simulador: se setea outgoing.SEND_IMPL = send_whatsapp_cli
    """
    if SEND_IMPL is not None:
        SEND_IMPL(to, body)
        return

    print(f"[FAKE SEND] → {to}: {body}")
