"""
Simulador de WhatsApp para Housekeeping por terminal.
Nodo 1 = input()    (tú escribes)
Nodo 2 = lógica     (reutilizamos la del backend)
Nodo 3 = output     (imprimimos en pantalla)
"""

# TODO: AJUSTAR ESTE IMPORT con tu developer
# Debe apuntar al módulo donde está _handle_hk_message y send_whatsapp.
# Ejemplo inventado:
# from hestia.whatsapp_flows import _handle_hk_message
import whatsapp_flows  # <- tu dev cambiará esto al módulo correcto

# 1) Redefinimos send_whatsapp para que IMPRIMA en vez de mandar a Meta
def send_whatsapp_cli(to: str, body: str):
    print(f"\nBOT → {to}: {body}\n")

# 2) Sobrescribimos la función send_whatsapp que usa la lógica interna
whatsapp_flows.send_whatsapp = send_whatsapp_cli

# 3) Usaremos la misma función de lógica que se usa en producción
handle_message = whatsapp_flows._handle_hk_message  # nombre real que ya vimos

def main():
    fake_phone = "56900000000"  # número ficticio para simular a la mucama
    print("Simulador Hestia HK (CLI)")
    print("Escribe como si fueras la mucama. 'salir' para terminar.\n")

    while True:
        text = input("TÚ → ").strip()
        if text.lower() in {"salir", "exit", "q"}:
            print("Fin del simulador.")
            break

        # Aquí entra el mismo flujo real de HK
        handle_message(fake_phone, text)

if __name__ == "__main__":
    main()
