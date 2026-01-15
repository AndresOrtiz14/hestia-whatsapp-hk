# Importar lo que tengas disponible
try:
    from .orchestrator_simple import handle_supervisor_message_simple
    handle_supervisor_message = handle_supervisor_message_simple
except ImportError:
    # Fallback al original si el simple no existe
    from .orchestrator import handle_supervisor_message

# Alias de compatibilidad para código viejo
handle_supervisor_message = handle_supervisor_message_simple

__all__ = ["handle_supervisor_message_simple", "handle_supervisor_message"]

# Notificaciones
try:
    from .orchestrator_simple import (
        notify_new_ticket_from_guest,
        notify_ticket_completed,
        notify_ticket_delayed
    )
except ImportError:
    # Dummy functions si no existen
    def notify_new_ticket_from_guest(*args, **kwargs): pass
    def notify_ticket_completed(*args, **kwargs): pass
    def notify_ticket_delayed(*args, **kwargs): pass

__all__ = [
    'handle_supervisor_message',
    'notify_new_ticket_from_guest',
    'notify_ticket_completed',
    'notify_ticket_delayed',
]