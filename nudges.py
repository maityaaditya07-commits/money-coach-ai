from typing import List
from services.db_service import DBService
from services.engine import FinancialEngine
from schemas import Nudge

class NudgeService:
    @classmethod
    def generate_nudges(cls) -> List[Nudge]:
        """
        Generates evidence-based nudges based on financial data.
        """
        nudges = []

        # 1. Unusual category spending
        # Compare last 30 days vs previous 30-60 days
        # For simplicity in hackathon, we'll use MoM from FinancialEngine
        import datetime
        now = datetime.datetime.now()
        curr_month = now.strftime("%Y-%m")

        stats = FinancialEngine.get_monthly_stats(curr_month)
        prev_month = (now.replace(day=1) - datetime.timedelta(days=1)).strftime("%Y-%m")
        prev_stats = FinancialEngine.get_monthly_stats(prev_month)

        for cat, amt in stats['category_totals'].items():
            prev_amt = prev_stats['category_totals'].get(cat, 0)
            if prev_amt > 0 and amt > prev_amt * 1.2:
                nudges.append(Nudge(
                    id=101,
                    message=f"Spending in {cat} is 20% higher than last month ({amt} vs {prev_amt})",
                    priority="medium"
                ))

        # 2. Budget overruns
        profile = DBService.get_profile("default")  # Single-user deployment
        if profile and profile.monthly_budget is not None and stats['expenses'] > FinancialEngine.to_decimal(profile.monthly_budget):
            nudges.append(Nudge(
                id=102,
                message=f"You've exceeded your monthly budget of {profile.monthly_budget} by {stats['expenses'] - FinancialEngine.to_decimal(profile.monthly_budget)}",
                priority="high"
            ))

        # 3. Low Emergency Fund Runway
        # Assume 50000 emergency savings for the nudge logic if not set
        runway = FinancialEngine.calculate_runway(50000.0)
        if runway < 3.0:
            nudges.append(Nudge(
                id=103,
                message=f"Your emergency fund runway is low ({runway:.1f} months). Try to increase savings.",
                priority="high"
            ))

        return nudges
