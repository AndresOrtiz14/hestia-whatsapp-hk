@echo off
setlocal EnableExtensions EnableDelayedExpansion

set "OUT=project_extract.txt"
if exist "%OUT%" del "%OUT%"

set FILES=.env.example app.py extract_project.bat render.yaml requirements.txt ^
gateway_app\config.py gateway_app\__init__.py ^
gateway_app\core\utils\horario.py ^
gateway_app\core\utils\location_format.py ^
gateway_app\core\utils\__init__.py ^
gateway_app\flows\housekeeping_flows.py gateway_app\flows\__init__.py ^
gateway_app\flows\housekeeping\areas_comunes_helpers.py ^
gateway_app\flows\housekeeping\audio_integration.py ^
gateway_app\flows\housekeeping\demo_tickets.py ^
gateway_app\flows\housekeeping\intents.py ^
gateway_app\flows\housekeeping\message_handler.py ^
gateway_app\flows\housekeeping\orchestrator_hk_multiticket.py ^
gateway_app\flows\housekeeping\outgoing.py ^
gateway_app\flows\housekeeping\reminders.py ^
gateway_app\flows\housekeeping\state_simple.py ^
gateway_app\flows\housekeeping\turno_auto.py ^
gateway_app\flows\housekeeping\ui_simple.py ^
gateway_app\flows\housekeeping\__init__.py ^
gateway_app\flows\supervision\audio_commands.py ^
gateway_app\flows\supervision\orchestrator.py ^
gateway_app\flows\supervision\orchestrator_simple.py ^
gateway_app\flows\supervision\outgoing.py ^
gateway_app\flows\supervision\state.py ^
gateway_app\flows\supervision\ticket_assignment.py ^
gateway_app\flows\supervision\tiempo_utils.py ^
gateway_app\flows\supervision\ubicacion_helpers.py ^
gateway_app\flows\supervision\ui_simple.py ^
gateway_app\flows\supervision\worker_search.py ^
gateway_app\flows\supervision\__init__.py ^
gateway_app\routes\webhook.py gateway_app\routes\__init__.py ^
gateway_app\services\audio.py ^
gateway_app\services\daily_scheduler.py ^
gateway_app\services\db.py ^
gateway_app\services\migrations.py ^
gateway_app\services\runtime_state.py ^
gateway_app\services\tickets_db.py ^
gateway_app\services\ticket_watch.py ^
gateway_app\services\whatsapp_client.py ^
gateway_app\services\workers_db.py ^
gateway_app\services\__init__.py

for %%F in (%FILES%) do (
  echo === %%F ===>> "%OUT%"
  if exist "%%F" (
    type "%%F">> "%OUT%"
  ) else (
    echo [MISSING FILE] %%F>> "%OUT%"
  )
  echo.>> "%OUT%"
)

echo Listo. Generado: %OUT%
endlocal