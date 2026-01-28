# gateway_app/services/ticket_watch.py
from __future__ import annotations

import logging
import os
import re
import threading
import time
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

from gateway_app.services.db import execute, fetchall, fetchone, using_pg
from gateway_app.services.whatsapp_client import send_whatsapp_text
from gateway_app.core.utils.location_format import formatear_ubicacion_para_mensaje

logger = logging.getLogger(__name__)


def _normalize_phone(phone: str) -> str:
    return re.sub(r"\D", "", (phone or "").strip())


def _get_supervisor_phones() -> List[str]:
    raw = os.getenv("SUPERVISOR_PHONES", "") or ""
    phones = [_normalize_phone(p) for p in raw.split(",")]
    return [p for p in phones if p]


def _priority_emoji(prioridad: Optional[str]) -> str:
    p = (prioridad or "").upper().strip()
    return {"ALTA": "🔴", "MEDIA": "🟡", "BAJA": "🟢"}.get(p, "🟡")


def _db_hint() -> str:
    """
    Best-effort DB identity without leaking creds.
    """
    dsn = os.getenv("DATABASE_URL", "") or ""
    if not dsn:
        return "DATABASE_URL=∅ (sqlite?)"
    try:
        u = urlparse(dsn)
        host = u.hostname or "?"
        port = u.port or "?"
        db = (u.path or "").lstrip("/") or "?"
        return f"pg://{host}:{port}/{db}"
    except Exception:
        return "DATABASE_URL=(unparsed)"


def _tickets_table() -> str:
    return "public.tickets" if using_pg() else "tickets"


def _fetch_recent_guest_tickets(org_id: int, hotel_id: int, lookback_minutes: int) -> List[Dict[str, Any]]:
    """
    Fetch tickets created by guest bot that still need supervisor notification.

    Requires columns (per your CSV):
      - id, org_id, hotel_id, area, prioridad, estado, detalle, canal_origen, ubicacion,
        huesped_id, huesped_whatsapp, created_at, assignment_notif_sent
    """
    table = _tickets_table()

    pending_states = ("PENDIENTE", "PENDIENTE_APROBACION", "PENDIENTE_APROBACIÓN")
    in_states = ",".join(["?"] * len(pending_states))

    if using_pg():
        # Safer interval math: NOW() - (INTERVAL '1 minute' * ?)
        sql = f"""
        SELECT
            id,
            org_id,
            hotel_id,
            area,
            prioridad,
            estado,
            detalle,
            canal_origen,
            ubicacion,
            huesped_id,
            huesped_whatsapp,
            created_at,
            assignment_notif_sent
        FROM {table}
        WHERE org_id = ?
          AND hotel_id = ?
          AND canal_origen = 'huesped_whatsapp'
          AND estado IN ({in_states})
          AND (assignment_notif_sent IS NULL OR assignment_notif_sent = false)
          AND created_at >= NOW() - (INTERVAL '1 minute' * ?)
        ORDER BY created_at ASC
        LIMIT 100
        """
        params = [org_id, hotel_id, *pending_states, int(lookback_minutes)]
        return fetchall(sql, params) or []

    # SQLite fallback
    sql = f"""
    SELECT
        id,
        org_id,
        hotel_id,
        area,
        prioridad,
        estado,
        detalle,
        canal_origen,
        ubicacion,
        huesped_id,
        huesped_whatsapp,
        created_at,
        assignment_notif_sent
    FROM {table}
    WHERE org_id = ?
      AND hotel_id = ?
      AND canal_origen = 'huesped_whatsapp'
      AND estado IN ({in_states})
      AND (assignment_notif_sent IS NULL OR assignment_notif_sent = 0)
      AND datetime(created_at) >= datetime('now', '-' || ? || ' minutes')
    ORDER BY datetime(created_at) ASC
    LIMIT 100
    """
    params = [org_id, hotel_id, *pending_states, int(lookback_minutes)]
    return fetchall(sql, params) or []


