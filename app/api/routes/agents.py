"""Agents API — 사용 가능한 Agent 목록 조회."""
from fastapi import APIRouter
from app.agents.supervisor import AGENT_REGISTRY

router = APIRouter()


@router.get("/")
async def list_agents():
    return {k: {"description": v["description"]} for k, v in AGENT_REGISTRY.items()}
