@echo off
echo ========================================
echo   启动 Celery Worker
echo ========================================
echo.

cd /d "%~dp0..\backend"

echo 启动 Celery Worker...
celery -A backend.app.tasks worker -l info -P solo -Q pdf,ner,re,batch,default

pause