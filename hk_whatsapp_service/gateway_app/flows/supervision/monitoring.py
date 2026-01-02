"""
Módulo de monitoreo para el bot de Supervisión.
Ver tickets pendientes, en progreso, mucamas y estadísticas.
"""

from typing import List, Dict, Any
from .demo_data import (
    get_demo_tickets_pendientes,
    get_demo_tickets_en_progreso,
    get_demo_estadisticas,
    DEMO_MUCAMAS
)
from .ui import (
    formato_ticket_simple,
    formato_ticket_detallado,
    formato_mucama_estado,
    formato_estadisticas_dia,
    recordatorio_menu
)
from .outgoing import send_whatsapp


def mostrar_tickets_pendientes(phone: str) -> None:
    """
    Muestra la lista de tickets pendientes (sin asignar).
    
    Args:
        phone: Número de teléfono del supervisor
    """
    tickets = get_demo_tickets_pendientes()
    
    if not tickets:
        send_whatsapp(
            phone,
            "📋 No hay tickets pendientes\n\n"
            "✅ Todos los tickets están asignados." +
            recordatorio_menu()
        )
        return
    
    # Ordenar por prioridad y tiempo
    prioridad_order = {"ALTA": 0, "MEDIA": 1, "BAJA": 2}
    tickets_sorted = sorted(
        tickets,
        key=lambda t: (
            prioridad_order.get(t.get("prioridad", "MEDIA"), 1),
            -t.get("tiempo_sin_resolver_mins", 0)
        )
    )
    
    # Construir mensaje
    lineas = [f"📋 Tickets Pendientes ({len(tickets)})\n"]
    
    for ticket in tickets_sorted:
        lineas.append(formato_ticket_simple(ticket))
    
    lineas.append("\n💡 Para asignar un ticket:")
    lineas.append("• Escribe el # del ticket (ej: 1503)")
    lineas.append("• O escribe 'asignar' para el de mayor prioridad")
    
    mensaje = "\n".join(lineas) + recordatorio_menu()
    send_whatsapp(phone, mensaje)


def mostrar_tickets_en_progreso(phone: str) -> None:
    """
    Muestra la lista de tickets en progreso.
    
    Args:
        phone: Número de teléfono del supervisor
    """
    tickets = get_demo_tickets_en_progreso()
    
    if not tickets:
        send_whatsapp(
            phone,
            "🔄 No hay tickets en progreso\n\n"
            "📋 Todos los tickets están pendientes o completados." +
            recordatorio_menu()
        )
        return
    
    # Separar: retrasados (>10 min) y normales
    retrasados = [t for t in tickets if t.get("tiempo_sin_resolver_mins", 0) > 10]
    normales = [t for t in tickets if t.get("tiempo_sin_resolver_mins", 0) <= 10]
    
    lineas = [f"🔄 Tickets en Progreso ({len(tickets)})\n"]
    
    # Mostrar retrasados con detalle
    if retrasados:
        lineas.append("⚠️ RETRASADOS (>10 min):\n")
        for ticket in retrasados:
            lineas.append(formato_ticket_detallado(ticket))
            lineas.append("")  # Línea vacía
    
    # Mostrar normales simple
    if normales:
        if retrasados:
            lineas.append("✅ EN TIEMPO:\n")
        for ticket in normales:
            lineas.append(formato_ticket_simple(ticket))
    
    mensaje = "\n".join(lineas) + recordatorio_menu()
    send_whatsapp(phone, mensaje)


def mostrar_estado_mucamas(phone: str) -> None:
    """
    Muestra el estado actual de todas las mucamas.
    
    Args:
        phone: Número de teléfono del supervisor
    """
    mucamas = DEMO_MUCAMAS
    
    if not mucamas:
        send_whatsapp(
            phone,
            "👥 No hay mucamas registradas" +
            recordatorio_menu()
        )
        return
    
    # Separar por estado
    disponibles = [m for m in mucamas if m.get("estado") == "disponible"]
    ocupadas = [m for m in mucamas if m.get("estado") == "ocupada"]
    en_pausa = [m for m in mucamas if m.get("estado") == "en_pausa"]
    
    lineas = [f"👥 Estado de Mucamas ({len(mucamas)})\n"]
    
    # Disponibles
    if disponibles:
        lineas.append("✅ DISPONIBLES:\n")
        for mucama in disponibles:
            lineas.append(formato_mucama_estado(mucama))
        lineas.append("")
    
    # En pausa
    if en_pausa:
        lineas.append("⏸️ EN PAUSA:\n")
        for mucama in en_pausa:
            lineas.append(formato_mucama_estado(mucama))
        lineas.append("")
    
    # Ocupadas
    if ocupadas:
        lineas.append("🔴 OCUPADAS:\n")
        for mucama in ocupadas:
            lineas.append(formato_mucama_estado(mucama))
    
    mensaje = "\n".join(lineas) + recordatorio_menu()
    send_whatsapp(phone, mensaje)


def mostrar_estadisticas(phone: str) -> None:
    """
    Muestra las estadísticas del día.
    
    Args:
        phone: Número de teléfono del supervisor
    """
    stats = get_demo_estadisticas()
    mensaje = formato_estadisticas_dia(stats) + recordatorio_menu()
    send_whatsapp(phone, mensaje)