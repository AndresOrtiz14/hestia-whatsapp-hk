#!/usr/bin/env python3
"""
Tests automatizados para funcionalidad PUSH de Housekeeping.
"""

import sys
import os
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../'))

from hk_whatsapp_service.gateway_app.flows.housekeeping import (
    notify_new_ticket,
    handle_hk_message,
    check_and_assign_pending_tickets
)
from hk_whatsapp_service.gateway_app.flows.housekeeping import outgoing as outgoing_mod
from hk_whatsapp_service.gateway_app.flows.housekeeping.state import USER_STATE, get_user_state


# Captura de mensajes
messages = []

def mock_send(to, body):
    messages.append({"to": to, "body": body})

outgoing_mod.SEND_IMPL = mock_send


def reset():
    """Limpia estado entre tests."""
    global messages
    messages = []
    USER_STATE.clear()


def assert_contains(text, substring, test_name):
    """Verifica que un texto contenga un substring."""
    if substring.lower() in text.lower():
        print(f"✅ {test_name}")
        return True
    else:
        print(f"❌ {test_name}")
        print(f"   Esperaba: '{substring}'")
        print(f"   En: '{text[:100]}...'")
        return False


def test_push_basic():
    """Test: Notificación PUSH básica."""
    reset()
    phone = "56900000001"
    
    ticket = {
        "id": 3001,
        "room": "502",
        "detalle": "Necesito toallas",
        "prioridad": "ALTA"
    }
    
    result = notify_new_ticket(phone, ticket)
    
    assert result["success"], "Debe ser exitoso"
    assert result["action"] == "assigned", "Debe estar asignado"
    assert result["ticket_id"] == 3001, "ID correcto"
    
    # Verificar estado
    state = get_user_state(phone)
    assert state["turno_activo"], "Turno debe estar activo"
    assert state["ticket_state"] == "S1", "Debe estar en S1"
    assert state["ticket_activo"]["id"] == 3001, "Ticket activo correcto"
    assert state["ticket_activo"]["auto_assigned"], "Debe estar marcado como auto_assigned"
    
    # Verificar mensaje
    msg = messages[-1]["body"]
    assert_contains(msg, "NUEVO TICKET ASIGNADO", "Mensaje de notificación")
    assert_contains(msg, "3001", "ID en mensaje")
    assert_contains(msg, "502", "Habitación en mensaje")
    
    print("✅ Test básico PUSH")


def test_push_con_huesped():
    """Test: Notificación con nombre de huésped."""
    reset()
    phone = "56900000002"
    
    ticket = {
        "id": 3002,
        "room": "314",
        "detalle": "Cambiar sábanas",
        "prioridad": "MEDIA",
        "guest_name": "Carlos Ruiz"
    }
    
    result = notify_new_ticket(phone, ticket)
    
    assert result["success"], "Debe ser exitoso"
    
    msg = messages[-1]["body"]
    assert_contains(msg, "Carlos Ruiz", "Nombre de huésped")
    
    print("✅ Test con huésped")


def test_push_mucama_ocupada():
    """Test: PUSH cuando mucama ya tiene ticket activo."""
    reset()
    phone = "56900000003"
    
    # Primer ticket
    ticket1 = {
        "id": 3001,
        "room": "502",
        "detalle": "Primer ticket",
        "prioridad": "ALTA"
    }
    
    result1 = notify_new_ticket(phone, ticket1)
    assert result1["action"] == "assigned", "Primer ticket asignado"
    
    messages.clear()  # Limpiar mensajes
    
    # Segundo ticket (mucama ocupada)
    ticket2 = {
        "id": 3002,
        "room": "314",
        "detalle": "Segundo ticket",
        "prioridad": "MEDIA"
    }
    
    result2 = notify_new_ticket(phone, ticket2)
    
    assert result2["success"], "Debe ser exitoso"
    assert result2["action"] == "queued", "Debe estar encolado"
    assert result2["queue_position"] == 1, "Posición en cola"
    
    # Verificar estado
    state = get_user_state(phone)
    assert len(state["pending_tickets"]) == 1, "Un ticket en cola"
    assert state["pending_tickets"][0]["id"] == 3002, "Ticket correcto en cola"
    
    # Verificar mensaje
    msg = messages[-1]["body"]
    assert_contains(msg, "EN ESPERA", "Mensaje de encolamiento")
    assert_contains(msg, "3002", "ID del ticket encolado")
    
    print("✅ Test mucama ocupada (encolamiento)")


def test_push_cola_automatica():
    """Test: Asignación automática de cola al finalizar ticket."""
    reset()
    phone = "56900000004"
    
    # Asignar primer ticket
    ticket1 = {"id": 3001, "room": "502", "detalle": "Primero", "prioridad": "ALTA"}
    notify_new_ticket(phone, ticket1)
    
    # Asignar segundo ticket (se encola)
    ticket2 = {"id": 3002, "room": "314", "detalle": "Segundo", "prioridad": "MEDIA"}
    notify_new_ticket(phone, ticket2)
    
    messages.clear()
    
    # Finalizar primer ticket
    handle_hk_message(phone, "fin")
    
    # Verificar que se asignó el segundo automáticamente
    state = get_user_state(phone)
    assert state["ticket_activo"]["id"] == 3002, "Segundo ticket asignado automáticamente"
    assert len(state.get("pending_tickets", [])) == 0, "Cola vacía"
    
    # Verificar mensajes (1: finalización, 2: nuevo ticket)
    assert len(messages) >= 2, "Debe haber al menos 2 mensajes"
    
    msg_fin = messages[0]["body"]
    msg_nuevo = messages[1]["body"]
    
    assert_contains(msg_fin, "FINALIZADO", "Mensaje de finalización")
    assert_contains(msg_nuevo, "NUEVO TICKET ASIGNADO", "Mensaje de nuevo ticket")
    assert_contains(msg_nuevo, "3002", "ID del segundo ticket")
    
    print("✅ Test cola automática")


