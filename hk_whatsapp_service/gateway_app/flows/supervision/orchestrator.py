"""
Compat: algunos imports antiguos esperan gateway_app.flows.supervision.orchestrator
"""
from .orchestrator_simple import handle_supervisor_message_simple as handle_supervisor_message

__all__ = ["handle_supervisor_message"]
