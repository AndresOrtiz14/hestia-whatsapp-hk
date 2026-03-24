# gateway_app/services/api_client.py
"""
Cliente HTTP centralizado para el NestJS backend.
Todos los módulos del bot usan este cliente — nunca requests directo al backend.
"""
import os
import logging
import requests
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

_BASE    = os.getenv("BACKEND_API_URL", "https://hestia-saas-backend.onrender.com")
_APIKEY  = os.getenv("NESTJS_API_KEY", "")
_TIMEOUT = 10  # segundos — WhatsApp cierra el webhook a ~20s


def _headers() -> Dict[str, str]:
    return {
        "Content-Type": "application/json",
        "X-API-Key": _APIKEY,
    }


def _unwrap(resp: Any) -> Optional[Any]:
    """
    NestJS siempre devuelve {success, data, error, meta}.
    Extrae el campo data para que los callers trabajen con el payload directo.
    """
    if isinstance(resp, dict) and "success" in resp:
        return resp.get("data")
    return resp


def api_get(path: str, params: Dict = None) -> Optional[Any]:
    try:
        r = requests.get(
            f"{_BASE}{path}",
            headers=_headers(),
            params=params,
            timeout=_TIMEOUT,
        )
        r.raise_for_status()
        return _unwrap(r.json())
    except requests.HTTPError as e:
        logger.error(
            "api_get HTTPError %s %s: %s",
            e.response.status_code, path, e.response.text[:200],
        )
        return None
    except Exception:
        logger.exception("api_get failed: %s", path)
        return None


def api_post(path: str, body: Dict) -> Optional[Any]:
    try:
        r = requests.post(
            f"{_BASE}{path}",
            headers=_headers(),
            json=body,
            timeout=_TIMEOUT,
        )
        r.raise_for_status()
        if r.status_code == 204 or not r.content:
            return {}
        return _unwrap(r.json())
    except requests.HTTPError as e:
        logger.error(
            "api_post HTTPError %s %s: %s",
            e.response.status_code, path, e.response.text[:200],
        )
        return None
    except Exception:
        logger.exception("api_post failed: %s", path)
        return None


def api_put(path: str, body: Dict) -> Optional[Any]:
    try:
        r = requests.put(
            f"{_BASE}{path}",
            headers=_headers(),
            json=body,
            timeout=_TIMEOUT,
        )
        r.raise_for_status()
        if r.status_code == 204 or not r.content:
            return {}
        return _unwrap(r.json())
    except requests.HTTPError as e:
        logger.error(
            "api_put HTTPError %s %s: %s",
            e.response.status_code, path, e.response.text[:200],
        )
        return None
    except Exception:
        logger.exception("api_put failed: %s", path)
        return None


def api_patch(path: str, body: Dict) -> Optional[Any]:
    try:
        r = requests.patch(
            f"{_BASE}{path}",
            headers=_headers(),
            json=body,
            timeout=_TIMEOUT,
        )
        r.raise_for_status()
        if r.status_code == 204 or not r.content:
            return {}
        return _unwrap(r.json())
    except requests.HTTPError as e:
        logger.error(
            "api_patch HTTPError %s %s: %s",
            e.response.status_code, path, e.response.text[:200],
        )
        return None
    except Exception:
        logger.exception("api_patch failed: %s", path)
        return None
