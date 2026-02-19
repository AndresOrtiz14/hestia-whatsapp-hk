# gateway_app/services/media_storage.py
"""
Servicio de almacenamiento de medios.
Descarga archivos de WhatsApp Cloud API, los OPTIMIZA, y los sube a Supabase Storage.
"""

import logging
import requests
import uuid
import io
from datetime import datetime
from typing import Optional, Tuple
from gateway_app.config import Config

logger = logging.getLogger(__name__)

# ============================================================
# CONFIGURACIÓN DE OPTIMIZACIÓN
# ============================================================
IMAGE_MAX_WIDTH = 1280          # Ancho máximo en píxeles
IMAGE_MAX_HEIGHT = 1280         # Alto máximo en píxeles
JPEG_QUALITY = 85               # Calidad JPEG (1-100, 85 es buen balance)
CONVERT_TO_JPEG = True          # Convertir PNG/WebP a JPEG para ahorrar espacio

# Configuración de Supabase Storage
STORAGE_BUCKET = "ticket-media"


def _get_supabase_config():
    """Obtiene configuración de Supabase desde environment."""
    import os
    
    url = os.getenv("SUPABASE_URL", "")
    key = os.getenv("SUPABASE_SERVICE_KEY", "")
    
    if not url or not key:
        logger.warning("⚠️ SUPABASE_URL o SUPABASE_SERVICE_KEY no configurados")
        return None, None
    
    return url, key


def optimize_image(image_data: bytes, mime_type: str) -> Tuple[bytes, str, int]:
    """
    Optimiza una imagen: redimensiona y comprime.
    
    Args:
        image_data: Bytes de la imagen original
        mime_type: Tipo MIME original (image/jpeg, image/png, etc.)
    
    Returns:
        (bytes_optimizados, nuevo_mime_type, tamaño_original)
    """
    try:
        from PIL import Image
        
        original_size = len(image_data)
        
        # Abrir imagen desde bytes
        img = Image.open(io.BytesIO(image_data))
        
        # Obtener dimensiones originales
        original_width, original_height = img.size
        logger.info(f"📐 Imagen original: {original_width}x{original_height}, {original_size/1024:.1f}KB")
        
        # Calcular nuevas dimensiones manteniendo aspect ratio
        needs_resize = original_width > IMAGE_MAX_WIDTH or original_height > IMAGE_MAX_HEIGHT
        
        if needs_resize:
            # Calcular ratio para que quepa en el box máximo
            ratio = min(IMAGE_MAX_WIDTH / original_width, IMAGE_MAX_HEIGHT / original_height)
            new_width = int(original_width * ratio)
            new_height = int(original_height * ratio)
            
            # Redimensionar con alta calidad
            img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)
            logger.info(f"📐 Redimensionado a: {new_width}x{new_height}")
        
        # Convertir a RGB si es necesario (para JPEG)
        if img.mode in ('RGBA', 'P', 'LA'):
            # Crear fondo blanco para transparencias
            background = Image.new('RGB', img.size, (255, 255, 255))
            if img.mode == 'P':
                img = img.convert('RGBA')
            background.paste(img, mask=img.split()[-1] if img.mode == 'RGBA' else None)
            img = background
        elif img.mode != 'RGB':
            img = img.convert('RGB')
        
        # Guardar como JPEG optimizado
        output = io.BytesIO()
        img.save(
            output, 
            format='JPEG', 
            quality=JPEG_QUALITY,
            optimize=True,
            progressive=True  # JPEG progresivo carga mejor en web
        )
        
        optimized_data = output.getvalue()
        optimized_size = len(optimized_data)
        
        savings = ((original_size - optimized_size) / original_size) * 100
        logger.info(f"✅ Optimizado: {optimized_size/1024:.1f}KB (ahorro: {savings:.1f}%)")
        
        return optimized_data, "image/jpeg", original_size
        
    except ImportError:
        logger.warning("⚠️ Pillow no instalado, subiendo imagen sin optimizar")
        return image_data, mime_type, len(image_data)
    except Exception as e:
        logger.exception(f"⚠️ Error optimizando imagen: {e}, subiendo sin optimizar")
        return image_data, mime_type, len(image_data)


