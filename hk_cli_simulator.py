"""
Simulador de WhatsApp para Housekeeping por terminal.
Nodo 1 = input()    (tú escribes)
Nodo 2 = lógica     (reutilizamos la del backend)
Nodo 3 = output     (imprimimos en pantalla)
"""

import hk_whatsapp_service.gateway_app.flows.housekeeping_flows as flows
import hk_whatsapp_service.gateway_app.flows.housekeeping.outgoing as outgoing_mod


def send_whatsapp_cli(to: str, body: str) -> None:
    print(f"\nBOT → {to}: {body}\n")


# IMPORTANTE:
# Con el nuevo outgoing.py NO parcheamos outgoing_mod.send_whatsapp (wrapper),
# sino outgoing_mod.SEND_IMPL (la implementación real).
outgoing_mod.SEND_IMPL = send_whatsapp_cli

handle_message = flows.handle_hk_message


def main() -> None:
    fake_phone = "56900000000"
    print("Simulador Hestia HK (CLI)")
    print("Escribe como si fueras la mucama. 'salir' para terminar.\n")

    while True:
        text = input("TÚ → ").strip()
        if text.lower() in {"salir", "exit", "q"}:
            print("Fin del simulador.")
            break
        handle_message(fake_phone, text)


if __name__ == "__main__":
    main()
