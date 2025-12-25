from typing import Callable

def _real_send_whatsapp(to: str, body: str) -> None:
    """
    En producción esto enviaría un WhatsApp (Meta/WhatsApp API).
    Por ahora, dejamos un fallback a consola.
    """
    print(f"[FAKE SEND] → {to}: {body}")

# Esta es la “implementación” que se puede reemplazar desde el simulador
SEND_IMPL: Callable[[str, str], None] = _real_send_whatsapp

def send_whatsapp(to: str, body: str) -> None:
    """
    Wrapper estable: siempre llama a SEND_IMPL.
    En el simulador, cambiamos SEND_IMPL para interceptar todos los envíos.
    """
    return SEND_IMPL(to, body)
