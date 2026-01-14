@echo off
setlocal enabledelayedexpansion

set "OUT=project_extract.txt"

> "%OUT%" (
  echo === .env.example ===
  type ".env.example"
  echo.

  echo === app.py ===
  type "app.py"
  echo.

  echo === render.yaml ===
  type "render.yaml"
  echo.

  echo === requirements.txt ===
  type "requirements.txt"
  echo.

  echo === gateway_app\config.py ===
  type "gateway_app\config.py"
  echo.

  echo === gateway_app\__init__.py ===
  type "gateway_app\__init__.py"
  echo.

  echo === gateway_app\routes\webhook.py ===
  type "gateway_app\routes\webhook.py"
  echo.

  echo === gateway_app\routes\__init__.py ===
  type "gateway_app\routes\__init__.py"
  echo.

  echo === gateway_app\services\audio.py ===
  type "gateway_app\services\audio.py"
  echo.

  echo === gateway_app\services\db.py ===
  type "gateway_app\services\db.py"
  echo.

  echo === gateway_app\services\migrations.py ===
  type "gateway_app\services\migrations.py"
  echo.

  echo === gateway_app\services\runtime_state.py ===
  type "gateway_app\services\runtime_state.py"
  echo.

  echo === gateway_app\services\tickets_db.py ===
  type "gateway_app\services\tickets_db.py"
  echo.

  echo === gateway_app\services\whatsapp_client.py ===
  type "gateway_app\services\whatsapp_client.py"
  echo.

  echo === gateway_app\services\workers_db.py ===
  type "gateway_app\services\workers_db.py"
  echo.

  echo === gateway_app\services\__init__.py ===
  type "gateway_app\services\__init__.py"
  echo.

  echo === gateway_app\flows\housekeeping_flows.py ===
  type "gateway_app\flows\housekeeping_flows.py"
  echo.

  echo === gateway_app\flows\__init__.py ===
  type "gateway_app\flows\__init__.py"
  echo.

  echo === gateway_app\flows\housekeeping\areas_comunes_helpers.py ===
  type "gateway_app\flows\housekeeping\areas_comunes_helpers.py"
  echo.

  echo === gateway_app\flows\housekeeping\audio_integration.py ===
  type "gateway_app\flows\housekeeping\audio_integration.py"
  echo.

  echo === gateway_app\flows\housekeeping\demo_tickets.py ===
  type "gateway_app\flows\housekeeping\demo_tickets.py"
  echo.

  echo === gateway_app\flows\housekeeping\intents.py ===
  type "gateway_app\flows\housekeeping\intents.py"
  echo.

  echo === gateway_app\flows\housekeeping\message_handler.py ===
  type "gateway_app\flows\housekeeping\message_handler.py"
  echo.

  echo === gateway_app\flows\housekeeping\orchestrator_hk_multiticket.py ===
  type "gateway_app\flows\housekeeping\orchestrator_hk_multiticket.py"
  echo.

  echo === gateway_app\flows\housekeeping\outgoing.py ===
  type "gateway_app\flows\housekeeping\outgoing.py"
  echo.

  echo === gateway_app\flows\housekeeping\reminders.py ===
  type "gateway_app\flows\housekeeping\reminders.py"
  echo.

  echo === gateway_app\flows\housekeeping\state_simple.py ===
  type "gateway_app\flows\housekeeping\state_simple.py"
  echo.

  echo === gateway_app\flows\housekeeping\ui_simple.py ===
  type "gateway_app\flows\housekeeping\ui_simple.py"
  echo.

  echo === gateway_app\flows\housekeeping\__init__.py ===
  type "gateway_app\flows\housekeeping\__init__.py"
  echo.

  echo === gateway_app\flows\supervision\audio_commands.py ===
  type "gateway_app\flows\supervision\audio_commands.py"
  echo.

  echo === gateway_app\flows\supervision\orchestrator_simple.py ===
  type "gateway_app\flows\supervision\orchestrator_simple.py"
  echo.

  echo === gateway_app\flows\supervision\outgoing.py ===
  type "gateway_app\flows\supervision\outgoing.py"
  echo.

  echo === gateway_app\flows\supervision\state.py ===
  type "gateway_app\flows\supervision\state.py"
  echo.

  echo === gateway_app\flows\supervision\ticket_assignment.py ===
  type "gateway_app\flows\supervision\ticket_assignment.py"
  echo.

  echo === gateway_app\flows\supervision\ubicacion_helpers.py ===
  type "gateway_app\flows\supervision\ubicacion_helpers.py"
  echo.

  echo === gateway_app\flows\supervision\ui_simple.py ===
  type "gateway_app\flows\supervision\ui_simple.py"
  echo.

  echo === gateway_app\flows\supervision\worker_search.py ===
  type "gateway_app\flows\supervision\worker_search.py"
  echo.

  echo === gateway_app\flows\supervision\__init__.py ===
  type "gateway_app\flows\supervision\__init__.py"
  echo.
)

echo OK - generado: %OUT%
endlocal
