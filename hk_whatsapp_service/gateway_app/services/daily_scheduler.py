# gateway_app/services/daily_scheduler.py
"""
Sistema de recordatorios diarios para trabajadores y supervisión.
"""
from __future__ import annotations

import logging
import os
import threading
import time
import json
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)

TIMEZONE = ZoneInfo("America/Santiago")
HORA_RECORDATORIO = 7
MINUTO_RECORDATORIO = 30


def _get_supervisor_phones() -> List[str]:
    import re
    raw = os.getenv("SUPERVISOR_PHONES", "") or ""
    phones = [re.sub(r"\D", "", p.strip()) for p in raw.split(",")]
    return [p for p in phones if p]


def _get_all_workers_phones() -> List[Dict[str, Any]]:
    from gateway_app.services.workers_db import obtener_todos_workers
    return obtener_todos_workers() or []


def _get_tickets_pendientes_resumen() -> Dict[str, Any]:
    from gateway_app.services.tickets_db import obtener_pendientes
    
    pendientes = obtener_pendientes() or []
    nocturnos = []
    diurnos = []
    
    for ticket in pendientes:
        created_at = ticket.get("created_at")
        if created_at:
            try:
                from dateutil import parser
                if isinstance(created_at, str):
                    created_at = parser.parse(created_at)
                
                if created_at.tzinfo is None:
                    created_at = created_at.replace(tzinfo=TIMEZONE)
                
                hora_creacion = created_at.time()
                from datetime import time as dt_time
                if hora_creacion >= dt_time(23, 30) or hora_creacion < dt_time(7, 30):
                    nocturnos.append(ticket)
                else:
                    diurnos.append(ticket)
            except Exception:
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
    if not created_at:
        return "?"
    try:
        from dateutil import parser
        if isinstance(created_at, str):
            created_at = parser.parse(created_at)
        
        ahora = datetime.now(TIMEZONE)
        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=TIMEZONE)
        else:
            created_at = created_at.astimezone(TIMEZONE)
        
        delta = ahora - created_at
        total_mins = int(delta.total_seconds() / 60)
        
        if total_mins < 0:
            return "reciente"
        if total_mins < 60:
            return f"{total_mins} min"
        
        horas = total_mins // 60
        mins = total_mins % 60
        
        if horas >= 24:
            dias = horas // 24
            horas_restantes = horas % 24
            return f"{dias}d {horas_restantes}h"
        
        return f"{horas}h {mins}min"
    except Exception:
        return "?"


def _formatear_ticket_con_tiempo(ticket: Dict[str, Any]) -> str:
    ticket_id = ticket.get("id", "?")
    ubicacion = ticket.get("ubicacion") or ticket.get("habitacion", "?")
    detalle = (ticket.get("detalle") or "Sin detalle")[:50]
    prioridad = (ticket.get("prioridad") or "MEDIA").upper()
    
    tiempo = _calcular_tiempo_transcurrido(ticket.get("created_at"))
    prioridad_emoji = {"ALTA": "🔴", "MEDIA": "🟡", "BAJA": "🟢"}.get(prioridad, "🟡")
    
    return f"{prioridad_emoji} #{ticket_id} · {ubicacion} · {tiempo}\n   {detalle}"


def construir_mensaje_recordatorio_worker(worker: Dict[str, Any]) -> str:
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
    pendientes = resumen.get("pendientes", [])
    nocturnos = resumen.get("nocturnos", [])
    total = resumen.get("total", 0)
    
    if total == 0:
        return (
            "☀️ ¡Buenos días!\n\n"
            "✅ No hay tickets pendientes.\n\n"
            "💡 Di 'pendientes' o 'equipo'"
        )
    
    lineas = ["☀️ ¡Buenos días!\n"]
    
    if nocturnos:
        lineas.append(f"🌙 {len(nocturnos)} ticket(s) fuera de horario:\n")
        for ticket in nocturnos[:5]:
            lineas.append(_formatear_ticket_con_tiempo(ticket))
        if len(nocturnos) > 5:
            lineas.append(f"   ... y {len(nocturnos) - 5} más")
        lineas.append("")
    
    diurnos = [t for t in pendientes if t not in nocturnos]
    if diurnos:
        lineas.append(f"📋 {len(diurnos)} ticket(s) pendientes:\n")
        for ticket in diurnos[:5]:
            lineas.append(_formatear_ticket_con_tiempo(ticket))
        if len(diurnos) > 5:
            lineas.append(f"   ... y {len(diurnos) - 5} más")
        lineas.append("")
    
    lineas.append(f"📊 Total: {total}")
    
    return "\n".join(lineas)


