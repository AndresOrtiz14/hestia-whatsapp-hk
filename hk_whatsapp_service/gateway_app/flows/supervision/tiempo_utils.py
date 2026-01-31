# gateway_app/flows/supervision/tiempo_utils.py
"""
Utilidades para mostrar tiempo transcurrido y estado de turnos en supervisión.

Funcionalidades:
1. Calcular y formatear tiempo transcurrido desde creación de ticket
2. Mostrar listado de trabajadores con estado de turno
3. Formatear tickets incluyendo antigüedad
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo
from typing import Any

logger = logging.getLogger(__name__)

TIMEZONE = ZoneInfo("America/Santiago")


def calcular_tiempo_transcurrido(fecha: Any) -> str:
    """
    Calcula el tiempo transcurrido desde una fecha.
    
    Args:
        fecha: datetime, string ISO, o None
    
    Returns:
        String formateado: "X min", "Xh Xm", "X días Xh"
    """
    if not fecha:
        return "?"
    
    try:
        from dateutil import parser
        
        if isinstance(fecha, str):
            fecha = parser.isoparse(fecha)

        # Normalización: si viene naive, ASUMIR UTC (muy típico en DB/ISO sin offset)
        if fecha.tzinfo is None:
            fecha = fecha.replace(tzinfo=timezone.utc)
        
        # Comparar en UTC (regla simple y sin DST headaches)
        ahora_utc = datetime.now(timezone.utc)
        fecha_utc = fecha.astimezone(timezone.utc)

        delta = ahora_utc - fecha_utc
        total_mins = int(delta.total_seconds() // 60)

        # Si queda negativo, suele ser skew o TZ mal en el dato; igual lo manejamos
        if total_mins < 0:
            # si está "levemente" en el futuro por segundos/desfase, muéstralo como recién
            if total_mins > -2:
                return "recién"
            return "?"

        if total_mins < 60:
            return f"{total_mins} min"

        horas = total_mins // 60
        mins = total_mins % 60

        if horas >= 24:
            dias = horas // 24
            horas_rest = horas % 24
            if dias == 1:
                return f"1 día {horas_rest}h" if horas_rest else "1 día"
            return f"{dias}d {horas_rest}h" if horas_rest else f"{dias} días"

        return f"{horas}h" if mins == 0 else f"{horas}h {mins}m"

    except Exception as e:
        logger.warning(f"Error calculando tiempo: {e}")
        return "?"


def calcular_tiempo_emoji(fecha: Any) -> str:
    """
    Devuelve un emoji indicando la urgencia basada en el tiempo.
    
    🟢 < 30 min
    🟡 30 min - 2h
    🟠 2h - 8h
    🔴 > 8h
    """
    if not fecha:
        return "⚪"
    
    try:
        from dateutil import parser
        
        if isinstance(fecha, str):
            fecha = parser.parse(fecha)
        
        ahora = datetime.now(TIMEZONE)
        
        if fecha.tzinfo is None:
            fecha = fecha.replace(tzinfo=TIMEZONE)
        else:
            ahora = datetime.now(fecha.tzinfo)
        
        delta = ahora - fecha
        total_mins = int(delta.total_seconds() / 60)
        
        if total_mins < 30:
            return "🟢"
        elif total_mins < 120:  # 2 horas
            return "🟡"
        elif total_mins < 480:  # 8 horas
            return "🟠"
        else:
            return "🔴"
    
    except Exception:
        return "⚪"


def formatear_ticket_con_tiempo(ticket: Dict[str, Any], 
                                  mostrar_asignado: bool = False) -> str:
    """
    Formatea un ticket incluyendo tiempo transcurrido.
    
    Formato:
    🟡 #123 · Hab. 305 · 45 min
       Fuga de agua en baño
    """
    ticket_id = ticket.get("id", "?")
    ubicacion = ticket.get("ubicacion") or ticket.get("habitacion", "?")
    detalle = (ticket.get("detalle") or "Sin detalle")
    prioridad = (ticket.get("prioridad") or "MEDIA").upper()
    created_at = ticket.get("created_at")
    estado = (ticket.get("estado") or "PENDIENTE").upper()
    
    # Tiempo transcurrido
    tiempo = calcular_tiempo_transcurrido(created_at)
    tiempo_emoji = calcular_tiempo_emoji(created_at)
    
    # Emoji de prioridad
    prioridad_emoji = {"ALTA": "🔴", "MEDIA": "🟡", "BAJA": "🟢"}.get(prioridad, "🟡")
    
    # Truncar detalle si es muy largo
    if len(detalle) > 40:
        detalle = detalle[:37] + "..."
    
    linea = f"{prioridad_emoji} #{ticket_id} · {ubicacion} · ⏱️{tiempo}"
    
    # Si se pide mostrar asignado
    if mostrar_asignado:
        huesped_wa = ticket.get("huesped_whatsapp", "")
        if "|" in huesped_wa:
            _, nombre_asignado = huesped_wa.split("|", 1)
            linea += f" · 👤{nombre_asignado}"
        elif estado == "PENDIENTE":
            linea += " · Sin asignar"
    
    linea += f"\n   {detalle}"
    
    return linea


def formatear_lista_tickets_con_tiempo(tickets: List[Dict[str, Any]], 
                                        titulo: str = "📋 Tickets",
                                        mostrar_asignado: bool = True,
                                        max_items: int = 10) -> str:
    """
    Formatea una lista de tickets con tiempo transcurrido.
    """
    if not tickets:
        return f"{titulo}\n\n✅ No hay tickets"
    
    lineas = [f"{titulo} ({len(tickets)})\n"]
    
    for ticket in tickets[:max_items]:
        lineas.append(formatear_ticket_con_tiempo(ticket, mostrar_asignado))
    
    if len(tickets) > max_items:
        lineas.append(f"\n... y {len(tickets) - max_items} más")
    
    return "\n".join(lineas)


# ============================================================
# FUNCIONES PARA MOSTRAR ESTADO DE TURNOS
# ============================================================

def obtener_workers_con_estado() -> List[Dict[str, Any]]:
    """
    Obtiene todos los workers con su estado de turno.
    """
    from gateway_app.services.workers_db import obtener_todos_workers
    
    workers = obtener_todos_workers() or []
    
    for w in workers:
        turno = w.get("turno_activo", False)
        w["turno_emoji"] = "🟢" if turno else "🔴"
        w["turno_texto"] = "En turno" if turno else "Fuera"
    
    return workers


def formatear_workers_para_asignacion(workers: List[Dict[str, Any]], 
                                        ticket: Optional[Dict] = None) -> str:
    """
    Formatea lista de workers para asignación, mostrando estado de turno.
    
    Ordena: primero los que tienen turno activo.
    
    Formato:
    👥 Trabajadores disponibles
    
    ✅ EN TURNO:
    1. 🟢 María García (🏠 HK)
    2. 🟢 Juan López (🔧 MT)
    
    ⚠️ SIN TURNO:
    3. 🔴 Ana Pérez (🏠 HK)
    """
    if not workers:
        return "📭 No hay trabajadores registrados"
    
    # Calcular score si hay ticket
    if ticket:
        from gateway_app.flows.supervision.ticket_assignment import calcular_score_worker
        for w in workers:
            w["score"] = calcular_score_worker(w, ticket)
    
    # Separar por estado de turno
    en_turno = [w for w in workers if w.get("turno_activo", False)]
    sin_turno = [w for w in workers if not w.get("turno_activo", False)]
    
    # Ordenar por score si existe
    if ticket:
        en_turno.sort(key=lambda w: w.get("score", 0), reverse=True)
        sin_turno.sort(key=lambda w: w.get("score", 0), reverse=True)
    
    lineas = ["👥 Trabajadores\n"]
    
    idx = 1
    
    # Primero los que están en turno
    if en_turno:
        lineas.append(f"✅ EN TURNO ({len(en_turno)}):")
        for w in en_turno[:5]:  # Máximo 5
            nombre = w.get("nombre_completo", w.get("username", "?"))
            area = (w.get("area") or "HK").upper()
            
            area_emoji = {
                "HOUSEKEEPING": "🏠", "HK": "🏠",
                "AREAS_COMUNES": "📍", "AC": "📍",
                "MANTENIMIENTO": "🔧", "MT": "🔧", "MANTENCION": "🔧"
            }.get(area, "👤")
            
            area_corta = {
                "HOUSEKEEPING": "HK",
                "AREAS_COMUNES": "AC", 
                "MANTENIMIENTO": "MT",
                "MANTENCION": "MT"
            }.get(area, area[:3])
            
            lineas.append(f"{idx}. 🟢 {nombre} ({area_emoji} {area_corta})")
            idx += 1
        
        if len(en_turno) > 5:
            lineas.append(f"   ... +{len(en_turno) - 5} más en turno")
        
        lineas.append("")
    
    # Luego los que no están en turno (con advertencia)
    if sin_turno:
        lineas.append(f"⚠️ SIN TURNO ({len(sin_turno)}):")
        for w in sin_turno[:3]:  # Máximo 3
            nombre = w.get("nombre_completo", w.get("username", "?"))
            area = (w.get("area") or "HK").upper()
            
            area_emoji = {
                "HOUSEKEEPING": "🏠", "HK": "🏠",
                "AREAS_COMUNES": "📍", "AC": "📍",
                "MANTENIMIENTO": "🔧", "MT": "🔧", "MANTENCION": "🔧"
            }.get(area, "👤")
            
            area_corta = {
                "HOUSEKEEPING": "HK",
                "AREAS_COMUNES": "AC",
                "MANTENIMIENTO": "MT", 
                "MANTENCION": "MT"
            }.get(area, area[:3])
            
            lineas.append(f"{idx}. 🔴 {nombre} ({area_emoji} {area_corta})")
            idx += 1
        
        if len(sin_turno) > 3:
            lineas.append(f"   ... +{len(sin_turno) - 3} más sin turno")
    
    lineas.append("")
    lineas.append("💡 Recomendado: asignar a quien tenga turno activo (🟢)")
    lineas.append("💡 Di el nombre o número")
    
    return "\n".join(lineas)


def construir_mensaje_equipo() -> str:
    """
    Construye mensaje con el estado del equipo completo.
    Comando: 'equipo' o 'trabajadores' o 'mucamas'
    """
    workers = obtener_workers_con_estado()
    
    if not workers:
        return "📭 No hay trabajadores registrados"
    
    en_turno = [w for w in workers if w.get("turno_activo", False)]
    sin_turno = [w for w in workers if not w.get("turno_activo", False)]
    
    lineas = [
        f"👥 Estado del Equipo\n",
        f"🟢 En turno: {len(en_turno)}",
        f"🔴 Sin turno: {len(sin_turno)}",
        f"📊 Total: {len(workers)}\n"
    ]
    
    if en_turno:
        lineas.append("─── EN TURNO ───")
        for w in en_turno:
            nombre = w.get("nombre_completo", "?")
            area = (w.get("area") or "HK").upper()
            area_emoji = {"HOUSEKEEPING": "🏠", "AREAS_COMUNES": "📍", "MANTENIMIENTO": "🔧"}.get(area, "👤")
            lineas.append(f"🟢 {nombre} ({area_emoji})")
        lineas.append("")
    
    if sin_turno:
        lineas.append("─── SIN TURNO ───")
        for w in sin_turno[:5]:
            nombre = w.get("nombre_completo", "?")
            area = (w.get("area") or "HK").upper()
            area_emoji = {"HOUSEKEEPING": "🏠", "AREAS_COMUNES": "📍", "MANTENIMIENTO": "🔧"}.get(area, "👤")
            lineas.append(f"🔴 {nombre} ({area_emoji})")
        
        if len(sin_turno) > 5:
            lineas.append(f"   ... y {len(sin_turno) - 5} más")
    
    return "\n".join(lineas)


# ============================================================
# CÓDIGO A INTEGRAR EN orchestrator_simple.py
# ============================================================
"""
INSTRUCCIONES DE INTEGRACIÓN:

