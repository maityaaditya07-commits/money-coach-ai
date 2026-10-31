from fastapi import APIRouter
from schemas import ChatRequest, ChatResponse
from typing import List
from services.agent import CoachAgent

router = APIRouter(prefix="/coach", tags=["Coach"])

@router.post("/chat", response_model=ChatResponse)
async def coach_chat(payload: ChatRequest):
    return CoachAgent.handle_chat(payload.message)
