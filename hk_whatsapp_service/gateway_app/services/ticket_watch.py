# gateway_app/services/ticket_watch.py
from __future__ import annotations

import logging
import os
import re
import threading
import time
from typing import Any, Dict, List, Optional

from gateway_app.services.db import execute, fetchall, using_pg
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


def _fetch_recent_guest_tickets(org_id: int, hotel_id: int, lookback_minutes: int) -> List[Dict[str, Any]]:
    """
    Fetch recent tickets created by the guest bot that still need supervisor notification.

    Uses tickets.assignment_notif_sent as dedupe (no extra tables needed).

    Requires columns (per your CSV):
      - id, org_id, hotel_id, area, prioridad, estado, detalle, canal_origen, ubicacion,
        huesped_id, huesped_whatsapp, created_at, assignment_notif_sent
    """
    table = "public.tickets" if using_pg() else "tickets"

    # Treat both as “pending”
    pending_states = ("PENDIENTE", "PENDIENTE_APROBACION", "PENDIENTE_APROBACIÓN")
    in_states = ",".join(["?"] * len(pending_states))

    if using_pg():
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
          AND created_at >= NOW() - (? * INTERVAL '1 minute')
        ORDER BY created_at ASC
        LIMIT 100
        """
        params = [org_id, hotel_id, *pending_states, int(lookback_minutes)]
        return fetchall(sql, params) or []

    # SQLite fallback
    # NOTE: SQLite datetime arithmetic uses modifiers like '-10 minutes'
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


def _mark_ticket_notified(ticket_id: int) -> None:
    table = "public.tickets" if using_pg() else "tickets"

    if using_pg():
        sql = f"UPDATE {table} SET assignment_notif_sent = true WHERE id = ?"
        execute(sql, [ticket_id], commit=True)
    else:
        # SQLite booleans are typically 0/1
        sql = f"UPDATE {table} SET assignment_notif_sent = 1 WHERE id = ?"
        execute(sql, [ticket_id], commit=True)


def _build_supervisor_message(ticket: Dict[str, Any]) -> str:
    ticket_id = int(ticket.get("id"))

    raw_ubicacion = ticket.get("ubicacion") or ticket.get("habitacion") or "—"
    area = (ticket.get("area") or "HOUSEKEEPING").upper()
    ubicacion = formatear_ubicacion_para_mensaje(raw_ubicacion, area)

    detalle = (ticket.get("detalle") or "").strip()
    prioridad = (ticket.get("prioridad") or "MEDIA").upper()
    p_emoji = _priority_emoji(prioridad)

    # Guest identity (best-effort) - your table has huesped_whatsapp + huesped_id
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
    logger.info(
        "TICKET_WATCH started org_id=%s hotel_id=%s poll=%ss lookback=%smin",
        org_id, hotel_id, poll_seconds, lookback_minutes
    )

    supervisors = _get_supervisor_phones()
    if not supervisors:
        logger.warning("TICKET_WATCH disabled: SUPERVISOR_PHONES empty")
        return

    while True:
        try:
            tickets = _fetch_recent_guest_tickets(org_id, hotel_id, lookback_minutes)
            logger.info("TICKET_WATCH fetched=%s", len(tickets))

            for t in tickets:
                tid = t.get("id")
                if tid is None:
                    continue
                try:
                    tid_int = int(tid)
                except Exception:
                    continue

                msg = _build_supervisor_message(t)

                any_sent = False
                for sup in supervisors:
                    try:
                        send_whatsapp_text(to=sup, body=msg)
                        any_sent = True
                    except Exception as e:
                        logger.warning(
                            "TICKET_WATCH send failed ticket_id=%s to=%s err=%s",
                            tid_int, sup, e
                        )

                # Dedupe: mark as notified if we managed to send to at least one supervisor
                # (prevents infinite retry loops on bad data / message formats).
                if any_sent:
                    try:
                        _mark_ticket_notified(tid_int)
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
    Start background watcher thread (per gunicorn worker).

    Dedupe strategy:
      - Uses tickets.assignment_notif_sent (no extra tables, compatible with SKIP_MIGRATIONS=true).
    """
    enabled = (os.getenv("TICKET_WATCH_ENABLED", "true") or "").lower() == "true"
    if not enabled:
        logger.info("TICKET_WATCH not started (TICKET_WATCH_ENABLED=false)")
        return

    org_id = int(os.getenv("ORG_ID_DEFAULT", "1"))
    hotel_id = int(os.getenv("HOTEL_ID_DEFAULT", "1"))
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
