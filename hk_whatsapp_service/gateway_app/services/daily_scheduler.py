# gateway_app/services/daily_scheduler.py
"""
Sistema de recordatorios diarios para trabajadores y supervisión.

Funcionalidades:
1. 7:30 AM: Recordatorio a trabajadores para usar el bot
2. 7:30 AM: Resumen de tickets pendientes/nocturnos a supervisión
3. Activación automática de turno con cualquier respuesta
"""
from __future__ import annotations

import logging
import os
import threading
import time
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)

# Zona horaria de Chile
TIMEZONE = ZoneInfo("America/Santiago")

# Hora del recordatorio matutino
HORA_RECORDATORIO = 1
MINUTO_RECORDATORIO = 57


def _get_supervisor_phones() -> List[str]:
    """Obtiene los teléfonos de supervisores desde env vars."""
    import re
    raw = os.getenv("SUPERVISOR_PHONES", "") or ""
    phones = [re.sub(r"\D", "", p.strip()) for p in raw.split(",")]
    return [p for p in phones if p]


def _get_all_workers_phones() -> List[Dict[str, Any]]:
    """Obtiene todos los trabajadores activos con sus datos."""
    from gateway_app.services.workers_db import obtener_todos_workers
    return obtener_todos_workers() or []


def _get_tickets_pendientes_resumen() -> Dict[str, Any]:
    """
    Obtiene resumen de tickets pendientes/nocturnos para supervisión.
    
    Returns:
        Dict con:
        - pendientes: tickets pendientes
        - nocturnos: tickets creados fuera de horario (después de 23:30 o antes de 7:30)
        - total: cantidad total
    """
    from gateway_app.services.tickets_db import obtener_pendientes, fetchall, using_pg
    from gateway_app.services.db import fetchall as db_fetchall
    
    ahora = datetime.now(TIMEZONE)
    
    # Obtener tickets pendientes
    pendientes = obtener_pendientes() or []
    
    # Identificar tickets nocturnos (creados después de 23:30 ayer o antes de 7:30 hoy)
    inicio_horario_hoy = ahora.replace(hour=7, minute=30, second=0, microsecond=0)
    fin_horario_ayer = (ahora - timedelta(days=1)).replace(hour=23, minute=30, second=0, microsecond=0)
    
    nocturnos = []
    diurnos = []
    
    for ticket in pendientes:
        created_at = ticket.get("created_at")
        if created_at:
            try:
                from dateutil import parser
                if isinstance(created_at, str):
                    created_at = parser.parse(created_at)
                
                # Asegurar timezone
                if created_at.tzinfo is None:
                    created_at = created_at.replace(tzinfo=TIMEZONE)
                
                # Si fue creado en horario nocturno
                hora_creacion = created_at.time()
                from datetime import time
                if hora_creacion >= time(23, 30) or hora_creacion < time(7, 30):
                    nocturnos.append(ticket)
                else:
                    diurnos.append(ticket)
            except Exception as e:
                logger.warning(f"Error parseando fecha ticket #{ticket.get('id')}: {e}")
                diurnos.append(ticket)
        else:
            diurnos.append(ticket)
    
    return {
        "pendientes": pendientes,
        "nocturnos": nocturnos,
        "diurnos": diurnos,
        "total": len(pendientes)
    }


def _calcular_tiempo_transcurrido(created_at) -> str:
    """
    Calcula el tiempo transcurrido desde la creación de un ticket.
    
    Returns:
        String formateado como "Xh Xmin" o "X min"
    """
    if not created_at:
        return "?"
    
    try:
        from dateutil import parser
        if isinstance(created_at, str):
            created_at = parser.parse(created_at)
        
        ahora = datetime.now(TIMEZONE)
        
        # Asegurar timezone
        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=TIMEZONE)
        else:
            ahora = datetime.now(created_at.tzinfo)
        
        delta = ahora - created_at
        total_mins = int(delta.total_seconds() / 60)
        
        if total_mins < 60:
            return f"{total_mins} min"
        
        horas = total_mins // 60
        mins = total_mins % 60
        
        if horas >= 24:
            dias = horas // 24
            horas_restantes = horas % 24
            if dias == 1:
                return f"1 día {horas_restantes}h"
            return f"{dias} días {horas_restantes}h"
        
        return f"{horas}h {mins}min"
    
    except Exception as e:
        logger.warning(f"Error calculando tiempo transcurrido: {e}")
        return "?"


