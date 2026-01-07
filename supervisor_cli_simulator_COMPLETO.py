#!/usr/bin/env python3
"""
Simulador CLI completo para el Bot de Supervisión.
Incluye soporte de comandos de audio simulados.
"""

import sys
import os
import json

# CRÍTICO: Agregar la ruta correcta al path
project_root = os.path.dirname(os.path.abspath(__file__))
service_path = os.path.join(project_root, 'hk_whatsapp_service')
sys.path.insert(0, service_path)

# Importar módulos de supervisión
import gateway_app.flows.supervision.outgoing as outgoing
from gateway_app.flows.supervision import handle_supervisor_message  # Usa el __init__.py
from gateway_app.flows.supervision.state import SUPERVISOR_STATE

# Mock de envío de mensajes
messages = []

def mock_send(to, body):
    messages.append({"to": to, "body": body})
    print(f"\n{'='*70}")
    print(f"📱 BOT → Supervisor")
    print(f"{'='*70}")
    print(body)
    print(f"{'='*70}\n")

# Inyectar implementación mock
outgoing.SEND_IMPL = mock_send


def simular_audio(text: str) -> str:
    """
    Simula la transcripción de un audio.
    
    Args:
        text: Texto que "diría" el audio
    
    Returns:
        El mismo texto (simulando transcripción perfecta)
    """
    print(f"\n🎤 Simulando audio...")
    print(f"📝 Transcripción: \"{text}\"")
    return text


def mostrar_ayuda():
    """Muestra la ayuda de comandos especiales."""
    print("\n" + "="*70)
    print("📚 COMANDOS ESPECIALES DEL SIMULADOR")
    print("="*70)
    print("\n🎤 COMANDOS DE AUDIO (simular voz):")
    print("  audio: [tu comando]")
    print("  Ejemplos:")
    print("    audio: asignar ticket 1503 a María")
    print("    audio: habitación 420 limpieza urgente asignar a Pedro")
    print("    audio: ver tickets pendientes")
    print()
    print("⚙️  COMANDOS DEL SIMULADOR:")
    print("  exit / quit / salir  → Salir del simulador")
    print("  reset                → Limpiar estado y empezar de nuevo")
    print("  estado               → Ver estado actual del supervisor")
    print("  tickets              → Ver tickets de demo disponibles")
    print("  mucamas              → Ver mucamas de demo disponibles")
    print("  help / ayuda         → Mostrar esta ayuda")
    print()
    print("📋 COMANDOS DEL BOT:")
    print("  M / menú             → Volver al menú principal")
    print("  1 / pendientes       → Ver tickets pendientes")
    print("  2 / progreso         → Ver tickets en progreso")
    print("  3 / mucamas          → Ver estado de mucamas")
    print("  5 / stats            → Ver estadísticas")
    print("  asignar              → Asignar ticket de mayor prioridad")
    print("  [número]             → Ver detalles de ticket específico")
    print("="*70 + "\n")


def mostrar_tickets_demo():
    """Muestra los tickets de demo disponibles."""
    from gateway_app.flows.supervision.demo_data import (
        get_demo_tickets_pendientes,
        get_demo_tickets_en_progreso
    )
    
    print("\n" + "="*70)
    print("📋 TICKETS DE DEMO DISPONIBLES")
    print("="*70)
    
    print("\n📌 PENDIENTES:")
    for ticket in get_demo_tickets_pendientes():
        print(f"  #{ticket['id']} · Hab. {ticket['habitacion']} · "
              f"{ticket['detalle']} · {ticket['prioridad']}")
    
    print("\n🔄 EN PROGRESO:")
    for ticket in get_demo_tickets_en_progreso():
        print(f"  #{ticket['id']} · Hab. {ticket['habitacion']} · "
              f"{ticket['detalle']} · Asignado a {ticket['asignado_a_nombre']}")
    
    print("="*70 + "\n")


def mostrar_mucamas_demo():
    """Muestra las mucamas de demo disponibles."""
    from gateway_app.flows.supervision.demo_data import DEMO_MUCAMAS
    
    print("\n" + "="*70)
    print("👥 MUCAMAS DE DEMO DISPONIBLES")
    print("="*70)
    
    for mucama in DEMO_MUCAMAS:
        estado_emoji = {
            "disponible": "✅",
            "ocupada": "🔴",
            "en_pausa": "⏸️"
        }.get(mucama['estado'], "❓")
        
        print(f"\n  {estado_emoji} {mucama['nombre']}")
        print(f"     Estado: {mucama['estado']}")
        print(f"     Tickets hoy: {mucama['tickets_completados_hoy']}")
        print(f"     Promedio: {mucama['promedio_tiempo_resolucion']:.1f} min")
        if mucama.get('ticket_activo'):
            print(f"     Ticket activo: #{mucama['ticket_activo']}")
    
    print("="*70 + "\n")


