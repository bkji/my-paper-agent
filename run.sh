#!/bin/bash
# Co-Scientist Agent 서버 시작 (Linux/폐쇄망 서버용)

echo "============================================"
echo " Co-Scientist Agent 서버 시작"
echo "============================================"

PORT=${PORT:-8080}
PYTHON=${PYTHON:-python3}

echo "[1/3] Python 환경 확인..."
$PYTHON --version || { echo "ERROR: Python을 찾을 수 없습니다."; exit 1; }

echo ""
echo "[2/3] 필수 패키지 확인..."
$PYTHON -c "import fastapi, uvicorn, langgraph, pymilvus, sqlalchemy, httpx, langfuse" 2>/dev/null
if [ $? -ne 0 ]; then
    echo "패키지 설치 중..."
    $PYTHON -m pip install -r requirements.txt
fi

echo ""
echo "[3/3] FastAPI 서버 시작 (port=$PORT)..."
echo ""
echo "  Swagger UI:     http://localhost:$PORT/docs"
echo "  API 엔드포인트:  http://localhost:$PORT/api/chat"
echo "  OpenAI 호환:    http://localhost:$PORT/v1/chat/completions"
echo "  Open WebUI 연결: http://localhost:$PORT/v1"
echo ""
echo "  종료: Ctrl+C"
echo "============================================"

$PYTHON -m uvicorn app.main:app --host 0.0.0.0 --port $PORT --reload
