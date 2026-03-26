# gateway_app/services/tenant_resolver.py
"""
Resuelve phone_number_id → TenantContext.

El TenantContext contiene todo lo que el bot necesita para operar
sin depender de env vars globales como ORG_ID_DEFAULT o HOTEL_ID_DEFAULT.

Flujo:
  webhook recibe phone_number_id
       ↓
  resolve_tenant(phone_number_id)
       ↓
  1. Cache en memoria  (instantáneo)
  2. Cache en disco    (sobrevive reinicios de gunicorn dentro del mismo deploy)
  3. GET /api/v1/properties/workers-phone/{phone_number_id}  (NestJS)
       ↓
  TenantContext  →  se pasa a todos los handlers y flows
"""
from __future__ import annotations

import json
import logging
import os
from dataclasses import asdict, dataclass
from typing import Optional

logger = logging.getLogger(__name__)

_CACHE_DIR = os.getenv("TENANT_CACHE_DIR", "/tmp/hestia_tenant_cache")


@dataclass
class TenantContext:
    # Identifiers
    property_id:     str   # UUID — usado en todas las llamadas al NestJS
    organization_id: str   # UUID
    hotel_name:      str
    timezone:        str   # ej: "America/Santiago"

    # WhatsApp
    phone_number_id: str   # el mismo que llegó en el webhook
    wa_token:        str   # whatsappWorkersCloudToken — para enviar mensajes


# ── Cache en memoria ──────────────────────────────────────────────────────────
_cache: dict[str, TenantContext] = {}


# ── Cache en disco (/tmp — sobrevive reinicios de gunicorn) ───────────────────

def _disk_path(phone_number_id: str) -> str:
    safe = phone_number_id.replace("/", "_")
    return os.path.join(_CACHE_DIR, f"{safe}.json")


def _load_from_disk(phone_number_id: str) -> Optional[TenantContext]:
    path = _disk_path(phone_number_id)
    try:
        with open(path) as f:
            data = json.load(f)
        return TenantContext(**data)
    except FileNotFoundError:
        return None
    except Exception:
        logger.warning("resolve_tenant: error leyendo cache disco %s", path)
        return None


def _save_to_disk(ctx: TenantContext) -> None:
    try:
        os.makedirs(_CACHE_DIR, exist_ok=True)
        with open(_disk_path(ctx.phone_number_id), "w") as f:
            json.dump(asdict(ctx), f)
    except Exception:
        logger.warning("resolve_tenant: no se pudo guardar cache disco para %s", ctx.phone_number_id)


# ── Resolución principal ──────────────────────────────────────────────────────

def resolve_tenant(phone_number_id: str) -> Optional[TenantContext]:
    """
    Busca la property que tiene este phone_number_id en
    whatsapp_workers_phone_number_id y retorna su TenantContext.

    Retorna None si no hay match — en ese caso el webhook debe
    responder 200 y salir sin procesar. Puede ser un phone_number_id
    del bot de huéspedes u otro sistema.
    """
    if not phone_number_id:
        logger.warning("resolve_tenant: phone_number_id vacío")
        return None

    # 1. Cache en memoria
    if phone_number_id in _cache:
        return _cache[phone_number_id]

    # 2. Cache en disco (sobrevive reinicios de gunicorn dentro del mismo deploy)
    ctx = _load_from_disk(phone_number_id)
    if ctx:
        logger.info(
            "resolve_tenant: cargado desde disco phone_number_id=%s → property=%s",
            phone_number_id, ctx.property_id,
        )
        _cache[phone_number_id] = ctx
        return ctx

    # 3. API NestJS
    from gateway_app.services.api_client import api_get

    data = api_get(f"/api/v1/properties/workers-phone/{phone_number_id}")

    if not data:
        logger.warning(
            "resolve_tenant: no property para phone_number_id=%s", phone_number_id
        )
        return None

    wa_token = data.get("whatsappWorkersCloudToken") or ""
    if not wa_token:
        logger.warning(
            "resolve_tenant: property=%s no tiene whatsappWorkersCloudToken configurado",
            data.get("id"),
        )

    ctx = TenantContext(
        property_id=     data["id"],
        organization_id= data["organizationId"],
        hotel_name=      data["name"],
        timezone=        data.get("timezone", "America/Santiago"),
        phone_number_id= phone_number_id,
        wa_token=        wa_token,
    )

    _cache[phone_number_id] = ctx
    _save_to_disk(ctx)
    logger.info(
        "resolve_tenant: phone_number_id=%s → property=%s (%s)",
        phone_number_id, ctx.property_id, ctx.hotel_name,
    )
    return ctx


def invalidate_cache(phone_number_id: str = None) -> None:
    """
    Invalida el cache de tenant (memoria y disco).
    - Sin argumento: limpia todo.
    - Con phone_number_id: limpia solo ese entry.
    """
    if phone_number_id:
        _cache.pop(phone_number_id, None)
        try:
            os.remove(_disk_path(phone_number_id))
        except FileNotFoundError:
            pass
        logger.info("resolve_tenant: cache invalidado para phone_number_id=%s", phone_number_id)
    else:
        _cache.clear()
        try:
            import shutil
            shutil.rmtree(_CACHE_DIR, ignore_errors=True)
        except Exception:
            pass
        logger.info("resolve_tenant: cache completo invalidado")