def _diagnostic_sample(org_id: int, hotel_id: int) -> None:
    """
    When fetched=0, log last few tickets so we know what filter mismatched.
    """
    try:
        table = _tickets_table()
        sql = f"""
        SELECT id, org_id, hotel_id, canal_origen, estado, created_at, assignment_notif_sent
        FROM {table}
        WHERE org_id = ?
          AND hotel_id = ?
        ORDER BY created_at DESC
        LIMIT 5
        """
        rows = fetchall(sql, [org_id, hotel_id]) or []
        if not rows:
            logger.warning("TICKET_WATCH diag: no tickets found for org_id=%s hotel_id=%s", org_id, hotel_id)
            return

        # Compact summary
        summary = [
            {
                "id": r.get("id"),
                "canal": r.get("canal_origen"),
                "estado": r.get("estado"),
                "created_at": str(r.get("created_at")),
                "notif": r.get("assignment_notif_sent"),
            }
            for r in rows
        ]
        logger.warning("TICKET_WATCH diag last_tickets=%s", summary)
    except Exception:
        logger.exception("TICKET_WATCH diag failed")


def _claim_ticket_atomic_pg(ticket_id: int) -> bool:
    """
    Postgres-only atomic claim to ensure exactly-once across multiple instances.
    Returns True only for the process that successfully flips the flag.
    """
    table = _tickets_table()
    row = fetchone(
        f"""
        UPDATE {table}
        SET assignment_notif_sent = true
        WHERE id = ?
          AND (assignment_notif_sent IS NULL OR assignment_notif_sent = false)
        RETURNING id
        """,
        [ticket_id],
    )
    return bool(row)


def _mark_ticket_notified_sqlite(ticket_id: int) -> None:
    table = _tickets_table()
    execute(f"UPDATE {table} SET assignment_notif_sent = 1 WHERE id = ?", [ticket_id], commit=True)


def _build_supervisor_message(ticket: Dict[str, Any]) -> str:
    ticket_id = int(ticket.get("id"))

    raw_ubicacion = ticket.get("ubicacion") or ticket.get("habitacion") or "—"
    area = (ticket.get("area") or "HOUSEKEEPING").upper()
    ubicacion = formatear_ubicacion_para_mensaje(raw_ubicacion, area)

    detalle = (ticket.get("detalle") or "").strip()
    prioridad = (ticket.get("prioridad") or "MEDIA").upper()
    p_emoji = _priority_emoji(prioridad)

    guest_phone = _normalize_phone(ticket.get("huesped_whatsapp") or ticket.get("huesped_id") or "")
    actor = f"Huésped {guest_phone}" if guest_phone else "Huésped"

    return (
        f"📋 Nuevo reporte de {actor}\n\n"
        f"#{ticket_id} · {ubicacion}\n"
        f"{detalle}\n"
        f"{p_emoji} Prioridad: {prioridad}\n"
        f"🧩 Área: {area}\n\n"
        f"💡 Di 'asignar {ticket_id} a [nombre]' para derivar"
    )


