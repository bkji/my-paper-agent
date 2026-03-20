@echo off
chcp 65001 >nul
echo ============================================
echo  Co-Scientist Agent 서버 시작
echo ============================================
echo.

set PYTHON=D:\WPy64-312101_paper\python\python.exe

echo [1/3] Python 환경 확인...
%PYTHON% --version
if %ERRORLEVEL% neq 0 (
    echo ERROR: Python을 찾을 수 없습니다. PYTHON 경로를 확인하세요.
    pause
    exit /b 1
)

echo.
echo [2/3] 필수 패키지 확인...
%PYTHON% -c "import fastapi, uvicorn, langgraph, pymilvus, sqlalchemy, httpx, langfuse" 2>nul
if %ERRORLEVEL% neq 0 (
    echo 패키지 설치 중...
    %PYTHON% -m pip install -r requirements.txt
)

:: .env에서 포트 읽기
for /f "tokens=2 delims==" %%a in ('findstr /b "SERVER_PORT" .env') do set PORT=%%a
if "%PORT%"=="" set PORT=20035

echo.
echo [3/3] FastAPI 서버 시작 (port=%PORT%)...
echo.
echo   Swagger UI:     http://localhost:%PORT%/docs
echo   API 엔드포인트:  http://localhost:%PORT%/api/chat
echo   OpenAI 호환:    http://localhost:%PORT%/v1/chat/completions
echo.
echo   ── Open WebUI 연결 설정 ──
echo   Base URL:  http://localhost:%PORT%/v1
echo   API Key:   .env의 OPENAI_COMPAT_API_KEY 값
echo   모델명:    co-scientist
echo.
echo   종료: Ctrl+C
echo ============================================

%PYTHON% -m uvicorn app.main:app --host 0.0.0.0 --port %PORT% --reload
