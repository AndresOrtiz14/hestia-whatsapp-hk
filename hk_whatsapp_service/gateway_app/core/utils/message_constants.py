"""
Constantes y helpers centralizados para mensajes WhatsApp de Hestia.
Fuente única de verdad para emojis, formatos y extracción de datos de tickets.

v2: Incluye templates para confirmaciones (Fase 3) y mensajes HK (Fase 4).

Uso:
    from gateway_app.core.message_constants import (
        emoji_prioridad, formatear_linea_ticket, formatear_lista_tickets,
        msg_sup_confirmacion, msg_worker_nueva_tarea,
    )
"""

from datetime import datetime, timezone
from typing import Dict, Any, List, Optional

# ═══════════════════════════════════════════════════════════════
# CONSTANTES DE EMOJI
# ═══════════════════════════════════════════════════════════════

PRIORIDAD_EMOJI = {"ALTA": "🔴", "MEDIA": "🟡", "BAJA": "🟢"}
PRIORIDAD_ORDER = {"ALTA": 0, "MEDIA": 1, "BAJA": 2}

ESTADO_EMOJI = {
    "PENDIENTE": "⏳",
    "ASIGNADO": "📋",
    "EN_CURSO": "🔄",
    "PAUSADO": "⏸️",
    "RESUELTO": "✅",
    "COMPLETADO": "✅",
}

ESTADO_LABEL = {
    "PENDIENTE": "Pendiente",
    "ASIGNADO": "Asignada",
    "EN_CURSO": "En curso",
    "PAUSADO": "Pausada",
    "RESUELTO": "Completada",
    "COMPLETADO": "Completada",
}

AREA_EMOJI = {
    "HOUSEKEEPING": "🏠", "HK": "🏠",
    "AREAS_COMUNES": "📍", "AC": "📍",
    "MANTENIMIENTO": "🔧", "MANTENCION": "🔧", "MT": "🔧",
}

AREA_TAG = {
    "HOUSEKEEPING": "HK", "HK": "HK",
    "AREAS_COMUNES": "AC", "AC": "AC",
    "MANTENIMIENTO": "MT", "MANTENCION": "MT", "MT": "MT",
}

TURNO_EMOJI = {True: "🟢", False: "🔴"}


# ═══════════════════════════════════════════════════════════════
# HELPERS DE EMOJI
# ═══════════════════════════════════════════════════════════════

def emoji_prioridad(p: str) -> str:
    """'ALTA' → '🔴', 'MEDIA' → '🟡', 'BAJA' → '🟢'"""
    return PRIORIDAD_EMOJI.get(str(p).upper(), "🟡")


def emoji_estado(e: str) -> str:
    """'PENDIENTE' → '⏳', 'EN_CURSO' → '🔄', etc."""
    return ESTADO_EMOJI.get(str(e).upper(), "❓")


def label_estado(e: str) -> str:
    """'EN_CURSO' → 'En curso', 'PENDIENTE' → 'Pendiente', etc."""
    return ESTADO_LABEL.get(str(e).upper(), str(e))


def emoji_area(a: str) -> str:
    """'HOUSEKEEPING' → '🏠', 'MANTENIMIENTO' → '🔧', etc."""
    return AREA_EMOJI.get(str(a).upper(), "👤")


def tag_area(a: str) -> str:
    """'HOUSEKEEPING' → 'HK', 'MANTENIMIENTO' → 'MT', etc."""
    return AREA_TAG.get(str(a).upper(), str(a)[:3].upper() if a else "?")


# ═══════════════════════════════════════════════════════════════
# HELPERS DE EXTRACCIÓN DE DATOS
# ═══════════════════════════════════════════════════════════════

def ubicacion_de_ticket(t: dict) -> str:
    """Extrae ubicación de cualquier ticket dict (maneja múltiples keys)."""
    return t.get("ubicacion") or t.get("habitacion") or t.get("room") or "?"


def ubicacion_corta(t: dict) -> str:
    """
    Para listas: 'Hab. 305' o 'Lobby'.
    Detecta si es número de habitación y agrega prefijo.
    """
    ubi = ubicacion_de_ticket(t)
    if ubi == "?":
        return ubi
    if ubi.strip().isdigit():
        return f"Hab. {ubi.strip()}"
    if ubi.lower().startswith("hab"):
        return ubi
    return ubi


