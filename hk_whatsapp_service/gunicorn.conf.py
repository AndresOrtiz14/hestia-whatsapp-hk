# gunicorn.conf.py
# Solo el primer worker (age == 0) inicia el daily_scheduler.
# Evita el doble envío de recordatorios cuando hay múltiples workers.


def post_fork(server, worker):
    if worker.age == 0:
        from gateway_app.services.daily_scheduler import start_daily_scheduler
        start_daily_scheduler()
