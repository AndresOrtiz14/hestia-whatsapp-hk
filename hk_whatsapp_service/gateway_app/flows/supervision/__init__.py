from .orchestrator_simple import handle_supervisor_message_simple

# Alias de compatibilidad para código viejo
handle_supervisor_message = handle_supervisor_message_simple

__all__ = ["handle_supervisor_message_simple", "handle_supervisor_message"]
