@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion

echo ============================================================
echo  Co-Scientist Agent - API 응답 확인 (토큰 사용량 포함)
echo ============================================================
echo.

set BASE_URL=http://localhost:20035
set API_KEY=co-sci
set QUERY=24년 11월 논문 리스트

echo [1] /api/chat (자체 API, 비스트리밍)
echo ------------------------------------------------------------
curl -s -X POST "%BASE_URL%/api/chat/" ^
  -H "Content-Type: application/json" ^
  -H "Authorization: Bearer %API_KEY%" ^
  -d "{\"query\": \"%QUERY%\", \"stream\": false}" | python -m json.tool --no-ensure-ascii 2>nul || (
    curl -s -X POST "%BASE_URL%/api/chat/" ^
      -H "Content-Type: application/json" ^
      -H "Authorization: Bearer %API_KEY%" ^
      -d "{\"query\": \"%QUERY%\", \"stream\": false}"
)

echo.
echo.
echo [2] /v1/chat/completions (OpenAI 호환, 비스트리밍)
echo ------------------------------------------------------------
curl -s -X POST "%BASE_URL%/v1/chat/completions" ^
  -H "Content-Type: application/json" ^
  -H "Authorization: Bearer %API_KEY%" ^
  -d "{\"model\": \"co-scientist-bk03\", \"messages\": [{\"role\": \"user\", \"content\": \"%QUERY%\"}], \"stream\": false}" | python -m json.tool --no-ensure-ascii 2>nul || (
    curl -s -X POST "%BASE_URL%/v1/chat/completions" ^
      -H "Content-Type: application/json" ^
      -H "Authorization: Bearer %API_KEY%" ^
      -d "{\"model\": \"co-scientist-bk03\", \"messages\": [{\"role\": \"user\", \"content\": \"%QUERY%\"}], \"stream\": false}"
)

echo.
echo.
echo [3] /v1/chat/completions (OpenAI 호환, 스트리밍 + usage)
echo ------------------------------------------------------------
curl -s -N -X POST "%BASE_URL%/v1/chat/completions" ^
  -H "Content-Type: application/json" ^
  -H "Authorization: Bearer %API_KEY%" ^
  -d "{\"model\": \"co-scientist-bk03\", \"messages\": [{\"role\": \"user\", \"content\": \"%QUERY%\"}], \"stream\": true, \"stream_options\": {\"include_usage\": true}}"

echo.
echo.
echo ============================================================
echo  완료
echo ============================================================
pause