def detalle_de_ticket(t: dict, max_len: int = 35) -> str:
    """Extrae detalle truncado."""
    d = t.get("detalle") or t.get("descripcion") or "Sin detalle"
    return (d[:max_len] + "...") if len(d) > max_len else d


def nombre_worker_de_ticket(t: dict) -> str:
    """
    Extrae nombre del worker asignado. Soporta:
    - t["worker_name"] (de JOINs)
    - t["huesped_whatsapp"] formato "phone|nombre"
    - t["asignado_a_nombre"] (campo enriquecido)
    """
    wn = t.get("worker_name")
    if wn:
        return wn

    hw = str(t.get("huesped_whatsapp") or "")
    if "|" in hw:
        return hw.split("|", 1)[1]

    return t.get("asignado_a_nombre") or "Sin asignar"


# ═══════════════════════════════════════════════════════════════
# FORMATEO DE UBICACIÓN (para mensajes completos)
# ═══════════════════════════════════════════════════════════════

def ubicacion_con_emoji(ubicacion) -> str:
    """
    Formatea ubicación con emoji para mensajes de confirmación/notificación.
    '305' → '🏠 Habitación 305'
    'Lobby' → '📍 Lobby'
    Reemplaza formatear_ubicacion_con_emoji() de otros archivos.
    """
    ubi = str(ubicacion).strip() if ubicacion else ""
    if not ubi or ubi == "?":
        return "📍 Sin ubicación"
    if ubi.isdigit():
        num = int(ubi)
        if 100 <= num <= 9999:
            return f"🏠 Habitación {ubi}"
        return f"📍 {ubi}"
    if ubi.lower().startswith("hab"):
        return f"🏠 {ubi}"
    return f"📍 {ubi}"


# ═══════════════════════════════════════════════════════════════
# CÁLCULO DE TIEMPO
# ═══════════════════════════════════════════════════════════════

def _parse_fecha(fecha) -> Optional[datetime]:
    """Parsea fecha de cualquier formato (datetime, str ISO, None)."""
    if fecha is None:
        return None
    if isinstance(fecha, datetime):
        return fecha
    try:
        from dateutil import parser
        return parser.parse(str(fecha))
    except Exception:
        return None


def calcular_minutos(fecha) -> int:
    """
    Calcula minutos transcurridos desde una fecha hasta ahora.
    Maneja timezone-aware y naive. Retorna 0 si no puede calcular.
    """
    dt = _parse_fecha(fecha)
    if not dt:
        return 0
    try:
        if dt.tzinfo:
            now = datetime.now(timezone.utc)
        else:
            now = datetime.now()
        return max(0, int((now - dt).total_seconds() / 60))
    except Exception:
        return 0


def formato_tiempo(mins: int) -> str:
    """
    Formatea minutos a texto legible:
    - < 60:    '12 min'
    - 60-1440: '2h 15m'
    - > 1440:  '1d 3h'
    """
    if mins < 60:
        return f"{mins} min"
    elif mins < 1440:
        h, m = divmod(mins, 60)
        return f"{h}h {m}m"
    else:
        d, resto = divmod(mins, 1440)
        h = resto // 60
        return f"{d}d {h}h"


# ═══════════════════════════════════════════════════════════════
# FORMATEADORES UNIFICADOS PARA LISTAS DE TICKETS
# ═══════════════════════════════════════════════════════════════

