@echo off
echo [%TIME%] Starting Docker Desktop...
start "" "C:\Program Files\Docker\Docker\Docker Desktop.exe"

echo [%TIME%] Waiting for Docker engine (up to 3 min)...
set /a count=0
:waitloop
timeout /t 5 /nobreak >nul
set /a count+=5
docker -H tcp://localhost:2375 info >nul 2>&1
if %errorlevel%==0 goto :ready
if %count% GEQ 180 goto :timeout
echo [%TIME%] Still waiting... (%count%s)
goto :waitloop

:timeout
echo [%TIME%] ERROR: Docker Desktop did not start in time.
exit /b 1

:ready
echo [%TIME%] Docker engine ready after %count%s!
echo.
echo [%TIME%] Running docker compose up --build ...
set DOCKER_HOST=tcp://localhost:2375
docker compose up -d --build
echo [%TIME%] Done. Exit code: %errorlevel%
exit /b %errorlevel%
