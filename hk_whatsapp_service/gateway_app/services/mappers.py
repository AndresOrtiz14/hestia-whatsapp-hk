# gateway_app/services/mappers.py
"""
Traduce entre los valores que usa el bot Flask y los que espera/devuelve el NestJS.
Fuente única de verdad para todos los mapeos de dominio.
"""
import re
from typing import Optional


def _build_phone(prefix: str, number: str) -> str:
    """Construye número completo normalizado desde prefix y number."""
    prefix_clean = re.sub(r"\D", "", prefix or "")
    number_clean = re.sub(r"\D", "", number or "")
    if not number_clean:
        return ""
    # Evitar duplicar el prefijo si number ya lo incluye
    if number_clean.startswith(prefix_clean) and len(number_clean) > 9:
        return number_clean
    return prefix_clean + number_clean


# ── Estados ───────────────────────────────────────────────────────────────────
STATUS_TO_NESTJS = {
    "PENDIENTE":  "open",
    "ASIGNADO":   "assigned",
    "EN_CURSO":   "in_progress",
    "PAUSADO":    "blocked",
    "RESUELTO":   "finished",
    "COMPLETADO": "closed",
}
STATUS_FROM_NESTJS = {v: k for k, v in STATUS_TO_NESTJS.items()}

# ── Prioridades ───────────────────────────────────────────────────────────────
PRIORITY_TO_NESTJS = {
    "URGENTE": "critical",
    "ALTA":    "high",
    "MEDIA":   "medium",
    "BAJA":    "low",
}
PRIORITY_FROM_NESTJS = {v: k for k, v in PRIORITY_TO_NESTJS.items()}

# ── Áreas ─────────────────────────────────────────────────────────────────────
# ⚠️ Confirmar que estos codes coinciden con los registros reales
# en la tabla areas del NestJS antes del go-live.
AREA_TO_NESTJS = {
    "HOUSEKEEPING":  "HOUSEKEEPING",
    "MANTENIMIENTO": "MAINTENANCE",
    "MANTENCION":    "MAINTENANCE",
    "AREAS_COMUNES": "COMMON_AREAS",
    "ROOMSERVICE":   "ROOMSERVICE",
}
AREA_FROM_NESTJS = {
    "HOUSEKEEPING":  "HOUSEKEEPING",
    "MAINTENANCE":   "MANTENIMIENTO",
    "COMMON_AREAS":  "AREAS_COMUNES",
    "ROOMSERVICE":   "ROOMSERVICE",
    "MANAGEMENT":    "MANAGEMENT",
    "RECEPTION":     "RECEPTION",
}


# ── Helpers internos ──────────────────────────────────────────────────────────

def _generar_titulo(detalle: str, area: str, ubicacion: str) -> str:
    """
    NestJS requiere title pero el bot nunca lo captura.
    Se genera de forma determinista para que sea legible en el dashboard.
    """
    area_label = {
        "HOUSEKEEPING":  "HK",
        "MANTENIMIENTO": "MT",
        "MANTENCION":    "MT",
        "AREAS_COMUNES": "AC",
        "ROOMSERVICE":   "RS",
    }.get((area or "").upper(), (area or "?")[:3].upper())

    ubi_label    = f"Hab.{ubicacion}" if str(ubicacion).isdigit() else (ubicacion or "?")
    detalle_corto = (detalle or "Sin detalle")[:60]
    return f"[{area_label}] {ubi_label} — {detalle_corto}"


def _extract_worker_name(assignee: Optional[dict]) -> Optional[str]:
    if not assignee:
        return None
    first = assignee.get("firstName", "")
    last  = assignee.get("lastName", "")
    return f"{first} {last}".strip() or None


# ── Conversores públicos ──────────────────────────────────────────────────────

