@echo off
echo ========================================
echo   Article Analysis System v3 - Start
echo ========================================
echo.

:: Load environment variables from .env
for /f "tokens=1,2 delims==" %%a in ('type "%~dp0.env" 2^>nul') do (
    set %%a=%%b
)

:: Set Python executable (default to D:\temp\python.exe if not set)
if "%PYTHON_EXECUTABLE%"=="" set PYTHON_EXECUTABLE=D:\temp\python.exe

:: Start Backend (from project root directory)
echo [1/2] Starting backend service...
start "SciPDF Backend" cmd /k "cd /d %~dp0 && %PYTHON_EXECUTABLE% -m uvicorn backend.app.main:app --host 0.0.0.0 --port 8000 --reload"
timeout /t 3 >nul

:: Start Frontend
echo [2/2] Starting frontend service...
start "SciPDF Frontend" cmd /k "cd /d %~dp0frontend && npm run dev"
timeout /t 2 >nul

echo.
echo ========================================
echo   Services started!
echo   Backend:  http://localhost:8000
echo   Frontend: http://localhost:3000
echo   API Docs: http://localhost:8000/docs
echo ========================================
echo.
pause