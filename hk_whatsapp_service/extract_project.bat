@echo off
setlocal EnableDelayedExpansion

set "OUTPUT=project_extract.txt"
if exist "%OUTPUT%" del "%OUTPUT%"

for /R %%F in (*) do (
    set "skip="

    REM Excluir rutas venv y __pycache__
    echo "%%~fF" | findstr /I "\\venv\\" >nul && set "skip=1"
    echo "%%~fF" | findstr /I "\\__pycache__\\" >nul && set "skip=1"

    REM Excluir extension .pyc
    if /I "%%~xF"==".pyc" set "skip=1"

    REM Excluir el archivo de salida
    if /I "%%~nxF"=="%OUTPUT%" set "skip=1"

    if not defined skip (
        echo === %%~fF ===>> "%OUTPUT%"
        type "%%~fF" >> "%OUTPUT%"
        echo.>> "%OUTPUT%"
    )
)

echo Proyecto extraído en %OUTPUT%
pause