def _formatear_ticket_con_tiempo(ticket: Dict[str, Any]) -> str:
    """
    Formatea un ticket incluyendo tiempo transcurrido.
    
    Returns:
        String formateado con info del ticket
    """
    ticket_id = ticket.get("id", "?")
    ubicacion = ticket.get("ubicacion") or ticket.get("habitacion", "?")
    detalle = (ticket.get("detalle") or "Sin detalle")[:50]  # Truncar
    prioridad = (ticket.get("prioridad") or "MEDIA").upper()
    created_at = ticket.get("created_at")
    
    tiempo = _calcular_tiempo_transcurrido(created_at)
    
    prioridad_emoji = {"ALTA": "🔴", "MEDIA": "🟡", "BAJA": "🟢"}.get(prioridad, "🟡")
    
    return f"{prioridad_emoji} #{ticket_id} · {ubicacion} · {tiempo}\n   {detalle}"


def construir_mensaje_recordatorio_worker(worker: Dict[str, Any]) -> str:
    """
    Construye el mensaje de recordatorio matutino para un trabajador.
    """
    nombre = worker.get("nombre_completo", worker.get("username", ""))
    primer_nombre = nombre.split()[0] if nombre else "👋"
    
    return (
        f"☀️ ¡Buenos días{', ' + primer_nombre if primer_nombre != '👋' else ''}!\n\n"
        f"📱 Si hoy estás trabajando, responde cualquier mensaje "
        f"para activar tu turno automáticamente.\n\n"
        f"💡 Una vez activo, podrás:\n"
        f"• Recibir y tomar tareas\n"
        f"• Reportar problemas\n"
        f"• Ver tus asignaciones\n\n"
        f"¡Que tengas un excelente día! 🌟"
    )


def construir_mensaje_resumen_supervision(resumen: Dict[str, Any]) -> str:
    """
    Construye el mensaje de resumen matutino para supervisión.
    """
    pendientes = resumen.get("pendientes", [])
    nocturnos = resumen.get("nocturnos", [])
    total = resumen.get("total", 0)
    
    if total == 0:
        return (
            "☀️ ¡Buenos días!\n\n"
            "✅ No hay tickets pendientes.\n\n"
            "💡 Comandos disponibles:\n"
            "• 'pendientes' - ver lista\n"
            "• 'equipo' - ver trabajadores activos"
        )
    
    lineas = ["☀️ ¡Buenos días!\n"]
    
    # Tickets nocturnos primero (más importantes)
    if nocturnos:
        lineas.append(f"🌙 {len(nocturnos)} ticket(s) recibidos fuera de horario:\n")
        for ticket in nocturnos[:5]:  # Máximo 5
            lineas.append(_formatear_ticket_con_tiempo(ticket))
        if len(nocturnos) > 5:
            lineas.append(f"   ... y {len(nocturnos) - 5} más")
        lineas.append("")
    
    # Otros tickets pendientes
    diurnos = [t for t in pendientes if t not in nocturnos]
    if diurnos:
        lineas.append(f"📋 {len(diurnos)} ticket(s) pendientes adicionales:\n")
        for ticket in diurnos[:5]:
            lineas.append(_formatear_ticket_con_tiempo(ticket))
        if len(diurnos) > 5:
            lineas.append(f"   ... y {len(diurnos) - 5} más")
        lineas.append("")
    
    lineas.append(f"📊 Total pendientes: {total}\n")
    lineas.append("💡 Di 'pendientes' para ver completo")
    lineas.append("💡 Di 'equipo' para ver trabajadores")
    
    return "\n".join(lineas)


