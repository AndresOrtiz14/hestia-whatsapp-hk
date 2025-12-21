def send_whatsapp(to: str, body: str):
    """
    En producción esto enviaría un WhatsApp.
    En el simulador se sobreescribe/monkeypatch.
    """
    print(f"[FAKE SEND] → {to}: {body}")
