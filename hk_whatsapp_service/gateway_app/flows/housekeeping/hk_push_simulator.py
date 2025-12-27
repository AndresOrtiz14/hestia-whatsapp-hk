#!/usr/bin/env python3
"""
Simulador de Notificaciones PUSH para Housekeeping.
Simula el sistema backend enviando tickets automáticamente a las mucamas.
"""

import sys
import os
from datetime import datetime, timedelta

# Agregar el directorio al path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../'))

from hk_whatsapp_service.gateway_app.flows.housekeeping import (
    notify_new_ticket,
    handle_hk_message
)
from hk_whatsapp_service.gateway_app.flows.housekeeping import outgoing as outgoing_mod
from hk_whatsapp_service.gateway_app.flows.housekeeping.state import USER_STATE


def send_whatsapp_cli(to: str, body: str) -> None:
    """Implementación CLI del envío de mensajes."""
    print(f"\n{'='*60}")
    print(f"📱 WHATSAPP → {to}")
    print(f"{'='*60}")
    print(body)
    print(f"{'='*60}\n")


# Configurar la implementación de envío
outgoing_mod.SEND_IMPL = send_whatsapp_cli


# Tickets de ejemplo para el sistema
TICKETS_SISTEMA = [
    {
        "id": 3001,
        "room": "502",
        "detalle": "Necesito toallas limpias y shampoo",
        "prioridad": "ALTA",
        "guest_name": "María González",
        "created_at": datetime.now()
    },
    {
        "id": 3002,
        "room": "314",
        "detalle": "Por favor cambiar sábanas",
        "prioridad": "MEDIA",
        "guest_name": "Carlos Ruiz",
        "created_at": datetime.now()
    },
    {
        "id": 3003,
        "room": "205",
        "detalle": "Falta papel higiénico",
        "prioridad": "ALTA",
        "created_at": datetime.now()
    },
    {
        "id": 3004,
        "room": "418",
        "detalle": "Limpieza general de la habitación",
        "prioridad": "BAJA",
        "guest_name": "Ana Martínez",
        "created_at": datetime.now()
    }
]


def mostrar_menu_sistema():
    """Muestra el menú del simulador de sistema."""
    print("\n" + "="*60)
    print("🏨 SIMULADOR DE SISTEMA BACKEND - HESTIA")
    print("="*60)
    print("\nSimula el sistema que asigna tickets a mucamas")
    print("\nComandos disponibles:")
    print("  [1-4] → Enviar ticket automático (PUSH)")
    print("  'lista' → Ver tickets disponibles")
    print("  'estado' → Ver estado de mucamas")
    print("  'limpiar' → Limpiar estado de mucamas")
    print("  'conversar' → Modo conversación (responder como mucama)")
    print("  'salir' → Terminar simulador")
    print("="*60 + "\n")


def mostrar_tickets_disponibles():
    """Muestra los tickets disponibles para enviar."""
    print("\n📋 TICKETS DISPONIBLES PARA ASIGNAR:\n")
    for i, ticket in enumerate(TICKETS_SISTEMA, 1):
        prioridad_emoji = {"ALTA": "🔴", "MEDIA": "🟡", "BAJA": "🟢"}.get(
            ticket["prioridad"], "🟡"
        )
        guest = f" | {ticket.get('guest_name', 'Sin nombre')}" if ticket.get('guest_name') else ""
        print(f"  [{i}] {prioridad_emoji} #{ticket['id']} · Hab. {ticket['room']}{guest}")
        print(f"      {ticket['detalle']}")
    print()


def mostrar_estado_mucamas():
    """Muestra el estado actual de las mucamas."""
    print("\n👥 ESTADO DE MUCAMAS:\n")
    
    if not USER_STATE:
        print("  (No hay mucamas en el sistema)")
        return
    
    for phone, state in USER_STATE.items():
        turno = "🟢 ACTIVO" if state.get("turno_activo") else "⚪️ INACTIVO"
        ticket = state.get("ticket_activo")
        pending = len(state.get("pending_tickets", []))
        
        print(f"  📱 {phone}")
        print(f"     Turno: {turno}")
        
        if ticket:
            ticket_state = "⏸️ PAUSADO" if ticket.get("paused") else "▶️ EN CURSO"
            auto = " (AUTO)" if ticket.get("auto_assigned") else ""
            print(f"     Ticket actual: #{ticket.get('id')} · Hab. {ticket.get('room')} · {ticket_state}{auto}")
        else:
            print(f"     Ticket actual: Sin ticket")
        
        if pending > 0:
            print(f"     Tickets en cola: {pending}")
        
        print()