def mostrar_ejemplos_audio():
    """Muestra ejemplos de comandos de audio."""
    print("\n" + "="*70)
    print("🎤 EJEMPLOS DE COMANDOS DE AUDIO")
    print("="*70)
    print("\n1️⃣  ASIGNAR TICKET EXISTENTE:")
    print("     audio: asignar ticket 1503 a María")
    print("     audio: derivar el 1504 a Pedro")
    print()
    print("2️⃣  CREAR Y ASIGNAR EN UN SOLO COMANDO:")
    print("     audio: habitación 420 limpieza urgente asignar a Pedro")
    print("     audio: cuarto 305 toallas mandar a María")
    print()
    print("3️⃣  SOLO CREAR TICKET:")
    print("     audio: habitación 305 necesita toallas")
    print("     audio: cuarto 210 cambio de sábanas urgente")
    print()
    print("4️⃣  ASIGNAR SIN ESPECIFICAR TICKET (usa el de mayor prioridad):")
    print("     audio: asignar a María")
    print("     audio: mandar a Pedro")
    print()
    print("5️⃣  VER ESTADO:")
    print("     audio: ver tickets pendientes")
    print("     audio: mostrar progreso")
    print("="*70 + "\n")


def main():
    """Loop principal del simulador."""
    print("="*70)
    print("👤 SIMULADOR CLI - Bot de Supervisión")
    print("="*70)
    print("\n💡 Escribe 'help' o 'ayuda' para ver todos los comandos")
    print("🎤 Escribe 'audio: [comando]' para simular comandos de voz")
    print("="*70)
    
    # Número de prueba (supervisor)
    test_phone = "56987654321"
    
    # Mostrar saludo inicial
    handle_supervisor_message(test_phone, "hola")
    
    while True:
        try:
            # Leer input del usuario
            user_input = input(f"\n👤 SUPERVISOR → ")
            
            if not user_input.strip():
                continue
            
            raw_input = user_input.strip()
            
            # Comandos especiales del simulador
            if raw_input.lower() in ['exit', 'quit', 'salir']:
                print("\n👋 ¡Hasta luego!\n")
                break
            
            if raw_input.lower() == 'reset':
                SUPERVISOR_STATE.clear()
                messages.clear()
                print("\n🔄 Estado reiniciado\n")
                handle_supervisor_message(test_phone, "hola")
                continue
            
            if raw_input.lower() == 'estado':
                state = SUPERVISOR_STATE.get(test_phone, {})
                print("\n📊 Estado actual del supervisor:")
                print(json.dumps(state, indent=2, default=str))
                continue
            
            if raw_input.lower() == 'tickets':
                mostrar_tickets_demo()
                continue
            
            if raw_input.lower() == 'mucamas':
                mostrar_mucamas_demo()
                continue
            
            if raw_input.lower() in ['help', 'ayuda', '?']:
                mostrar_ayuda()
                continue
            
            if raw_input.lower() == 'ejemplos':
                mostrar_ejemplos_audio()
                continue
            
            # Comando de audio simulado
            if raw_input.lower().startswith('audio:'):
                comando_audio = raw_input[6:].strip()
                if comando_audio:
                    texto_transcrito = simular_audio(comando_audio)
                    # Simular mensaje de transcripción
                    print(f"\n🎤 Escuché: \"{texto_transcrito}\"")
                    # Procesar como mensaje normal
                    handle_supervisor_message(test_phone, texto_transcrito)
                else:
                    print("❌ Debes escribir un comando después de 'audio:'")
                continue
            
            # Procesar mensaje normal (texto)
            handle_supervisor_message(test_phone, raw_input)
            
        except KeyboardInterrupt:
            print("\n\n👋 ¡Hasta luego!\n")
            break
        except Exception as e:
            print(f"\n❌ Error: {e}\n")
            import traceback
            traceback.print_exc()


if __name__ == "__main__":
    main()