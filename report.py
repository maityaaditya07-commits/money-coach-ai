from fastapi import APIRouter, Query, HTTPException
from schemas import MonthlyReport
from typing import List
from services.engine import FinancialEngine
from fastapi import status

router = APIRouter(prefix="/report", tags=["Reports"])

@router.get("/monthly", response_model=MonthlyReport)
async def get_monthly_report(month: str = Query(..., description="YYYY-MM")):
    # Validate month format
    import re
    if not re.match(r"^\d{4}-(0[1-9]|1[0-2])$", month):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid month format. Use YYYY-MM")

    stats = FinancialEngine.get_monthly_stats(month)

    return MonthlyReport(
        month=month,
        total_spent=float(stats['expenses']),
        total_income=float(stats['income']),
        top_categories=[{"category": k, "amount": v} for k, v in stats['category_totals'].items()],
        savings_rate=float(stats['savings_rate'])
    )
