# gateway_app/services/daily_scheduler.py
"""
Sistema de recordatorios diarios para workers y supervisores.

Corre a las 7:30 AM (hora de cada property según su timezone).
Opera en todas las properties con workers bot configurado.

Multi-tenant: descubre las properties via NestJS en cada ejecución.
No depende de ORG_ID_DEFAULT, HOTEL_ID_DEFAULT ni SUPERVISOR_PHONES.
"""
from __future__ import annotations

import logging
import os
import threading
import time
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

logger = logging.getLogger(__name__)

# Hora del recordatorio — igual para todas las properties
HORA_RECORDATORIO  = 7
MINUTO_RECORDATORIO = 30

# Intervalo de polling del loop (cada 60 segundos)
_POLL_SECONDS = 60

# TTL del cache de properties (1 hora) — reduce llamadas al NestJS de 1440/día a ~24/día
_PROPERTIES_TTL = 3600
_properties_cache: List[Dict[str, Any]] = []
_properties_cache_expiry: float = 0.0


# ============================================================
# DISCOVERY DE PROPERTIES
# ============================================================

def _get_properties_configuradas() -> List[Dict[str, Any]]:
    """
    Retorna todas las properties que tienen el bot de workers configurado.
    Cachea el resultado 1 hora para evitar llamadas excesivas al NestJS
    (especialmente durante rolling deploys donde dos instancias corren en paralelo).
    """
    global _properties_cache, _properties_cache_expiry

    now = time.time()
    if _properties_cache and now < _properties_cache_expiry:
        return _properties_cache

    from gateway_app.services.api_client import api_get
    data = api_get("/api/v1/properties/workers-configured")
    if not data or not isinstance(data, list):
        logger.warning("daily_scheduler: no se pudieron obtener properties configuradas")
        return _properties_cache  # devuelve el cache anterior si existe
    logger.info("daily_scheduler: %s properties configuradas", len(data))
    _properties_cache = data
    _properties_cache_expiry = now + _PROPERTIES_TTL
    return _properties_cache


# ============================================================
# LÓGICA DE TIMING POR TIMEZONE
# ============================================================

def _es_hora_recordatorio(timezone_str: str, ahora_utc: datetime) -> bool:
    """
    Verifica si en la timezone de la property son las 7:30 AM.
    Retorna True solo durante el minuto exacto para evitar envíos duplicados.
    """
    try:
        tz = ZoneInfo(timezone_str or "America/Santiago")
    except ZoneInfoNotFoundError:
        logger.warning(
            "daily_scheduler: timezone inválida '%s', usando America/Santiago",
            timezone_str,
        )
        tz = ZoneInfo("America/Santiago")

    ahora_local = ahora_utc.astimezone(tz)
    return (
        ahora_local.hour   == HORA_RECORDATORIO
        and ahora_local.minute == MINUTO_RECORDATORIO
    )


# ============================================================
# CONSTRUCCIÓN DE MENSAJES
# ============================================================

def _construir_mensaje_worker(worker: Dict[str, Any]) -> str:
    nombre = worker.get("nombre_completo", "")
    primer_nombre = nombre.split()[0] if nombre else ""
    saludo = f", {primer_nombre}" if primer_nombre else ""

    return (
        f"☀️ ¡Buenos días{saludo}!\n\n"
        f"📱 Si hoy estás trabajando, responde cualquier mensaje "
        f"para activar tu turno automáticamente.\n\n"
        f"💡 Una vez activo, podrás:\n"
        f"• Recibir y tomar tareas\n"
        f"• Reportar problemas\n"
        f"• Ver tus asignaciones"
    )


