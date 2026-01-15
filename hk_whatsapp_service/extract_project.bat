@echo off
setlocal enabledelayedexpansion

set "OUT=project_extract.txt"

REM Lista de archivos (según tree)
set FILES=.env.example ^
app.py ^
render.yaml ^
requirements.txt ^
gateway_app\config.py ^
gateway_app\__init__.py ^
gateway_app\routes\webhook.py ^
gateway_app\routes\__init__.py ^
gateway_app\services\audio.py ^
gateway_app\services\db.py ^
gateway_app\services\migrations.py ^
gateway_app\services\runtime_state.py ^
gateway_app\services\tickets_db.py ^
gateway_app\services\whatsapp_client.py ^
gateway_app\services\workers_db.py ^
gateway_app\services\__init__.py ^
gateway_app\flows\housekeeping_flows.py ^
gateway_app\flows\__init__.py ^
gateway_app\flows\housekeeping\areas_comunes_helpers.py ^
gateway_app\flows\housekeeping\audio_integration.py ^
gateway_app\flows\housekeeping\demo_tickets.py ^
gateway_app\flows\housekeeping\intents.py ^
gateway_app\flows\housekeeping\message_handler.py ^
gateway_app\flows\housekeeping\orchestrator_hk_multiticket.py ^
gateway_app\flows\housekeeping\outgoing.py ^
gateway_app\flows\housekeeping\reminders.py ^
gateway_app\flows\housekeeping\state_simple.py ^
gateway_app\flows\housekeeping\ui_simple.py ^
gateway_app\flows\housekeeping\__init__.py ^
gateway_app\flows\supervision\audio_commands.py ^
gateway_app\flows\supervision\orchestrator.py ^
gateway_app\flows\supervision\orchestrator_simple.py ^
gateway_app\flows\supervision\outgoing.py ^
gateway_app\flows\supervision\state.py ^
gateway_app\flows\supervision\ticket_assignment.py ^
gateway_app\flows\supervision\ubicacion_helpers.py ^
gateway_app\flows\supervision\ui_simple.py ^
gateway_app\flows\supervision\worker_search.py ^
gateway_app\flows\supervision\__init__.py

REM Generar el extract
> "%OUT%" (
  for %%F in (%FILES%) do (
    echo === %%F ===
    if exist "%%F" (
      type "%%F"
    ) else (
      echo [MISSING FILE] %%F
    )
    echo.
  )
)

echo OK - generado: %OUT%
endlocal
