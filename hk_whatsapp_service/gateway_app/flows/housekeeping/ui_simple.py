from typing import Dict, Any

# =========================
#   HELPERS DE TEXTO
# =========================

def recordatorio_menu() -> str:
    """
    Recordatorio consistente para volver al menú.
    Se agrega al final de todos los mensajes no-menú.
    """
    return "\n\n💡 Escribe 'M' para ver el menú."


def texto_menu_principal(state: Dict[str, Any]) -> str:
    linea_turno = "🟢 Turno ACTIVO" if state["turno_activo"] else "⚪️ Sin turno activo"
    opcion_turno = "1) Iniciar turno" if not state["turno_activo"] else "1) Finalizar turno"

    return (
        f"{linea_turno}\n\n"
        "🏨 Menú Housekeeping\n"
        f"{opcion_turno}\n"
        "2) Tickets por resolver\n"
        "3) Crear ticket / reportar problema\n"
        "4) Ayuda / contactar supervisor\n\n"
        "Escribe el número de opción o 'M' para ver este menú de nuevo."
    )