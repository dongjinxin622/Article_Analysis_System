@echo off
echo ========================================
echo   Article Analysis System v3 - Stop
echo ========================================
echo.

echo [1/2] Stopping backend service...
taskkill /FI "WINDOWTITLE eq SciPDF Backend*" /F >nul 2>&1
echo [Backend] Service stopped

echo.
echo [2/2] Stopping frontend service...
taskkill /FI "WINDOWTITLE eq SciPDF Frontend*" /F >nul 2>&1
echo [Frontend] Service stopped

echo.
echo ========================================
echo   All services stopped
echo ========================================
echo.
pause