def _watch_loop(org_id: int, hotel_id: int, poll_seconds: int, lookback_minutes: int) -> None:
    """
    Loop de vigilancia de tickets de huéspedes.
    ✅ MODIFICADO: Solo notifica a supervisores en horario laboral (7:30 AM - 11:30 PM)
    """
    from gateway_app.core.utils.horario import esta_en_horario_laboral
    
    supervisors = _get_supervisor_phones()
    logger.info(
        "TICKET_WATCH started db=%s org_id=%s hotel_id=%s poll=%ss lookback=%smin supervisors=%s",
        _db_hint(), org_id, hotel_id, poll_seconds, lookback_minutes, supervisors
    )

    if not supervisors:
        logger.warning("TICKET_WATCH disabled: SUPERVISOR_PHONES empty")
        return

    while True:
        try:
            # ====================================================================
            # ✅ NUEVO: CHECK DE HORARIO AL INICIO DEL LOOP
            # ====================================================================
            en_horario = esta_en_horario_laboral()
            
            if not en_horario:
                # 🌙 FUERA DE HORARIO: No procesar ni notificar
                logger.debug("🌙 TICKET_WATCH: Fuera de horario laboral - no se procesan notificaciones")
                time.sleep(max(2, int(poll_seconds)))
                continue  # ← Saltar esta iteración
            # ====================================================================
            
            tickets = _fetch_recent_guest_tickets(org_id, hotel_id, lookback_minutes)
            logger.info("TICKET_WATCH fetched=%s", len(tickets))

            if not tickets:
                # Only occasionally log diagnostics to avoid log spam
                _diagnostic_sample(org_id, hotel_id)

            for t in tickets:
                tid = t.get("id")
                if tid is None:
                    continue
                try:
                    tid_int = int(tid)
                except Exception:
                    continue

                # EXACTLY ONCE claim
                if using_pg():
                    claimed = _claim_ticket_atomic_pg(tid_int)
                    if not claimed:
                        continue  # already claimed by another instance
                # SQLite: we mark after send (single-process typical)

                msg = _build_supervisor_message(t)

                # ✅ Logging mejorado: Indicar que se notifica EN horario
                logger.info(f"✅ TICKET_WATCH: Notificando ticket #{tid_int} (EN horario laboral)")
                
                any_sent = False
                for sup in supervisors:
                    try:
                        send_whatsapp_text(to=sup, body=msg)
                        any_sent = True
                    except Exception as e:
                        logger.warning("TICKET_WATCH send failed ticket_id=%s to=%s err=%s", tid_int, sup, e)

                if using_pg():
                    # Postgres: already marked true in the atomic claim.
                    if any_sent:
                        logger.info("TICKET_WATCH notified ticket_id=%s supervisors=%s", tid_int, supervisors)
                    else:
                        # If all sends failed, we currently *keep it claimed* to prevent infinite retries.
                        # If you prefer retries, we can revert flag on failure.
                        logger.warning("TICKET_WATCH all sends failed ticket_id=%s (claimed=true)", tid_int)
                else:
                    if any_sent:
                        try:
                            _mark_ticket_notified_sqlite(tid_int)
                            logger.info("TICKET_WATCH notified ticket_id=%s supervisors=%s", tid_int, supervisors)
                        except Exception:
                            logger.exception("TICKET_WATCH failed to mark notified ticket_id=%s", tid_int)
                    else:
                        logger.warning("TICKET_WATCH no sends succeeded ticket_id=%s (will retry)", tid_int)

        except Exception:
            logger.exception("TICKET_WATCH loop error")

        time.sleep(max(2, int(poll_seconds)))


def start_ticket_watch() -> None:
    """
    Start background watcher thread.

    Dedupe:
      - Postgres: atomic UPDATE ... RETURNING claim using tickets.assignment_notif_sent
      - SQLite: marks after send
    """
    enabled = (os.getenv("TICKET_WATCH_ENABLED", "true") or "").lower() == "true"
    if not enabled:
        logger.info("TICKET_WATCH not started (TICKET_WATCH_ENABLED=false)")
        return

    org_id = int(os.getenv("ORG_ID_DEFAULT", "5"))
    hotel_id = int(os.getenv("HOTEL_ID_DEFAULT", "6"))
    poll_seconds = int(os.getenv("TICKET_WATCH_POLL_SECONDS", "5"))
    lookback_minutes = int(os.getenv("TICKET_WATCH_LOOKBACK_MINUTES", "1440"))

    th = threading.Thread(
        target=_watch_loop,
        args=(org_id, hotel_id, poll_seconds, lookback_minutes),
        daemon=True,
        name="ticket_watch",
    )
    th.start()
    logger.info("TICKET_WATCH thread started")
