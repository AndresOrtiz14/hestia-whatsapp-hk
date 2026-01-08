"""
Datos de demo para el bot de Supervisión.
Tickets y mucamas de prueba.
"""

from datetime import datetime, timedelta
from typing import List, Dict, Any


# Demo: Workers registrados (todos los roles del hotel)
DEMO_WORKERS = [
    {
        "phone": "56912345671",
        "nombre": "María",
        "apellido": "González",
        "nombre_completo": "María González",
        "apodos": ["Mari", "Marita"],
        "rol": "housekeeping",
        "departamento": "Limpieza",
        "estado": "disponible",
        "ticket_activo": None,
        "tickets_completados_hoy": 5,
        "promedio_tiempo_resolucion": 12.5
    },
    {
        "phone": "56912345672",
        "nombre": "Pedro",
        "apellido": "Ramírez",
        "nombre_completo": "Pedro Ramírez",
        "apodos": ["Pedrito"],
        "rol": "mantenimiento",
        "departamento": "Mantención",
        "estado": "en_pausa",
        "ticket_activo": None,
        "tickets_completados_hoy": 3,
        "promedio_tiempo_resolucion": 15.0
    },
    {
        "phone": "56912345673",
        "nombre": "Ana",
        "apellido": "Torres",
        "nombre_completo": "Ana Torres",
        "apodos": ["Anita"],
        "rol": "housekeeping",
        "departamento": "Limpieza",
        "estado": "ocupada",
        "ticket_activo": 1502,
        "tickets_completados_hoy": 7,
        "promedio_tiempo_resolucion": 10.5
    },
    {
        "phone": "56912345674",
        "nombre": "Daniela",
        "apellido": "Silva",
        "nombre_completo": "Daniela Silva",
        "apodos": ["Dani"],
        "rol": "housekeeping",
        "departamento": "Limpieza",
        "estado": "disponible",
        "ticket_activo": None,
        "tickets_completados_hoy": 4,
        "promedio_tiempo_resolucion": 13.0
    },
    {
        "phone": "56912345675",
        "nombre": "Carlos",
        "apellido": "Muñoz",
        "nombre_completo": "Carlos Muñoz",
        "apodos": ["Carlitos"],
        "rol": "mantenimiento",
        "departamento": "Mantención",
        "estado": "disponible",
        "ticket_activo": None,
        "tickets_completados_hoy": 6,
        "promedio_tiempo_resolucion": 11.0
    },
    {
        "phone": "56912345676",
        "nombre": "José",
        "apellido": "Pérez",
        "nombre_completo": "José Pérez",
        "apodos": ["Pepe", "Chepe"],
        "rol": "housekeeping",
        "departamento": "Limpieza",
        "estado": "disponible",
        "ticket_activo": None,
        "tickets_completados_hoy": 8,
        "promedio_tiempo_resolucion": 9.5
    },
    {
        "phone": "56912345677",
        "nombre": "María",
        "apellido": "López",
        "nombre_completo": "María López",
        "apodos": [],
        "rol": "housekeeping",
        "departamento": "Limpieza",
        "estado": "disponible",
        "ticket_activo": None,
        "tickets_completados_hoy": 2,
        "promedio_tiempo_resolucion": 14.0
    },
    {
        "phone": "56912345678",
        "nombre": "Roberto",
        "apellido": "Soto",
        "nombre_completo": "Roberto Soto",
        "apodos": ["Beto"],
        "rol": "mantenimiento",
        "departamento": "Mantención",
        "estado": "disponible",
        "ticket_activo": None,
        "tickets_completados_hoy": 4,
        "promedio_tiempo_resolucion": 18.0
    },
    {
        "phone": "56912345679",
        "nombre": "Carmen",
        "apellido": "Díaz",
        "nombre_completo": "Carmen Díaz",
        "apodos": ["Menchita"],
        "rol": "housekeeping",
        "departamento": "Limpieza",
        "estado": "disponible",
        "ticket_activo": None,
        "tickets_completados_hoy": 6,
        "promedio_tiempo_resolucion": 11.5
    },
]

# Alias para retrocompatibilidad
DEMO_MUCAMAS = DEMO_WORKERS


# Demo: Tickets pendientes (sin asignar)
def get_demo_tickets_pendientes() -> List[Dict[str, Any]]:
    """
    Retorna tickets de demo sin asignar.
    """
    now = datetime.now()
    
    return [
        {
            "id": 1503,
            "habitacion": "210",
            "detalle": "Cambio de sábanas",
            "prioridad": "ALTA",
            "origen": "huesped",
            "estado": "pendiente",
            "asignado_a": None,
            "asignado_a_nombre": None,
            "created_at": (now - timedelta(minutes=15)).isoformat(),
            "tiempo_sin_resolver_mins": 15
        },
        {
            "id": 1504,
            "habitacion": "315",
            "detalle": "Necesita toallas",
            "prioridad": "MEDIA",
            "origen": "huesped",
            "estado": "pendiente",
            "asignado_a": None,
            "asignado_a_nombre": None,
            "created_at": (now - timedelta(minutes=5)).isoformat(),
            "tiempo_sin_resolver_mins": 5
        },
        {
            "id": 1505,
            "habitacion": "102",
            "detalle": "Amenities",
            "prioridad": "BAJA",
            "origen": "supervisor",
            "estado": "pendiente",
            "asignado_a": None,
            "asignado_a_nombre": None,
            "created_at": (now - timedelta(minutes=2)).isoformat(),
            "tiempo_sin_resolver_mins": 2
        },
    ]