def test_push_multiple_tickets_en_cola():
    """Test: Múltiples tickets encolados."""
    reset()
    phone = "56900000005"
    
    # Asignar 4 tickets (1 activo, 3 en cola)
    tickets = [
        {"id": 3001, "room": "501", "detalle": "Ticket 1", "prioridad": "ALTA"},
        {"id": 3002, "room": "502", "detalle": "Ticket 2", "prioridad": "MEDIA"},
        {"id": 3003, "room": "503", "detalle": "Ticket 3", "prioridad": "BAJA"},
        {"id": 3004, "room": "504", "detalle": "Ticket 4", "prioridad": "ALTA"},
    ]
    
    for ticket in tickets:
        notify_new_ticket(phone, ticket)
    
    # Verificar estado
    state = get_user_state(phone)
    assert state["ticket_activo"]["id"] == 3001, "Primer ticket activo"
    assert len(state["pending_tickets"]) == 3, "3 tickets en cola"
    
    # Finalizar tickets uno por uno
    for expected_id in [3002, 3003, 3004]:
        handle_hk_message(phone, "fin")
        state = get_user_state(phone)
        
        if expected_id != 3004:  # El último no tiene siguiente
            assert state["ticket_activo"]["id"] == expected_id, f"Ticket {expected_id} asignado"
    
    # Al final, cola debe estar vacía
    state = get_user_state(phone)
    assert len(state.get("pending_tickets", [])) == 0, "Cola vacía al final"
    
    print("✅ Test múltiples tickets en cola")


def test_push_sin_auto_start_shift():
    """Test: PUSH sin auto-inicio de turno."""
    reset()
    phone = "56900000006"
    
    ticket = {
        "id": 3001,
        "room": "502",
        "detalle": "Test sin auto-start",
        "prioridad": "ALTA"
    }
    
    result = notify_new_ticket(phone, ticket, auto_start_shift=False)
    
    assert result["success"], "Debe ser exitoso"
    assert not result.get("auto_started_shift"), "No debe auto-iniciar turno"
    
    # Verificar estado
    state = get_user_state(phone)
    assert not state["turno_activo"], "Turno NO debe estar activo"
    assert state["ticket_activo"]["id"] == 3001, "Ticket asignado de todos modos"
    
    print("✅ Test sin auto-inicio de turno")


def test_push_datos_incompletos():
    """Test: Validación de datos incompletos."""
    reset()
    phone = "56900000007"
    
    # Ticket sin habitación
    ticket = {
        "id": 3001,
        "detalle": "Sin habitación"
    }
    
    result = notify_new_ticket(phone, ticket)
    
    assert not result["success"], "Debe fallar con datos incompletos"
    assert result["action"] == "rejected", "Debe estar rechazado"
    assert "incompletos" in result["message"].lower(), "Mensaje de error"
    
    print("✅ Test datos incompletos")


def test_push_integracion_con_comandos():
    """Test: PUSH + comandos normales (pausar, reanudar)."""
    reset()
    phone = "56900000008"
    
    # Enviar ticket PUSH
    ticket = {
        "id": 3001,
        "room": "502",
        "detalle": "Test integración",
        "prioridad": "ALTA"
    }
    
    notify_new_ticket(phone, ticket)
    messages.clear()
    
    # Pausar
    handle_hk_message(phone, "pausar")
    msg = messages[-1]["body"]
    assert_contains(msg, "PAUSADO", "Pausado correctamente")
    
    # Reanudar
    handle_hk_message(phone, "reanudar")
    msg = messages[-1]["body"]
    assert_contains(msg, "REANUDADO", "Reanudado correctamente")
    
    # Finalizar
    handle_hk_message(phone, "fin")
    msg = messages[-1]["body"]
    assert_contains(msg, "FINALIZADO", "Finalizado correctamente")
    
    print("✅ Test integración con comandos")


def run_all_tests():
    """Ejecuta todos los tests."""
    print("\n" + "="*60)
    print("🧪 TESTS DE FUNCIONALIDAD PUSH")
    print("="*60 + "\n")
    
    tests = [
        ("PUSH básico", test_push_basic),
        ("PUSH con huésped", test_push_con_huesped),
        ("Mucama ocupada (encolamiento)", test_push_mucama_ocupada),
        ("Cola automática", test_push_cola_automatica),
        ("Múltiples tickets en cola", test_push_multiple_tickets_en_cola),
        ("Sin auto-inicio turno", test_push_sin_auto_start_shift),
        ("Datos incompletos", test_push_datos_incompletos),
        ("Integración con comandos", test_push_integracion_con_comandos),
    ]
    
    passed = 0
    failed = 0
    
    for name, test_func in tests:
        print(f"\n📋 Test: {name}")
        print("-" * 40)
        try:
            test_func()
            passed += 1
        except AssertionError as e:
            print(f"❌ FALLO: {e}")
            failed += 1
        except Exception as e:
            print(f"❌ ERROR: {e}")
            failed += 1
            import traceback
            traceback.print_exc()
    
    print("\n" + "="*60)
    print(f"RESULTADOS: {passed} ✅ | {failed} ❌")
    print("="*60 + "\n")
    
    return failed == 0


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)