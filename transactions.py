from fastapi import APIRouter, Query, HTTPException
from schemas import Transaction, CategoryUpdateRequest, CategoryUpdateResponse, Rule
from typing import List, Optional
from services.db_service import DBService
from services.categorizer import CategorizerService

router = APIRouter(prefix="/transactions", tags=["Transactions"])

@router.get("", response_model=List[Transaction])
async def get_transactions(
    month: Optional[str] = None,
    category: Optional[str] = None,
    limit: int = 10,
    offset: int = 0
):
    return DBService.get_transactions(month, category, limit, offset)

@router.patch("/{id}/category", response_model=CategoryUpdateResponse)
async def update_category(id: int, payload: CategoryUpdateRequest):
    try:
        return CategorizerService.apply_category_correction(id, payload.category)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
