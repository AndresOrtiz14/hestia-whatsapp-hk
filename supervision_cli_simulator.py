#!/usr/bin/env python3
"""
Simulador CLI para el bot de Supervisión.
Permite probar el bot sin necesidad de WhatsApp.
"""

import sys
import os

# CRÍTICO: Agregar la ruta correcta al path
project_root = os.path.dirname(os.path.abspath(__file__))
service_path = os.path.join(project_root, 'hk_whatsapp_service')
sys.path.insert(0, service_path)

# Importar el orquestador de supervisión
import gateway_app.flows.supervision.outgoing as outgoing
from gateway_app.flows.supervision.orchestrator import handle_supervisor_message

# Mock de envío de mensajes para testing
messages = []

def mock_send(to, body):
    messages.append({"to": to, "body": body})
    print(f"\n{'='*60}")
    print(f"BOT → {to}")
    print(f"{'='*60}")
    print(body)
    print(f"{'='*60}\n")

# Inyectar implementación mock
outgoing.SEND_IMPL = mock_send


def main():
    """
    Loop principal del simulador.
    """
    print("=" * 60)
    print("👤 SIMULADOR CLI - Bot de Supervisión")
    print("=" * 60)
    print("Comandos especiales:")
    print("  - 'exit' o 'quit' → Salir")
    print("  - 'reset' → Limpiar historial")
    print("  - 'estado' → Ver estado actual")
    print("=" * 60)
    
    # Número de prueba (supervisor)
    test_phone = "56987654321"
    
    while True:
        try:
            # Leer input del usuario
            user_input = input(f"\nSUPERVISOR → ")
            
            if not user_input.strip():
                continue
            
            # Comandos especiales
            if user_input.lower() in ['exit', 'quit', 'salir']:
                print("\n👋 ¡Hasta luego!\n")
                break
            
            if user_input.lower() == 'reset':
                from gateway_app.flows.supervision.state import SUPERVISOR_STATE
                SUPERVISOR_STATE.clear()
                messages.clear()
                print("\n🔄 Estado reiniciado\n")
                continue
            
            if user_input.lower() == 'estado':
                from gateway_app.flows.supervision.state import SUPERVISOR_STATE
                import json
                state = SUPERVISOR_STATE.get(test_phone, {})
                print("\n📊 Estado actual:")
                print(json.dumps(state, indent=2, default=str))
                continue
            
            # Procesar mensaje normal
            handle_supervisor_message(test_phone, user_input)
            
        except KeyboardInterrupt:
            print("\n\n👋 ¡Hasta luego!\n")
            break
        except Exception as e:
            print(f"\n❌ Error: {e}\n")
            import traceback
            traceback.print_exc()


if __name__ == "__main__":
    main()