def formatear_linea_ticket(
    t: dict,
    mostrar_tiempo: bool = True,
    mostrar_worker: bool = False,
    campo_fecha: str = "created_at",
) -> str:
    """
    Línea estándar de ticket para listas.

    Con tiempo:
        🟡 #123 · Hab. 305 · ⏱️ 12 min
           Fuga de agua en baño

    Con worker:
        🟡 #123 · Hab. 305 · ⏱️ 12 min · 👤 María
           Fuga de agua en baño

    Sin tiempo:
        🟡 #123 · Hab. 305
           Fuga de agua en baño
    """
    tid = t.get("id_code") or t.get("id", "?")
    pri = emoji_prioridad(t.get("prioridad", "MEDIA"))
    ubi = ubicacion_corta(t)
    det = detalle_de_ticket(t)

    partes = [f"{pri} #{tid} · {ubi}"]

    if mostrar_tiempo:
        mins = calcular_minutos(t.get(campo_fecha))
        if mins > 0:
            partes.append(f"⏱️ {formato_tiempo(mins)}")

    if mostrar_worker:
        worker = nombre_worker_de_ticket(t)
        if worker and worker != "Sin asignar":
            partes.append(f"👤 {worker[:15]}")

    linea1 = " · ".join(partes)
    return f"{linea1}\n   {det}"


def formatear_lista_tickets(
    tickets: List[dict],
    titulo: str,
    hint: str = "",
    msg_vacio: str = "",
    mostrar_tiempo: bool = True,
    mostrar_worker: bool = False,
    campo_fecha: str = "created_at",
    max_items: int = 10,
) -> str:
    """
    Lista formateada de tickets con título, líneas y hint.

    Resultado:
        📋 Tareas Pendientes (5)

        🟡 #123 · Hab. 305 · ⏱️ 12 min
           Fuga de agua en baño
        🔴 #124 · Hab. 201 · ⏱️ 45 min
           Vidrio roto

        💡 Di 'asignar [#] a [nombre]'
    """
    if not tickets:
        return msg_vacio or "✅ No hay tareas en esta categoría"

    lineas = [f"{titulo} ({len(tickets)})\n"]

    for t in tickets[:max_items]:
        lineas.append(formatear_linea_ticket(
            t,
            mostrar_tiempo=mostrar_tiempo,
            mostrar_worker=mostrar_worker,
            campo_fecha=campo_fecha,
        ))

    if len(tickets) > max_items:
        lineas.append(f"\n... y {len(tickets) - max_items} más")

    if hint:
        lineas.append(f"\n{hint}")

    return "\n".join(lineas)


# ═══════════════════════════════════════════════════════════════
# TEMPLATES: CONFIRMACIONES AL SUPERVISOR (FASE 3)
# ═══════════════════════════════════════════════════════════════

def msg_sup_confirmacion(
    ticket_id: int,
    verbo: str,
    ubicacion: str,
    detalle: str,
    prioridad: str,
    worker_nombre: str = None,
    worker_area: str = None,
    duracion_min: int = None,
    hint: str = None,
    ticket_area: str = None,
) -> str:
    """
    Template unificado para confirmaciones al supervisor.

    verbo: "creada" | "asignada" | "reasignada" | "finalizada"

    Resultado:
        ✅ Tarea #123 asignada

        🏠 Habitación 305
        📝 Fuga de agua
        🟡 Prioridad: MEDIA
        👤 Asignada a: María (🏠 HK)
        ⏱️ Duración: 12 min

        💡 Di 'asignar [#] a [nombre]'
    """
    pri = emoji_prioridad(prioridad)
    ubi_fmt = ubicacion_con_emoji(ubicacion)

    lineas = [
        f"✅ Tarea #{ticket_id} {verbo}\n",
        ubi_fmt,
        f"📝 {detalle}",
        f"{pri} Prioridad: {str(prioridad).upper()}",
    ]

    if worker_nombre:
        worker_info = worker_nombre
        if worker_area:
            a_emoji = emoji_area(worker_area)
            a_tag = tag_area(worker_area)
            worker_info = f"{worker_nombre} ({a_emoji} {a_tag})"

        verbo_worker = {
            "asignada": "Asignada a",
            "reasignada": "Reasignada a",
            "finalizada": "Worker",
            "creada": "Asignada a",
        }.get(verbo, "Asignada a")
        lineas.append(f"👤 {verbo_worker}: {worker_info}")

    if ticket_area:
        lineas.append(f"{emoji_area(ticket_area)} Área: {tag_area(ticket_area)}")

    if duracion_min is not None:
        lineas.append(f"⏱️ Duración: {formato_tiempo(duracion_min)}")

    if hint:
        lineas.append(f"\n{hint}")

    return "\n".join(lineas)


