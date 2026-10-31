from fastapi import APIRouter, HTTPException
from schemas import Profile
from typing import Dict, Any, Optional
from services.db_service import DBService

router = APIRouter(prefix="/profile", tags=["Profile"])

# Single-user deployment: all data is associated with a single "default" user.
# There is no authentication. See README for security implications.
DEFAULT_USER_ID = "default"


@router.get("", response_model=Profile)
async def get_profile():
    profile = DBService.get_profile(DEFAULT_USER_ID)
    if profile:
        return profile
    # Return a default empty profile if none has been set yet
    return Profile(user_id=DEFAULT_USER_ID)


@router.put("", response_model=Dict[str, str])
async def update_profile(payload: Dict[str, Any]):
    # Filter out unknown or read-only keys
    allowed = {
        "monthly_budget", "monthly_income", "fixed_costs",
        "emergency_fund", "currency", "risk_tolerance", "goals_enabled",
    }
    update_data = {k: v for k, v in payload.items() if k in allowed}
    if not update_data:
        raise HTTPException(status_code=400, detail="No valid profile fields provided")
    try:
        DBService.update_profile(DEFAULT_USER_ID, update_data)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"message": "Profile updated"}