def _marcar_recordatorio_enviado_hoy_directo(phone: str) -> bool:
    from gateway_app.services.runtime_state import load_runtime_session, save_runtime_session

    hoy = datetime.now(TIMEZONE).date().isoformat()
    try:
        state = load_runtime_session(phone) or {}
        state["recordatorio_matutino_fecha"] = hoy
        state["respondio_recordatorio_hoy"] = False
        save_runtime_session(phone, state)
        logger.info("DAILY: recordatorio guardado para %s", phone)
        return True
    except Exception:
        logger.exception("DAILY: Error guardando recordatorio para %s", phone)
        return False


def enviar_recordatorios_matutinos():
    """Envía recordatorios matutinos a trabajadores y supervisores."""
    from gateway_app.services.whatsapp_client import send_whatsapp_text
    
    logger.info("📨 DAILY_SCHEDULER: Iniciando envío de recordatorios matutinos")
    
    workers = _get_all_workers_phones()
    workers_notificados = 0
    
    for worker in workers:
        telefono = worker.get("telefono")
        if not telefono:
            continue
        
        try:
            mensaje = construir_mensaje_recordatorio_worker(worker)
            send_whatsapp_text(to=telefono, body=mensaje)
            
            # ✅ CRÍTICO: Marcar directamente en BD
            ok = _marcar_recordatorio_enviado_hoy_directo(telefono)
            
            if ok:
                workers_notificados += 1
                logger.info(f"✅ Recordatorio enviado y marcado: {worker.get('nombre_completo', telefono)}")
            else:
                logger.warning(f"⚠️ Recordatorio enviado pero NO marcado: {telefono}")
                
        except Exception as e:
            logger.error(f"❌ Error con {telefono}: {e}")
    
    logger.info(f"📨 Recordatorios enviados a {workers_notificados} trabajadores")
    
    # Resumen a supervisores
    supervisors = _get_supervisor_phones()
    resumen = _get_tickets_pendientes_resumen()
    mensaje_sup = construir_mensaje_resumen_supervision(resumen)
    
    for sup_phone in supervisors:
        try:
            send_whatsapp_text(to=sup_phone, body=mensaje_sup)
            logger.info(f"✅ Resumen enviado a supervisor: {sup_phone}")
        except Exception as e:
            logger.error(f"❌ Error supervisor {sup_phone}: {e}")
    
    logger.info(f"📨 Resumen enviado a {len(supervisors)} supervisores")


def _scheduler_loop():
    """Loop principal del scheduler."""
    ultimo_envio: Optional[str] = None
    
    logger.info("🕐 DAILY_SCHEDULER: Loop iniciado")
    
    while True:
        try:
            ahora = datetime.now(TIMEZONE)
            hoy_str = ahora.date().isoformat()
            
            if (ahora.hour == HORA_RECORDATORIO and 
                ahora.minute == MINUTO_RECORDATORIO and 
                ultimo_envio != hoy_str):
                
                logger.info("⏰ DAILY_SCHEDULER: Es hora del recordatorio matutino!")
                enviar_recordatorios_matutinos()
                ultimo_envio = hoy_str
            
            time.sleep(30)
            
        except Exception as e:
            logger.exception(f"❌ DAILY_SCHEDULER loop error: {e}")
            time.sleep(60)


def start_daily_scheduler() -> None:
    """Inicia el scheduler de recordatorios diarios."""
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