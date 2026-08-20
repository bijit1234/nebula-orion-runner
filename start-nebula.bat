@echo off
echo ========================================
echo    🚀 STARTING NEBULA CODE RUNNER
echo ========================================
echo.

echo [1/3] Starting Backend...
start "NEBULA Backend" cmd /k "cd backend && venv\Scripts\activate && python -m app.main"

echo [2/3] Waiting for backend to start...
timeout /t 3 /nobreak >nul

echo [3/3] Starting Frontend...
start "NEBULA Frontend" cmd /k "cd frontend && npm start"

echo.
echo ========================================
echo    ✅ NEBULA is starting!
echo    📱 Open: http://localhost:3000
echo    🔑 Login: admin / password123
echo ========================================
echo.
echo Press any key to close this window...
pause >nul