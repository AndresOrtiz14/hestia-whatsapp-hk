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
  GET /api/v1/properties/workers-phone/{phone_number_id}  (NestJS)
       ↓
  TenantContext  →  se pasa a todos los handlers y flows
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)


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

    # Los supervisores ya NO vienen de env vars.
    # Se consultan dinámicamente por área desde GET /users/supervisors
    # cuando el bot necesita notificar un ticket.


# Cache en memoria por phone_number_id.
# Se invalida reiniciando el servicio si cambia la configuración de la property.
# Con Gunicorn multi-worker cada proceso tiene su propia copia — es aceptable
# porque son datos de configuración que no cambian frecuentemente.
_cache: dict[str, TenantContext] = {}


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

    if phone_number_id in _cache:
        return _cache[phone_number_id]

    from gateway_app.services.api_client import api_get

    # api_client ya desenvuelve {success, data, ...} → devuelve el campo data directamente
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
        # No bloqueamos — el token puede estar en env var como fallback

    ctx = TenantContext(
        property_id=     data["id"],
        organization_id= data["organizationId"],
        hotel_name=      data["name"],
        timezone=        data.get("timezone", "America/Santiago"),
        phone_number_id= phone_number_id,
        wa_token=        wa_token,
    )

    _cache[phone_number_id] = ctx
    logger.info(
        "resolve_tenant: phone_number_id=%s → property=%s (%s)",
        phone_number_id, ctx.property_id, ctx.hotel_name,
    )
    return ctx


def invalidate_cache(phone_number_id: str = None) -> None:
    """
    Invalida el cache de tenant.
    - Sin argumento: limpia todo el cache.
    - Con phone_number_id: limpia solo ese entry.
    Útil para tests y para forzar re-fetch tras cambios de configuración.
    """
    if phone_number_id:
        _cache.pop(phone_number_id, None)
        logger.info("resolve_tenant: cache invalidado para phone_number_id=%s", phone_number_id)
    else:
        _cache.clear()
        logger.info("resolve_tenant: cache completo invalidado")
