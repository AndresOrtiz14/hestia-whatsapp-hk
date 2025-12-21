from typing import Dict, Any
from datetime import datetime, timedelta

# =========================
#   DEMO TICKETS
# =========================

DEMO_TICKETS = [
    {
        "id": 1010,
        "room": "312",
        "detalle": "Toallas adicionales",
        "prioridad": "MEDIA",
        "created_at": datetime.now() - timedelta(minutes=35),
        "esfuerzo": "FACIL",
    },
    {
        "id": 1011,
        "room": "221",
        "detalle": "Limpieza rápida",
        "prioridad": "ALTA",
        "created_at": datetime.now() - timedelta(minutes=10),
        "esfuerzo": "MEDIO",
    },
]

PRIORIDAD_PESO = {"ALTA": 100, "MEDIA": 60, "BAJA": 30}
ESFUERZO_PESO = {"FACIL": 25, "MEDIO": 10, "DIFICIL": 0}

def score_ticket(t: Dict[str, Any]) -> float:
    p = PRIORIDAD_PESO.get((t.get("prioridad") or "").upper(), 0)
    created_at = t.get("created_at")
    if isinstance(created_at, datetime):
        age_min = (datetime.now() - created_at).total_seconds() / 60.0
    else:
        age_min = 0.0
    e = ESFUERZO_PESO.get((t.get("esfuerzo") or "MEDIO").upper(), 10)
    return (p * 1.0) + (age_min * 0.8) + (e * 1.0)

def elegir_mejor_ticket(tickets: list[Dict[str, Any]]) -> Dict[str, Any] | None:
    if not tickets:
        return None
    return max(tickets, key=score_ticket)

def mock_listado_tickets_por_resolver() -> str:
    lines = ["Tickets por resolver (demo):"]
    ordered = sorted(DEMO_TICKETS, key=score_ticket, reverse=True)

    for t in ordered:
        created_at = t.get("created_at")
        if isinstance(created_at, datetime):
            age_min = int((datetime.now() - created_at).total_seconds() / 60)
            age_txt = f"hace {age_min} min"
        else:
            age_txt = "sin hora"

        esfuerzo = t.get("esfuerzo", "MEDIO")
        lines.append(
            f"- #{t['id']} / Hab. {t['room']} / {t['detalle']} / prioridad {t['prioridad']} / {age_txt} / {esfuerzo}"
        )

    lines.append(
        "\nPuedes responder por ejemplo:\n"
        "- 'aceptar' / 'tomar ticket' / 'ok lo tomo'\n"
        "- 'rechazar' / 'derivar'\n"
        "O escribir el ID: '#1011' para elegir uno específico."
    )
    return "\n".join(lines)
