"""Documents API — 논문 수집(ingest) 엔드포인트."""
import logging
from fastapi import APIRouter
from app.core.langfuse_client import observe, trace_attributes
from app.models.schemas import IngestRequest, IngestResponse
from app.services.ingest import ingest_paper

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/ingest", response_model=IngestResponse)
@observe(name="api_ingest")
async def ingest(request: IngestRequest) -> IngestResponse:
    logger.info("POST /api/documents/ingest: filename=%s", request.filename)

    paper = request.model_dump()
    with trace_attributes(metadata={"filename": request.filename}):
        result = await ingest_paper(paper)

    return IngestResponse(**result)
