@echo off
setlocal EnableExtensions EnableDelayedExpansion

set "OUT=project_extract.txt"

REM Limpia el archivo de salida
> "%OUT%" echo.

REM Lista de archivos (según tu tree)
set FILES=.env.example
set FILES=%FILES% app.py
set FILES=%FILES% render.yaml
set FILES=%FILES% requirements.txt
set FILES=%FILES% extract_project.bat

set FILES=%FILES% gateway_app\config.py
set FILES=%FILES% gateway_app\__init__.py

set FILES=%FILES% gateway_app\flows\__init__.py
set FILES=%FILES% gateway_app\flows\housekeeping_flows.py

set FILES=%FILES% gateway_app\flows\housekeeping\areas_comunes_helpers.py
set FILES=%FILES% gateway_app\flows\housekeeping\audio_integration.py
set FILES=%FILES% gateway_app\flows\housekeeping\demo_tickets.py
set FILES=%FILES% gateway_app\flows\housekeeping\intents.py
set FILES=%FILES% gateway_app\flows\housekeeping\message_handler.py
set FILES=%FILES% gateway_app\flows\housekeeping\orchestrator_hk_multiticket.py
set FILES=%FILES% gateway_app\flows\housekeeping\outgoing.py
set FILES=%FILES% gateway_app\flows\housekeeping\reminders.py
set FILES=%FILES% gateway_app\flows\housekeeping\state_simple.py
set FILES=%FILES% gateway_app\flows\housekeeping\ui_simple.py
set FILES=%FILES% gateway_app\flows\housekeeping\__init__.py

set FILES=%FILES% gateway_app\flows\supervision\audio_commands.py
set FILES=%FILES% gateway_app\flows\supervision\orchestrator.py
set FILES=%FILES% gateway_app\flows\supervision\orchestrator_simple.py
set FILES=%FILES% gateway_app\flows\supervision\outgoing.py
set FILES=%FILES% gateway_app\flows\supervision\state.py
set FILES=%FILES% gateway_app\flows\supervision\ticket_assignment.py
set FILES=%FILES% gateway_app\flows\supervision\ubicacion_helpers.py
set FILES=%FILES% gateway_app\flows\supervision\ui_simple.py
set FILES=%FILES% gateway_app\flows\supervision\worker_search.py
set FILES=%FILES% gateway_app\flows\supervision\__init__.py

set FILES=%FILES% gateway_app\routes\webhook.py
set FILES=%FILES% gateway_app\routes\__init__.py

set FILES=%FILES% gateway_app\services\audio.py
set FILES=%FILES% gateway_app\services\db.py
set FILES=%FILES% gateway_app\services\migrations.py
set FILES=%FILES% gateway_app\services\runtime_state.py
set FILES=%FILES% gateway_app\services\tickets_db.py
set FILES=%FILES% gateway_app\services\whatsapp_client.py
set FILES=%FILES% gateway_app\services\workers_db.py
set FILES=%FILES% gateway_app\services\__init__.py

for %%F in (%FILES%) do (
  >> "%OUT%" echo === %%F ===
  if exist "%%F" (
    type "%%F" >> "%OUT%"
  ) else (
    >> "%OUT%" echo [MISSING] %%F
  )
  >> "%OUT%" echo.
)

echo OK - generado: %OUT%
endlocal