def download_whatsapp_media(media_id: str) -> dict:
    """
    Descarga un archivo de WhatsApp Cloud API.
    
    Args:
        media_id: ID del media recibido en el webhook
    
    Returns:
        {"success": True, "data": bytes, "mime_type": str, "size": int}
        {"success": False, "error": str}
    """
    token = Config.WHATSAPP_TOKEN
    
    if not token:
        return {"success": False, "error": "WHATSAPP_TOKEN no configurado"}
    
    try:
        # Paso 1: Obtener URL del media
        url_info = f"https://graph.facebook.com/v18.0/{media_id}"
        headers = {"Authorization": f"Bearer {token}"}
        
        logger.info(f"📥 Obteniendo URL para media_id: {media_id}")
        resp = requests.get(url_info, headers=headers, timeout=30)
        
        if resp.status_code != 200:
            logger.error(f"❌ Error obteniendo URL: {resp.status_code} - {resp.text}")
            return {"success": False, "error": f"Error obteniendo URL: {resp.status_code}"}
        
        media_data = resp.json()
        media_url = media_data.get("url")
        mime_type = media_data.get("mime_type", "application/octet-stream")
        file_size = media_data.get("file_size", 0)
        
        if not media_url:
            return {"success": False, "error": "No se obtuvo URL del media"}
        
        # Paso 2: Descargar el archivo
        logger.info(f"📥 Descargando archivo ({mime_type}, {file_size} bytes)...")
        resp_file = requests.get(media_url, headers=headers, timeout=60)
        
        if resp_file.status_code != 200:
            logger.error(f"❌ Error descargando: {resp_file.status_code}")
            return {"success": False, "error": f"Error descargando: {resp_file.status_code}"}
        
        logger.info(f"✅ Archivo descargado: {len(resp_file.content)} bytes")
        
        return {
            "success": True,
            "data": resp_file.content,
            "mime_type": mime_type,
            "size": len(resp_file.content)
        }
        
    except requests.Timeout:
        logger.error("❌ Timeout descargando media")
        return {"success": False, "error": "Timeout descargando archivo"}
    except Exception as e:
        logger.exception(f"❌ Error descargando media: {e}")
        return {"success": False, "error": str(e)}


def upload_to_supabase(
    file_data: bytes,
    mime_type: str,
    folder: str = "tickets",
    filename: Optional[str] = None
) -> dict:
    """
    Sube un archivo a Supabase Storage.
    
    Args:
        file_data: Bytes del archivo
        mime_type: Tipo MIME (image/jpeg, video/mp4, etc.)
        folder: Carpeta dentro del bucket
        filename: Nombre del archivo (se genera UUID si no se provee)
    
    Returns:
        {"success": True, "url": str, "path": str}
        {"success": False, "error": str}
    """
    supabase_url, supabase_key = _get_supabase_config()
    
    if not supabase_url or not supabase_key:
        logger.warning("⚠️ Supabase no configurado, no se puede subir archivo")
        return {"success": False, "error": "Supabase Storage no configurado"}
    
    try:
        # Generar nombre único
        if not filename:
            ext = _get_extension(mime_type)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"{timestamp}_{uuid.uuid4().hex[:8]}{ext}"
        
        file_path = f"{folder}/{filename}"
        
        # URL de upload
        upload_url = f"{supabase_url}/storage/v1/object/{STORAGE_BUCKET}/{file_path}"
        
        headers = {
            "Authorization": f"Bearer {supabase_key}",
            "Content-Type": mime_type,
            "x-upsert": "true"
        }
        
        logger.info(f"📤 Subiendo a Supabase: {file_path} ({len(file_data)/1024:.1f}KB)")
        resp = requests.post(upload_url, headers=headers, data=file_data, timeout=60)
        
        if resp.status_code not in (200, 201):
            logger.error(f"❌ Error subiendo a Supabase: {resp.status_code} - {resp.text}")
            return {"success": False, "error": f"Error subiendo: {resp.status_code}"}
        
        # URL pública del archivo
        public_url = f"{supabase_url}/storage/v1/object/public/{STORAGE_BUCKET}/{file_path}"
        
        logger.info(f"✅ Archivo subido: {public_url}")
        
        return {
            "success": True,
            "url": public_url,
            "path": file_path
        }
        
    except Exception as e:
        logger.exception(f"❌ Error subiendo a Supabase: {e}")
        return {"success": False, "error": str(e)}