# Demo: Tickets en progreso
def get_demo_tickets_en_progreso() -> List[Dict[str, Any]]:
    """
    Retorna tickets de demo en progreso.
    """
    now = datetime.now()
    
    return [
        {
            "id": 1501,
            "habitacion": "305",
            "detalle": "Necesita toallas",
            "prioridad": "MEDIA",
            "origen": "huesped",
            "estado": "en_progreso",
            "asignado_a": "56912345671",
            "asignado_a_nombre": "María",
            "created_at": (now - timedelta(minutes=25)).isoformat(),
            "started_at": (now - timedelta(minutes=20)).isoformat(),
            "tiempo_sin_resolver_mins": 25,
            "total_paused_seconds": 300,  # 5 minutos en pausa
        },
        {
            "id": 1502,
            "habitacion": "221",
            "detalle": "Limpieza general",
            "prioridad": "ALTA",
            "origen": "supervisor",
            "estado": "en_progreso",
            "asignado_a": "56912345673",
            "asignado_a_nombre": "Ana",
            "created_at": (now - timedelta(minutes=8)).isoformat(),
            "started_at": (now - timedelta(minutes=5)).isoformat(),
            "tiempo_sin_resolver_mins": 8,
            "total_paused_seconds": 0,
        },
        {
            "id": 1506,
            "habitacion": "412",
            "detalle": "Cambio de ropa de cama",
            "prioridad": "MEDIA",
            "origen": "huesped",
            "estado": "en_progreso",
            "asignado_a": "56912345672",
            "asignado_a_nombre": "Pedro",
            "created_at": (now - timedelta(minutes=5)).isoformat(),
            "started_at": (now - timedelta(minutes=3)).isoformat(),
            "tiempo_sin_resolver_mins": 5,
            "total_paused_seconds": 0,
        },
    ]


# Demo: Estadísticas del día
def get_demo_estadisticas() -> Dict[str, Any]:
    """
    Retorna estadísticas de demo del día.
    """
    return {
        "completados": 15,
        "en_progreso": 3,
        "pendientes": 3,
        "rechazados": 1,
        "total_mucamas": 3,
        "mucamas_disponibles": 1,
        "mucamas_ocupadas": 2,
        "tiempo_promedio": 14.5
    }


def get_mucama_by_phone(phone: str) -> Dict[str, Any] | None:
    """
    Busca una mucama por teléfono.
    
    Args:
        phone: Número de teléfono
    
    Returns:
        Datos de la mucama o None
    """
    for mucama in DEMO_MUCAMAS:
        if mucama["phone"] == phone:
            return mucama
    return None


def get_mucama_by_nombre(nombre: str) -> Dict[str, Any] | None:
    """
    Busca un worker (mucama u otro trabajador) por nombre, apellido o apodo.
    
    NOTA: Nombre mantenido para retrocompatibilidad. 
    Usa get_worker_by_nombre() para nuevo código.
    
    Args:
        nombre: Nombre, apellido o apodo (case insensitive)
    
    Returns:
        Datos del worker o None
    """
    return get_worker_by_nombre(nombre)


def get_worker_by_nombre(nombre: str, rol: str = None) -> Dict[str, Any] | None:
    """
    Busca un worker por nombre, apellido o apodo, opcionalmente filtrando por rol.
    
    Args:
        nombre: Nombre, apellido o apodo (case insensitive)
        rol: Rol opcional para filtrar (ej: "housekeeping", "mantenimiento")
    
    Returns:
        Datos del worker o None
    """
    nombre_lower = nombre.lower().strip()
    
    workers = DEMO_WORKERS
    if rol:
        workers = [w for w in DEMO_WORKERS if w.get("rol") == rol]
    
    for worker in workers:
        # Buscar en nombre
        if worker["nombre"].lower() == nombre_lower:
            return worker
        
        # Buscar en apellido
        if worker.get("apellido", "").lower() == nombre_lower:
            return worker
        
        # Buscar en nombre completo
        if nombre_lower in worker.get("nombre_completo", "").lower():
            return worker
        
        # Buscar en apodos
        if any(apodo.lower() == nombre_lower for apodo in worker.get("apodos", [])):
            return worker
    
    return None


def get_workers_by_rol(rol: str) -> List[Dict[str, Any]]:
    """
    Obtiene todos los workers de un rol específico.
    
    Args:
        rol: Rol a filtrar (ej: "housekeeping", "mantenimiento")
    
    Returns:
        Lista de workers del rol especificado
    """
    return [w for w in DEMO_WORKERS if w.get("rol") == rol]


def get_ticket_by_id(ticket_id: int) -> Dict[str, Any] | None:
    """
    Busca un ticket por ID.
    
    Args:
        ticket_id: ID del ticket
    
    Returns:
        Datos del ticket o None
    """
    # Buscar en pendientes
    for ticket in get_demo_tickets_pendientes():
        if ticket["id"] == ticket_id:
            return ticket
    
    # Buscar en progreso
    for ticket in get_demo_tickets_en_progreso():
        if ticket["id"] == ticket_id:
            return ticket
    
    return None