def enviar_recordatorios_matutinos():
    """
    Envía recordatorios matutinos a trabajadores y supervisores.
    Se ejecuta a las 7:30 AM.
    """
    from gateway_app.services.whatsapp_client import send_whatsapp_text
    
    logger.info("📨 DAILY_SCHEDULER: Iniciando envío de recordatorios matutinos")
    
    # 1. Recordatorios a trabajadores
    workers = _get_all_workers_phones()
    workers_notificados = 0
    
    for worker in workers:
        telefono = worker.get("telefono")
        if not telefono:
            continue
        
        try:
            mensaje = construir_mensaje_recordatorio_worker(worker)
            send_whatsapp_text(to=telefono, body=mensaje)
            workers_notificados += 1
            logger.info(f"✅ Recordatorio enviado a worker: {worker.get('nombre_completo', telefono)}")
        except Exception as e:
            logger.error(f"❌ Error enviando recordatorio a {telefono}: {e}")
    
    logger.info(f"📨 Recordatorios enviados a {workers_notificados} trabajadores")
    
    # 2. Resumen a supervisores
    supervisors = _get_supervisor_phones()
    resumen = _get_tickets_pendientes_resumen()
    mensaje_sup = construir_mensaje_resumen_supervision(resumen)
    
    for sup_phone in supervisors:
        try:
            send_whatsapp_text(to=sup_phone, body=mensaje_sup)
            logger.info(f"✅ Resumen enviado a supervisor: {sup_phone}")
        except Exception as e:
            logger.error(f"❌ Error enviando resumen a supervisor {sup_phone}: {e}")
    
    logger.info(f"📨 Resumen enviado a {len(supervisors)} supervisores")


def _marcar_recordatorio_enviado_hoy(phone: str) -> None:
    """Marca que se envió recordatorio a este teléfono hoy."""
    from gateway_app.services.runtime_state import get_state, persist_state
    
    state = get_state(phone)
    state["recordatorio_matutino_fecha"] = datetime.now(TIMEZONE).date().isoformat()
    persist_state(phone, state)


def _necesita_activacion_turno_auto(phone: str) -> bool:
    """
    Verifica si el worker necesita activación automática de turno.
    
    Retorna True si:
    - El turno NO está activo
    - Se envió recordatorio matutino HOY
    - No ha respondido aún hoy
    """
    from gateway_app.services.runtime_state import get_state
    from gateway_app.services.workers_db import buscar_worker_por_telefono
    
    # Verificar si es un worker
    worker = buscar_worker_por_telefono(phone)
    if not worker:
        return False
    
    # Verificar turno actual
    if worker.get("turno_activo", False):
        return False
    
    # Verificar si se envió recordatorio hoy
    state = get_state(phone)
    fecha_recordatorio = state.get("recordatorio_matutino_fecha")
    hoy = datetime.now(TIMEZONE).date().isoformat()
    
    if fecha_recordatorio == hoy:
        # Se envió recordatorio hoy y no tiene turno activo
        # -> Cualquier mensaje activa el turno
        return True
    
    return False


def activar_turno_automatico_si_necesario(phone: str) -> bool:
    """
    Activa el turno automáticamente si el worker responde al recordatorio matutino.
    
    Returns:
        True si se activó el turno, False si no era necesario
    """
    from gateway_app.services.workers_db import activar_turno_por_telefono
    from gateway_app.services.runtime_state import get_state, persist_state
    
    if not _necesita_activacion_turno_auto(phone):
        return False
    
    # Activar turno
    ok = activar_turno_por_telefono(phone)
    
    if ok:
        state = get_state(phone)
        state["turno_activo"] = True
        state["turno_inicio"] = datetime.now(TIMEZONE).isoformat()
        # Limpiar flag de recordatorio
        state["recordatorio_matutino_fecha"] = None
        persist_state(phone, state)
        
        logger.info(f"✅ TURNO AUTO-ACTIVADO para {phone} (respuesta a recordatorio)")
        return True
    
    return False


