# gateway_app/services/ticket_watch.py
from __future__ import annotations

import logging
import os
import re
import threading
import time
from typing import Any, Dict, List, Optional

from gateway_app.services.db import execute, fetchall, fetchone, using_pg
from gateway_app.services.whatsapp_client import send_whatsapp_text
from gateway_app.core.utils.location_format import formatear_ubicacion_para_mensaje


logger = logging.getLogger(__name__)

_TABLE_NOTIFS_PG = "public.runtime_ticket_supervisor_notifs"
_TABLE_NOTIFS_SQLITE = "runtime_ticket_supervisor_notifs"


def _normalize_phone(phone: str) -> str:
    return re.sub(r"\D", "", (phone or "").strip())


def _get_supervisor_phones() -> List[str]:
    raw = os.getenv("SUPERVISOR_PHONES", "") or ""
    phones = [_normalize_phone(p) for p in raw.split(",")]
    return [p for p in phones if p]


def _priority_emoji(prioridad: Optional[str]) -> str:
    p = (prioridad or "").upper().strip()
    return {"ALTA": "🔴", "MEDIA": "🟡", "BAJA": "🟢"}.get(p, "🟡")


def _ensure_notif_table_exists() -> None:
    """
    Dedupe table: one row per ticket_id we already notified.
    Safe to call multiple times.
    """
    if using_pg():
        sql = f"""
        CREATE TABLE IF NOT EXISTS {_TABLE_NOTIFS_PG} (
            ticket_id BIGINT PRIMARY KEY,
            notified_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
        execute(sql, commit=True)
    else:
        sql = f"""
        CREATE TABLE IF NOT EXISTS {_TABLE_NOTIFS_SQLITE} (
            ticket_id INTEGER PRIMARY KEY,
            notified_at TEXT NOT NULL
        )
        """
        execute(sql, commit=True)


def _claim_ticket(ticket_id: int) -> bool:
    """
    Atomic claim: only one process will "win" per ticket_id.
    """
    if using_pg():
        row = fetchone(
            f"""
            INSERT INTO {_TABLE_NOTIFS_PG} (ticket_id)
            VALUES (?)
            ON CONFLICT (ticket_id) DO NOTHING
            RETURNING ticket_id
            """,
            [ticket_id],
        )
        return bool(row)
    else:
        existing = fetchone(
            f"SELECT ticket_id FROM {_TABLE_NOTIFS_SQLITE} WHERE ticket_id = ?",
            [ticket_id],
        )
        if existing:
            return False
        execute(
            f"INSERT INTO {_TABLE_NOTIFS_SQLITE} (ticket_id, notified_at) VALUES (?, CURRENT_TIMESTAMP)",
            [ticket_id],
            commit=True,
        )
        return True


def _fetch_recent_guest_tickets(org_id: int, hotel_id: int, lookback_minutes: int) -> List[Dict[str, Any]]:
    """
    Fetch recent tickets created by the guest bot.
    Filters:
      - org_id/hotel_id
      - canal_origen = 'huesped_whatsapp'
      - estado looks pending-ish
      - created_at within lookback window
    """
    table = "public.tickets" if using_pg() else "tickets"

    # Treat both as “pending”
    pending_states = ("PENDIENTE", "PENDIENTE_APROBACION", "PENDIENTE_APROBACIÓN")

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
            created_at,
            huesped_phone,
            huesped_nombre
        FROM {table}
        WHERE org_id = ?
          AND hotel_id = ?
          AND canal_origen = 'huesped_whatsapp'
          AND estado IN ({",".join(["?"] * len(pending_states))})
          AND created_at >= NOW() - (?::int * INTERVAL '1 minute')
        ORDER BY created_at DESC
        LIMIT 50
        """
        params = [org_id, hotel_id, *pending_states, int(lookback_minutes)]
        return fetchall(sql, params)

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
        created_at
    FROM {table}
    WHERE org_id = ?
      AND hotel_id = ?
      AND canal_origen = 'huesped_whatsapp'
      AND estado IN ({",".join(["?"] * len(pending_states))})
    ORDER BY created_at DESC
    LIMIT 50
    """
    params = [org_id, hotel_id, *pending_states]
    return fetchall(sql, params)


def _build_supervisor_message(ticket: Dict[str, Any]) -> str:
    ticket_id = int(ticket.get("id"))
    raw_ubicacion = ticket.get("ubicacion") or ticket.get("habitacion") or "—"
    area = (ticket.get("area") or "HOUSEKEEPING").upper()
    ubicacion = formatear_ubicacion_para_mensaje(raw_ubicacion, area)

    detalle = (ticket.get("detalle") or "").strip()
    prioridad = (ticket.get("prioridad") or "MEDIA").upper()
    area = (ticket.get("area") or "HOUSEKEEPING").upper()

    # Guest identity (best-effort)
    guest_name = (ticket.get("huesped_nombre") or "").strip()
    guest_phone = _normalize_phone(ticket.get("huesped_phone") or ticket.get("huesped_id") or "")
    actor = guest_name or ("Huésped " + guest_phone if guest_phone else "Huésped")

    p_emoji = _priority_emoji(prioridad)

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

    _ensure_notif_table_exists()

    while True:
        try:
            tickets = _fetch_recent_guest_tickets(org_id, hotel_id, lookback_minutes) or []
            # Iterate oldest -> newest so messages arrive in order
            for t in reversed(tickets):
                tid = t.get("id")
                if tid is None:
                    continue
                try:
                    tid_int = int(tid)
                except Exception:
                    continue

                if not _claim_ticket(tid_int):
                    continue  # already notified by another process

                msg = _build_supervisor_message(t)
                for sup in supervisors:
                    try:
                        send_whatsapp_text(to=sup, body=msg)
                    except Exception as e:
                        logger.warning("TICKET_WATCH send failed ticket_id=%s to=%s err=%s", tid_int, sup, e)

                logger.info("TICKET_WATCH notified ticket_id=%s supervisors=%s", tid_int, supervisors)

        except Exception:
            logger.exception("TICKET_WATCH loop error")

        time.sleep(max(2, int(poll_seconds)))


def start_ticket_watch() -> None:
    """
    Start background watcher thread (per gunicorn worker).
    Dedupe is guaranteed via runtime_ticket_supervisor_notifs table.
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