1. Reemplazar mostrar_opciones_workers() para incluir estado de turno:

```python
from gateway_app.flows.supervision.tiempo_utils import formatear_workers_para_asignacion

def mostrar_opciones_workers(from_phone: str, workers: list, ticket_id: int) -> None:
    from gateway_app.services.tickets_db import obtener_ticket_por_id
    
    ticket = obtener_ticket_por_id(ticket_id)
    mensaje = formatear_workers_para_asignacion(workers, ticket)
    
    state = get_supervisor_state(from_phone)
    state["ticket_seleccionado"] = ticket_id
    
    send_whatsapp(from_phone, mensaje)
```

2. Modificar mostrar_pendientes_simple() para incluir tiempo:

```python
from gateway_app.flows.supervision.tiempo_utils import formatear_lista_tickets_con_tiempo

def mostrar_pendientes_simple(from_phone: str) -> None:
    tickets = obtener_pendientes()
    mensaje = formatear_lista_tickets_con_tiempo(
        tickets, 
        titulo="📋 Tickets Pendientes",
        mostrar_asignado=False
    )
    mensaje += "\n\n💡 Di 'asignar [#] a [nombre]'"
    send_whatsapp(from_phone, mensaje)
```

3. Agregar comando 'equipo' al orquestador:

```python
from gateway_app.flows.supervision.tiempo_utils import construir_mensaje_equipo

# En handle_supervision_message(), agregar:
if raw in ['equipo', 'trabajadores', 'mucamas', 'team', 'staff']:
    mensaje = construir_mensaje_equipo()
    send_whatsapp(from_phone, mensaje)
    return
```
"""