def msg_sup_dialogo(
    ticket_id: int,
    ubicacion: str,
    detalle: str,
    prioridad: str,
    worker_nombre: str,
    es_creacion: bool = False,
    ticket_area: str = None,
) -> str:
    """
    Diálogo de confirmación antes de asignar.

    Resultado:
        🟦 Confirmar asignación

        📋 Tarea #123 [creada]
        🏠 Habitación 305
        📝 Fuga de agua
        🟡 Prioridad: MEDIA

        👤 ¿Asignar a: María?

        Responde 'si' o 'no'
    """
    pri = emoji_prioridad(prioridad)
    ubi_fmt = ubicacion_con_emoji(ubicacion)
    titulo = f"📋 Tarea #{ticket_id}" + (" creada" if es_creacion else "")

    area_linea = f"{emoji_area(ticket_area)} Área: {tag_area(ticket_area)}\n" if ticket_area else ""
    return (
        f"🟦 Confirmar asignación\n\n"
        f"{titulo}\n"
        f"{ubi_fmt}\n"
        f"📝 {detalle}\n"
        f"{pri} Prioridad: {str(prioridad).upper()}\n"
        f"{area_linea}"
        f"\n👤 ¿Asignar a: {worker_nombre}?\n\n"
        f"Responde 'si' o 'no'"
    )


# ═══════════════════════════════════════════════════════════════
# TEMPLATES: NOTIFICACIONES AL WORKER DESDE SUPERVISIÓN (FASE 3)
# ═══════════════════════════════════════════════════════════════

def msg_worker_nueva_tarea(
    ticket_id: int,
    ubicacion: str,
    detalle: str,
    prioridad: str,
) -> str:
    """
    Notificación al worker: nueva tarea asignada.
    Usado desde supervisión Y desde HK (fuente única).

    Resultado:
        🔔 Nueva tarea asignada

        🟡 #123 · 🏠 Habitación 305
        📝 Fuga de agua

        💡 Di 'tomar' para comenzar
    """
    pri = emoji_prioridad(prioridad)
    ubi_fmt = ubicacion_con_emoji(ubicacion)

    return (
        f"🔔 Nueva tarea asignada\n\n"
        f"{pri} #{ticket_id} · {ubi_fmt}\n"
        f"📝 {detalle}\n\n"
        f"💡 Di 'tomar' para comenzar"
    )


def msg_worker_tarea_reasignada_saliente(
    ticket_id: int,
    ubicacion: str,
    nuevo_worker: str,
) -> str:
    """
    Notificación al worker original: tu tarea fue reasignada.

    Resultado:
        🔄 Tarea #123 reasignada

        🏠 Habitación 305
        ℹ️ Fue reasignada a Pedro
    """
    ubi_fmt = ubicacion_con_emoji(ubicacion)
    return (
        f"🔄 Tarea #{ticket_id} reasignada\n\n"
        f"{ubi_fmt}\n"
        f"ℹ️ Fue reasignada a {nuevo_worker}"
    )


def msg_worker_tarea_finalizada_sup(
    ticket_id: int,
    ubicacion: str,
    detalle: str,
) -> str:
    """
    Notificación al worker: supervisión finalizó tu tarea.

    Resultado:
        ℹ️ Tarea #123 finalizada

        🏠 Habitación 305
        📝 Fuga de agua

        ✅ Ya no necesitas completarla
    """
    ubi_fmt = ubicacion_con_emoji(ubicacion)
    return (
        f"ℹ️ Tarea #{ticket_id} finalizada\n\n"
        f"{ubi_fmt}\n"
        f"📝 {detalle}\n\n"
        f"✅ Ya no necesitas completarla"
    )


# ═══════════════════════════════════════════════════════════════
# TEMPLATES: ESTADOS DE TAREA — WORKER / HK (FASE 4)
# ═══════════════════════════════════════════════════════════════

