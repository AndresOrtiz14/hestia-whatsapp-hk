"""
Datos de demo para el bot de Supervisión.
Tickets y mucamas de prueba.
"""

from datetime import datetime, timedelta
from typing import List, Dict, Any


# Demo: Mucamas registradas
DEMO_MUCAMAS = [
    {
        "phone": "56912345671",
        "nombre": "María",
        "estado": "disponible",
        "ticket_activo": None,
        "tickets_completados_hoy": 5,
        "promedio_tiempo_resolucion": 12.5
    },
    {
        "phone": "56912345672",
        "nombre": "Pedro",
        "estado": "en_pausa",
        "ticket_activo": None,
        "tickets_completados_hoy": 3,
        "promedio_tiempo_resolucion": 15.0
    },
    {
        "phone": "56912345673",
        "nombre": "Ana",
        "estado": "ocupada",
        "ticket_activo": 1502,
        "tickets_completados_hoy": 7,
        "promedio_tiempo_resolucion": 10.5
    },
]


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
    Busca una mucama por nombre.
    
    Args:
        nombre: Nombre de la mucama (case insensitive)
    
    Returns:
        Datos de la mucama o None
    """
    nombre_lower = nombre.lower().strip()
    for mucama in DEMO_MUCAMAS:
        if mucama["nombre"].lower() == nombre_lower:
            return mucama
    return None


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