def ticket_to_nestjs(data: dict, property_id: str, user_id: str = None) -> dict:
    """
    Convierte payload del bot al DTO que acepta POST /api/v1/tickets.
    data puede contener: ubicacion, habitacion, detalle, prioridad, area
    """
    ubicacion  = str(data.get("ubicacion") or data.get("habitacion") or "")
    area_flask = (data.get("area") or "HOUSEKEEPING").upper()
    prio_flask = (data.get("prioridad") or "MEDIA").upper()

    room_number   = ubicacion if ubicacion.isdigit() else None
    location_desc = ubicacion if not ubicacion.isdigit() else None

    payload = {
        "propertyId":          property_id,
        "title":               _generar_titulo(
                                   data.get("detalle", ""), area_flask, ubicacion
                               ),
        "description":         data.get("detalle", ""),
        "areaCode":            AREA_TO_NESTJS.get(area_flask, area_flask),
        "priority":            PRIORITY_TO_NESTJS.get(prio_flask, "medium"),
        "status":              "open",
        "channel":             "whatsapp_staff",
        "roomNumber":          room_number,
        "locationDescription": location_desc,
    }
    if user_id:
        payload["createdByUserId"] = user_id
    return payload


def ticket_from_nestjs(t: dict) -> dict:
    """
    Normaliza un ticket del NestJS al formato que espera el código Flask.
    Los flows usan: id, ubicacion, habitacion, detalle, prioridad, estado, area,
                    created_at, assigned_to, worker_name
    """
    ubicacion = t.get("roomNumber") or t.get("locationDescription") or "?"
    return {
        "id":          t.get("id"),
        "id_code":     t.get("idCode"),
        "ubicacion":   ubicacion,
        "habitacion":  ubicacion,   # alias que usan algunos flows
        "detalle":     t.get("description", ""),
        "prioridad":   PRIORITY_FROM_NESTJS.get(t.get("priority", "medium"), "MEDIA"),
        "estado":      STATUS_FROM_NESTJS.get(t.get("status", "open"), "PENDIENTE"),
        "area":        AREA_FROM_NESTJS.get(t.get("areaCode", ""), "HOUSEKEEPING"),
        "created_at":  t.get("createdAt"),
        "assigned_to": t.get("assignedToUserId"),
        "worker_name": _extract_worker_name(t.get("assignee")),
        "photo_url":   t.get("photoUrl"),
        "started_at":  t.get("startedAt"),
        "assigned_at": t.get("assignedAt"),
    }


def worker_from_nestjs(u: dict) -> dict:
    """
    Normaliza un user del NestJS al formato que espera el código Flask.
    Los flows usan: id, nombre_completo, telefono, area, turno_activo,
                    pausada, ocupada, activo
    """
    first = u.get("firstName", "")
    last  = u.get("lastName", "")

    # Área: viene como lista de userAreas → tomamos la primera no eliminada
    areas     = u.get("userAreas") or []
    area_code = areas[0]["area"]["code"] if areas else "HOUSEKEEPING"

    return {
        "id":             u.get("id"),
        "nombre_completo": f"{first} {last}".strip(),
        "telefono":        _build_phone(u.get("phonePrefix", ""), u.get("phoneNumber", "")),
        "area":            AREA_FROM_NESTJS.get(area_code, area_code),
        "activo":          u.get("enabled", True),
        "turno_activo":    u.get("turnoActivo", False),
        "pausada":         False,   # runtime_sessions lo sobreescribe después
        "ocupada":         False,   # runtime_sessions lo sobreescribe después
    }


def supervisor_from_nestjs(u: dict) -> dict:
    """
    Normaliza un supervisor del NestJS.
    Igual que worker_from_nestjs pero extrae las áreas donde es supervisor.
    """
    base = worker_from_nestjs(u)

    # Para supervisores, userAreas contiene solo las de relationship_type = "supervisor"
    areas = u.get("userAreas") or []
    base["areas_supervisadas"] = [
        AREA_FROM_NESTJS.get(a["area"]["code"], a["area"]["code"])
        for a in areas
        if a.get("area", {}).get("code")
    ]
    return base