def msg_worker_tarea_en_progreso(ticket_id: int, ubicacion: str, detalle: str) -> str:
    """
    🔄 Tarea #123 en curso

    🏠 Habitación 305
    📝 Fuga de agua

    💡 Di 'fin' cuando termines
    """
    ubi_fmt = ubicacion_con_emoji(ubicacion)
    return (
        f"🔄 Tarea #{ticket_id} en curso\n\n"
        f"{ubi_fmt}\n"
        f"📝 {detalle}\n\n"
        f"💡 Di 'fin' cuando termines"
    )


def msg_worker_tarea_completada(ticket_id: int, tiempo_mins: int) -> str:
    """
    ✅ Tarea #123 completada
    ⏱️ Tiempo: 12 min

    ¡Buen trabajo! 🎉
    """
    return (
        f"✅ Tarea #{ticket_id} completada\n"
        f"⏱️ Tiempo: {formato_tiempo(tiempo_mins)}\n\n"
        f"¡Buen trabajo! 🎉"
    )


def msg_worker_tarea_pausada(ticket_id: int) -> str:
    """
    ⏸️ Tarea #123 pausada

    💡 Di 'reanudar' para continuar
    """
    return (
        f"⏸️ Tarea #{ticket_id} pausada\n\n"
        f"💡 Di 'reanudar' para continuar"
    )


def msg_worker_tarea_reanudada(ticket_id: int) -> str:
    """
    ▶️ Tarea #123 reanudada

    💡 Di 'fin' cuando termines
    """
    return (
        f"▶️ Tarea #{ticket_id} reanudada\n\n"
        f"💡 Di 'fin' cuando termines"
    )


def msg_worker_reporte_creado(ticket_id: int, ubicacion: str, prioridad: str) -> str:
    """
    ✅ Tarea #123 creada
    🟡 Hab. 305

    ✓ Notificado a operaciones
    """
    pri = emoji_prioridad(prioridad)
    ubi = str(ubicacion).strip() if ubicacion else "?"
    # Formato corto para ubicación
    if ubi.isdigit():
        ubi = f"Hab. {ubi}"
    return (
        f"✅ Tarea #{ticket_id} creada\n"
        f"{pri} {ubi}\n\n"
        f"✓ Notificado a operaciones"
    )


# ═══════════════════════════════════════════════════════════════
# TEMPLATES: NOTIFICACIONES DE TICKET A SUPERVISOR
# ═══════════════════════════════════════════════════════════════

def msg_aviso_general(mensaje: str) -> str:
    """Mensaje de aviso general enviado a cada trabajador en turno."""
    return (
        f"📢 *Aviso de Supervisión*\n\n"
        f"{mensaje}\n\n"
        f"— Supervisión 🏨"
    )


def msg_sup_preview_aviso(mensaje: str, count: int) -> str:
    """Preview de confirmación mostrado al supervisor antes de enviar aviso."""
    return (
        f"📢 ¿Enviar este aviso a *{count} trabajador(es)* en turno?\n\n"
        f"_{mensaje}_\n\n"
        f"Responde *si* para confirmar o *no* para cancelar."
    )


def msg_notif_ticket_a_supervisor(
    ticket_id: int,
    ubicacion: str,
    detalle: str,
    prioridad: str,
    area: str,
    creado_por_phone: str,
) -> str:
    """
    Notificación a supervisor: nuevo ticket creado.

    Resultado:
        🔧 Nuevo ticket · MT

        🏠 Habitación 305
        📝 Fuga de agua en baño
        🔴 Prioridad: ALTA
        📤 Creado por: Supervisión (+56912345678)

        💡 Di 'tomar 123' para aceptar
    """
    area_emoji = emoji_area(area)
    area_tag = tag_area(area)
    ubi_fmt = ubicacion_con_emoji(ubicacion)
    pri = emoji_prioridad(prioridad)

    return (
        f"{area_emoji} Nuevo ticket #{ticket_id} · {area_tag}\n\n"
        f"{ubi_fmt}\n"
        f"📝 {detalle}\n"
        f"{pri} Prioridad: {str(prioridad).upper()}\n"
        f"📤 Creado por: Supervisión ({creado_por_phone})\n\n"
        f"💡 Di 'tomar {ticket_id}' para aceptar"
    )