def _construir_mensaje_supervisor(
    supervisor: Dict[str, Any],
    pendientes: List[Dict[str, Any]],
    hotel_name: str,
) -> str:
    nombre = supervisor.get("nombre_completo", "")
    primer_nombre = nombre.split()[0] if nombre else ""
    saludo = f", {primer_nombre}" if primer_nombre else ""

    if not pendientes:
        return (
            f"☀️ ¡Buenos días{saludo}!\n\n"
            f"✅ No hay tickets pendientes en {hotel_name}.\n"
            f"Buen inicio de jornada."
        )

    # Separar nocturnos (creados entre 23:30 y 7:30) de diurnos
    nocturnos = []
    diurnos   = []
    for t in pendientes:
        created = t.get("created_at") or t.get("createdAt")
        if _es_nocturno(created):
            nocturnos.append(t)
        else:
            diurnos.append(t)

    lineas = [f"☀️ ¡Buenos días{saludo}! Resumen de {hotel_name}\n"]

    if nocturnos:
        lineas.append(f"🌙 Tickets nocturnos ({len(nocturnos)}):")
        for t in nocturnos[:5]:
            lineas.append(_formatear_ticket(t))
        if len(nocturnos) > 5:
            lineas.append(f"   ... y {len(nocturnos) - 5} más")
        lineas.append("")

    if diurnos:
        lineas.append(f"⏳ Pendientes del día anterior ({len(diurnos)}):")
        for t in diurnos[:5]:
            lineas.append(_formatear_ticket(t))
        if len(diurnos) > 5:
            lineas.append(f"   ... y {len(diurnos) - 5} más")

    lineas.append(f"\n📊 Total pendientes: {len(pendientes)}")
    return "\n".join(lineas)


def _es_nocturno(created_at: Any) -> bool:
    """Ticket creado entre 23:30 y 07:30 (hora Chile)."""
    if not created_at:
        return False
    try:
        from dateutil import parser
        from datetime import time as dt_time
        tz = ZoneInfo("America/Santiago")
        if isinstance(created_at, str):
            dt = parser.parse(created_at)
        else:
            dt = created_at
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=tz)
        else:
            dt = dt.astimezone(tz)
        hora = dt.time()
        return hora >= dt_time(23, 30) or hora < dt_time(7, 30)
    except Exception:
        return False


def _formatear_ticket(t: Dict[str, Any]) -> str:
    tid      = t.get("id", "?")
    # Soporta tanto formato Flask como NestJS
    ubicacion = t.get("ubicacion") or t.get("roomNumber") or t.get("habitacion") or "?"
    detalle   = (t.get("detalle") or t.get("description") or "Sin detalle")[:50]
    prioridad = (t.get("prioridad") or t.get("priority") or "MEDIA").upper()

    from gateway_app.services.mappers import PRIORITY_FROM_NESTJS
    prioridad_flask = PRIORITY_FROM_NESTJS.get(prioridad, prioridad)

    emoji = {"URGENTE": "🔴", "ALTA": "🔴", "MEDIA": "🟡", "BAJA": "🟢"}.get(
        prioridad_flask, "🟡"
    )
    # Mostrar solo primeros 8 chars del UUID para legibilidad
    tid_corto = str(tid)[:8] if len(str(tid)) > 8 else str(tid)
    return f"{emoji} #{tid_corto} · {ubicacion}\n   {detalle}"


# ============================================================
# ENVÍO DE MENSAJES
# ============================================================

