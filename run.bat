@echo off
setlocal enabledelayedexpansion

set "PYTHON=D:\WPy64-312101_paper\python\python.exe"
set "PORT=20035"

echo ============================================
echo  Co-Scientist Agent Server
echo ============================================
echo.

echo [1/3] Checking Python...
"%PYTHON%" --version
if %ERRORLEVEL% neq 0 (
    echo ERROR: Python not found. Check PYTHON path.
    pause
    exit /b 1
)

echo.
echo [2/3] Checking packages...
"%PYTHON%" -c "import fastapi, uvicorn, langgraph, pymilvus, sqlalchemy, httpx, langfuse" 2>nul
if %ERRORLEVEL% neq 0 (
    echo Installing packages...
    "%PYTHON%" -m pip install -r requirements.txt
)

for /f "tokens=2 delims==" %%a in ('findstr /b "SERVER_PORT" .env 2^>nul') do set "PORT=%%a"

echo.
echo [3/3] Starting server on port %PORT% ...
echo.
echo   Swagger UI  : http://localhost:%PORT%/docs
echo   Chat API    : http://localhost:%PORT%/api/chat
echo   OpenAI API  : http://localhost:%PORT%/v1/chat/completions
echo.
echo   -- Open WebUI --
echo   Base URL : http://localhost:%PORT%/v1
echo   API Key  : co-sci
echo   Model    : co-scientist
echo.
echo   Press Ctrl+C to stop.
echo ============================================

"%PYTHON%" -m uvicorn app.main:app --host 0.0.0.0 --port %PORT% --reload

endlocal
