from fastapi import APIRouter, HTTPException
from schemas import Goal
from typing import List, Dict, Any
from services.db_service import DBService
from pydantic import BaseModel
from typing import Optional
from datetime import date

router = APIRouter(prefix="/goals", tags=["Goals"])


class GoalCreateRequest(BaseModel):
    name: str
    target_amount: float
    current_amount: float = 0.0
    deadline: Optional[date] = None


class GoalUpdateRequest(BaseModel):
    name: Optional[str] = None
    target_amount: Optional[float] = None
    current_amount: Optional[float] = None
    deadline: Optional[date] = None


@router.get("", response_model=List[Goal])
async def get_goals():
    return DBService.get_goals()


@router.post("", response_model=Goal, status_code=201)
async def create_goal(payload: GoalCreateRequest):
    goal_data = {
        "name": payload.name,
        "target_amount": payload.target_amount,
        "current_amount": payload.current_amount,
        "deadline": str(payload.deadline) if payload.deadline else None,
    }
    goal_id = DBService.add_goal(goal_data)
    goals = DBService.get_goals()
    goal = next((g for g in goals if g.id == goal_id), None)
    if not goal:
        raise HTTPException(status_code=500, detail="Failed to create goal")
    return goal


@router.put("/{id}", response_model=Dict[str, str])
async def update_goal(id: int, payload: GoalUpdateRequest):
    update_data = payload.model_dump(exclude_none=True)
    if "deadline" in update_data and update_data["deadline"] is not None:
        update_data["deadline"] = str(update_data["deadline"])
    try:
        DBService.update_goal(id, update_data)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"message": "Goal updated"}


@router.delete("/{id}", response_model=Dict[str, str])
async def delete_goal(id: int):
    DBService.delete_goal(id)
    return {"message": "Goal deleted"}
