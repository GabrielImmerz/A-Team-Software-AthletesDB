@echo off
setlocal
cd /d "%~dp0"
where py >nul 2>&1
if %errorlevel%==0 (
    set "PYTHON=py -3"
) else (
    set "PYTHON=python"
)
if not exist ".venv\Scripts\python.exe" (
    echo Erstelle Python-Umgebung ...
    %PYTHON% -m venv .venv
    if errorlevel 1 goto :error
)
echo Installiere / pruefe Abhaengigkeiten ...
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto :error
echo Starte Gewichtheben Tracker auf http://localhost:8501 ...
".venv\Scripts\python.exe" -m streamlit run app.py --server.address 127.0.0.1 --server.port 8501 --server.headless=false
exit /b 0
:error
echo.
echo Start fehlgeschlagen. Ist Python 3.10+ installiert und im PATH?
pause
exit /b 1