def modo_conversacion(phone: str):
    """Modo conversación: permite responder como mucama."""
    print(f"\n💬 MODO CONVERSACIÓN - Mucama {phone}")
    print("Escribe mensajes como si fueras la mucama.")
    print("Comandos: 'pausar', 'fin', 'supervisor', 'M', 'salir'\n")
    
    while True:
        try:
            text = input(f"MUCAMA {phone} → ").strip()
            
            if text.lower() == "salir":
                print("Saliendo del modo conversación...\n")
                break
            
            if not text:
                continue
            
            # Procesar mensaje como mucama
            handle_hk_message(phone, text)
            
        except KeyboardInterrupt:
            print("\n\nSaliendo del modo conversación...\n")
            break
        except Exception as e:
            print(f"\n❌ ERROR: {e}\n")


def main():
    """Loop principal del simulador de sistema."""
    phone_mucama = "56912345678"  # Número de mucama de prueba
    
    print("\n" + "="*60)
    print("🚀 SIMULADOR DE NOTIFICACIONES PUSH - HESTIA")
    print("="*60)
    print(f"\nMucama de prueba: {phone_mucama}")
    print("Este simulador actúa como el sistema backend que envía")
    print("tickets automáticamente a las mucamas.\n")
    
    mostrar_menu_sistema()
    
    while True:
        try:
            comando = input("SISTEMA → ").strip().lower()
            
            # Salir
            if comando in {"salir", "exit", "q"}:
                print("\n✅ Simulador terminado. ¡Hasta pronto!\n")
                break
            
            # Mostrar lista de tickets
            if comando == "lista":
                mostrar_tickets_disponibles()
                continue
            
            # Mostrar estado de mucamas
            if comando == "estado":
                mostrar_estado_mucamas()
                continue
            
            # Limpiar estado
            if comando == "limpiar":
                USER_STATE.clear()
                print("\n✅ Estado de mucamas limpiado\n")
                continue
            
            # Modo conversación
            if comando == "conversar":
                modo_conversacion(phone_mucama)
                mostrar_menu_sistema()
                continue
            
            # Ayuda
            if comando in {"ayuda", "help", "?"}:
                mostrar_menu_sistema()
                continue
            
            # Enviar ticket (1-4)
            if comando in {"1", "2", "3", "4"}:
                idx = int(comando) - 1
                
                if 0 <= idx < len(TICKETS_SISTEMA):
                    ticket = TICKETS_SISTEMA[idx]
                    
                    print(f"\n📤 ENVIANDO TICKET #{ticket['id']} A MUCAMA {phone_mucama}...\n")
                    
                    # Notificar ticket (PUSH)
                    result = notify_new_ticket(phone_mucama, ticket)
                    
                    # Mostrar resultado
                    if result["success"]:
                        action_msg = {
                            "assigned": "✅ Ticket ASIGNADO directamente",
                            "queued": "⏳ Ticket ENCOLADO (mucama ocupada)",
                            "rejected": "❌ Ticket RECHAZADO"
                        }.get(result["action"], "⚠️ Acción desconocida")
                        
                        print(f"\n{action_msg}")
                        print(f"ID: #{result['ticket_id']}")
                        
                        if result.get("queue_position"):
                            print(f"Posición en cola: {result['queue_position']}")
                        
                        if result.get("auto_started_shift"):
                            print("Turno iniciado automáticamente")
                    else:
                        print(f"\n❌ ERROR: {result.get('message')}")
                    
                    print()
                else:
                    print(f"\n❌ Opción inválida. Usa 1-{len(TICKETS_SISTEMA)}\n")
                
                continue
            
            # Comando desconocido
            if comando:
                print(f"\n⚠️ Comando '{comando}' no reconocido. Usa 'ayuda' para ver opciones.\n")
        
        except KeyboardInterrupt:
            print("\n\n✅ Simulador interrumpido. ¡Hasta pronto!\n")
            break
        except Exception as e:
            print(f"\n❌ ERROR: {e}\n")
            import traceback
            traceback.print_exc()


if __name__ == "__main__":
    main()