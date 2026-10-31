from fastapi import APIRouter, Body, HTTPException
from schemas import Subscription, SubscriptionUnusedRequest
from typing import List
from services.recurring import RecurringService
from services.db_service import DBService

router = APIRouter(prefix="/subscriptions", tags=["Subscriptions"])

@router.get("", response_model=List[Subscription])
async def get_subscriptions():
    # Update subscriptions from transactions first
    RecurringService.sync_subscriptions()
    return DBService.get_subscriptions()

@router.post("/{merchant}/unused", response_model=dict)
async def set_unused(merchant: str, payload: SubscriptionUnusedRequest):
    DBService.update_subscription_unused(merchant, payload.unused)
    return {"message": "Status updated"}
