@echo off
echo ========================================
echo   SciPDF v3 全服务启动脚本
echo ========================================
echo.

set PROJECT_DIR=data\00. 研究课题\Article_Analysis_System_v3

echo [1/4] 启动后端 API 服务...
start "Backend API" cmd /k "cd /d %PROJECT_DIR%\backend && python main.py"
timeout /t 3 >nul

echo [2/4] 启动 Celery Worker...
start "Celery Worker" cmd /k "cd /d %PROJECT_DIR%\backend && celery -A backend.app.tasks worker -l info -P solo"
timeout /t 3 >nul

echo [3/4] 启动前端开发服务...
start "Frontend Dev" cmd /k "cd /d %PROJECT_DIR%\frontend && npm run dev"
timeout /t 5 >nul

echo.
echo ========================================
echo   所有服务已启动!
echo ========================================
echo.
echo   - 后端 API: http://127.0.0.1:8000
echo   - 前端页面: http://localhost:3000 或 3001
echo   - API文档:  http://127.0.0.1:8000/docs
echo.
echo   按 Ctrl+C 停止各服务窗口
echo ========================================

pause