def process_and_store_media(
    media_id: str,
    media_type: str,
    ticket_id: Optional[int] = None,
    uploaded_by: str = ""
) -> dict:
    """
    Proceso completo: descarga de WhatsApp + OPTIMIZACIÓN + upload a Supabase + registro en BD.
    
    Args:
        media_id: ID del media de WhatsApp
        media_type: "image" o "video"
        ticket_id: ID del ticket asociado (puede ser None si aún no existe)
        uploaded_by: Teléfono del usuario que envió el media
    
    Returns:
        {
            "success": True,
            "storage_url": str,
            "media_id": str,
            "mime_type": str,
            "size": int,
            "original_size": int,
            "db_id": int
        }
        {"success": False, "error": str}
    """
    # Paso 1: Descargar de WhatsApp
    download_result = download_whatsapp_media(media_id)
    
    if not download_result["success"]:
        return download_result
    
    file_data = download_result["data"]
    mime_type = download_result["mime_type"]
    original_size = download_result["size"]
    
    # Paso 2: OPTIMIZAR si es imagen
    if media_type == "image" and mime_type.startswith("image/"):
        file_data, mime_type, _ = optimize_image(file_data, mime_type)
    
    file_size = len(file_data)
    
    # Paso 3: Subir a Supabase
    folder = f"tickets/{ticket_id}" if ticket_id else "pending"
    upload_result = upload_to_supabase(file_data, mime_type, folder=folder)
    
    storage_url = None
    if upload_result["success"]:
        storage_url = upload_result["url"]
    else:
        logger.warning(f"⚠️ No se pudo subir a Supabase, guardando solo media_id")
    
    # Paso 4: Guardar en BD (si hay ticket_id)
    db_id = None
    if ticket_id:
        try:
            from gateway_app.services.tickets_db import agregar_media_a_ticket
            db_id = agregar_media_a_ticket(
                ticket_id=ticket_id,
                media_type=media_type,
                storage_url=storage_url or "",
                whatsapp_media_id=media_id,
                mime_type=mime_type,
                file_size_bytes=file_size,
                uploaded_by=uploaded_by
            )
        except Exception as e:
            logger.exception(f"⚠️ Error guardando media en BD: {e}")
    
    return {
        "success": True,
        "storage_url": storage_url,
        "media_id": media_id,
        "mime_type": mime_type,
        "size": file_size,
        "original_size": original_size,
        "db_id": db_id
    }


def _get_extension(mime_type: str) -> str:
    """Obtiene extensión de archivo desde MIME type."""
    extensions = {
        "image/jpeg": ".jpg",
        "image/png": ".jpg",      # Convertimos a JPG
        "image/gif": ".gif",      # GIF mantiene (puede ser animado)
        "image/webp": ".jpg",     # Convertimos a JPG
        "video/mp4": ".mp4",
        "video/3gpp": ".3gp",
        "video/quicktime": ".mov",
        "audio/ogg": ".ogg",
        "audio/mpeg": ".mp3",
        "application/pdf": ".pdf",
    }
    return extensions.get(mime_type, ".bin")


def get_media_url_for_whatsapp(media_id: str) -> Optional[str]:
    """
    Obtiene la URL temporal de WhatsApp para reenviar un media.
    Útil para reenviar fotos al supervisor.
    """
    token = Config.WHATSAPP_TOKEN
    
    try:
        url_info = f"https://graph.facebook.com/v18.0/{media_id}"
        headers = {"Authorization": f"Bearer {token}"}
        
        resp = requests.get(url_info, headers=headers, timeout=10)
        
        if resp.status_code == 200:
            return resp.json().get("url")
        
        return None
        
    except Exception as e:
        logger.exception(f"Error obteniendo URL de media: {e}")
        return None