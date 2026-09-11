@echo off
chcp 65001 >nul
cd /d "%~dp0"
title 곽봇 서버
echo.
echo   곽봇 서버를 켭니다. 브라우저에서 http://127.0.0.1:8000 을 여세요.
echo   이 창을 닫으면 서버가 꺼집니다.
echo.
start "" http://127.0.0.1:8000
.venv\Scripts\python -m uvicorn app.main:app --port 8000
pause