def _enviar_recordatorios_property(property_data: Dict[str, Any]) -> None:
    """
    Envía recordatorios matutinos para una property específica.
    Se llama cuando es la hora correcta en la timezone de esa property.
    """
    property_id  = property_data["id"]
    hotel_name   = property_data["name"]
    wa_token     = property_data.get("whatsappWorkersCloudToken") or ""

    if not wa_token:
        logger.warning(
            "daily_scheduler: property=%s sin wa_token, omitiendo", property_id
        )
        return

    logger.info(
        "daily_scheduler: enviando recordatorios para property=%s (%s)",
        property_id, hotel_name,
    )

    from gateway_app.services.workers_db import (
        obtener_todos_workers,
        obtener_supervisores_por_area,
    )
    from gateway_app.services.tickets_db import obtener_pendientes
    from gateway_app.services.whatsapp_client import send_whatsapp_text

    # Workers — recordatorio de turno
    workers = obtener_todos_workers(property_id=property_id) or []
    for worker in workers:
        telefono = worker.get("telefono")
        if not telefono:
            continue
        try:
            msg = _construir_mensaje_worker(worker)
            send_whatsapp_text(to=telefono, body=msg, token=wa_token)
            logger.info(
                "daily_scheduler: recordatorio enviado a worker=%s",
                worker.get("nombre_completo"),
            )
        except Exception:
            logger.exception(
                "daily_scheduler: error enviando a worker=%s",
                worker.get("nombre_completo"),
            )

    # Tickets pendientes para el resumen a supervisores
    pendientes = obtener_pendientes(property_id=property_id) or []

    # Supervisores — resumen matutino por área
    # Obtener supervisores de todas las áreas (sin filtro de área)
    supervisores = obtener_supervisores_por_area("", property_id=property_id) or []

    for supervisor in supervisores:
        telefono = supervisor.get("telefono")
        if not telefono:
            continue
        try:
            msg = _construir_mensaje_supervisor(supervisor, pendientes, hotel_name)
            send_whatsapp_text(to=telefono, body=msg, token=wa_token)
            logger.info(
                "daily_scheduler: resumen enviado a supervisor=%s",
                supervisor.get("nombre_completo"),
            )
        except Exception:
            logger.exception(
                "daily_scheduler: error enviando a supervisor=%s",
                supervisor.get("nombre_completo"),
            )


# ============================================================
# LOOP PRINCIPAL
# ============================================================

# Registro de properties ya notificadas hoy — evita envíos duplicados
# key: property_id, value: fecha (YYYY-MM-DD) del último envío
_notificados_hoy: Dict[str, str] = {}


def _scheduler_loop() -> None:
    logger.info("daily_scheduler: loop iniciado")

    while True:
        try:
            ahora_utc = datetime.now(ZoneInfo("UTC"))
            fecha_utc = ahora_utc.strftime("%Y-%m-%d")

            properties = _get_properties_configuradas()

            for prop in properties:
                property_id  = prop.get("id")
                timezone_str = prop.get("timezone", "America/Santiago")

                if not property_id:
                    continue

                # Verificar si ya se notificó hoy para esta property
                if _notificados_hoy.get(property_id) == fecha_utc:
                    continue

                # Verificar si es la hora correcta en la timezone de esta property
                if not _es_hora_recordatorio(timezone_str, ahora_utc):
                    continue

                # Marcar antes de enviar para evitar doble envío si hay error parcial
                _notificados_hoy[property_id] = fecha_utc

                try:
                    _enviar_recordatorios_property(prop)
                except Exception:
                    logger.exception(
                        "daily_scheduler: error en property=%s", property_id
                    )

            # Limpiar _notificados_hoy a medianoche UTC para el día siguiente
            if ahora_utc.hour == 0 and ahora_utc.minute == 0:
                _notificados_hoy.clear()
                logger.info("daily_scheduler: registro diario limpiado (medianoche UTC)")

        except Exception:
            logger.exception("daily_scheduler: error en loop principal")

        time.sleep(_POLL_SECONDS)


def start_daily_scheduler() -> None:
    """Inicia el scheduler de recordatorios diarios."""
    enabled = (os.getenv("DAILY_SCHEDULER_ENABLED", "true") or "").lower() == "true"

    if not enabled:
        logger.info("daily_scheduler: no iniciado (DAILY_SCHEDULER_ENABLED=false)")
        return

    th = threading.Thread(
        target=_scheduler_loop,
        daemon=True,
        name="daily_scheduler",
    )
    th.start()
    logger.info("daily_scheduler: thread iniciado")