def _scheduler_loop():
    """
    Loop principal del scheduler.
    Verifica cada minuto si es hora de enviar recordatorios.
    """
    ultimo_envio: Optional[str] = None
    
    logger.info("🕐 DAILY_SCHEDULER: Loop iniciado")
    
    while True:
        try:
            ahora = datetime.now(TIMEZONE)
            hoy_str = ahora.date().isoformat()
            
            # Verificar si es hora del recordatorio (7:30 AM)
            if (ahora.hour == HORA_RECORDATORIO and 
                ahora.minute == MINUTO_RECORDATORIO and 
                ultimo_envio != hoy_str):
                
                logger.info("⏰ DAILY_SCHEDULER: Es hora del recordatorio matutino!")
                enviar_recordatorios_matutinos()
                ultimo_envio = hoy_str
            
            # Esperar 30 segundos antes de volver a verificar
            time.sleep(30)
            
        except Exception as e:
            logger.exception(f"❌ DAILY_SCHEDULER loop error: {e}")
            time.sleep(60)  # Esperar más en caso de error


def start_daily_scheduler() -> None:
    """
    Inicia el scheduler de recordatorios diarios.
    """
    enabled = (os.getenv("DAILY_SCHEDULER_ENABLED", "true") or "").lower() == "true"
    
    if not enabled:
        logger.info("🕐 DAILY_SCHEDULER no iniciado (DAILY_SCHEDULER_ENABLED=false)")
        return
    
    th = threading.Thread(
        target=_scheduler_loop,
        daemon=True,
        name="daily_scheduler"
    )
    th.start()
    logger.info("🕐 DAILY_SCHEDULER thread iniciado")


# ============================================================
# UTILIDADES PARA SUPERVISIÓN: Mostrar tiempo y estado de turnos
# ============================================================

def obtener_workers_con_estado_turno() -> List[Dict[str, Any]]:
    """
    Obtiene todos los workers con su estado de turno actual.
    
    Returns:
        Lista de workers con campos:
        - nombre_completo
        - telefono
        - area
        - turno_activo (bool)
        - turno_emoji (🟢 o 🔴)
    """
    from gateway_app.services.workers_db import obtener_todos_workers
    
    workers = obtener_todos_workers() or []
    
    for w in workers:
        turno = w.get("turno_activo", False)
        w["turno_emoji"] = "🟢" if turno else "🔴"
        w["turno_texto"] = "En turno" if turno else "Sin turno"
    
    return workers


def formatear_lista_workers_con_turno(workers: List[Dict[str, Any]], 
                                       resaltar_activos: bool = True) -> str:
    """
    Formatea una lista de workers mostrando su estado de turno.
    
    Args:
        workers: Lista de workers
        resaltar_activos: Si True, muestra primero los que tienen turno activo
    
    Returns:
        String formateado para enviar por WhatsApp
    """
    if not workers:
        return "📭 No hay trabajadores registrados"
    
    # Separar por estado de turno si se solicita
    if resaltar_activos:
        activos = [w for w in workers if w.get("turno_activo", False)]
        inactivos = [w for w in workers if not w.get("turno_activo", False)]
        workers_ordenados = activos + inactivos
    else:
        workers_ordenados = workers
    
    lineas = [f"👥 Equipo ({len(workers)} trabajadores)\n"]
    
    # Primero los activos
    activos_count = sum(1 for w in workers if w.get("turno_activo", False))
    lineas.append(f"🟢 En turno: {activos_count}")
    lineas.append(f"🔴 Sin turno: {len(workers) - activos_count}\n")
    
    for i, w in enumerate(workers_ordenados, 1):
        nombre = w.get("nombre_completo", w.get("username", "?"))
        area = (w.get("area") or "HK").upper()
        turno_emoji = w.get("turno_emoji", "❓")
        
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
        
        lineas.append(f"{turno_emoji} {nombre} ({area_emoji} {area_corta})")
    
    return "\n".join(lineas)