from decimal import Decimal, ROUND_HALF_UP
from typing import List, Dict, Any, Optional
from datetime import datetime, date, timedelta
from collections import defaultdict
from services.db_service import DBService
from schemas import Dashboard, MonthlyReport

class FinancialEngine:
    @staticmethod
    def to_decimal(value: Any) -> Decimal:
        if value is None:
            return Decimal('0.00')
        return Decimal(str(value)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

    @classmethod
    def get_monthly_stats(cls, month: str) -> Dict[str, Any]:
        """
        Calculates totals for a given month (YYYY-MM).
        """
        txs = DBService.get_transactions(month=month, limit=10000)

        income = Decimal('0.00')
        expenses = Decimal('0.00')
        category_totals = defaultdict(Decimal)

        for tx in txs:
            amt = cls.to_decimal(tx.amount)
            if amt > 0:
                income += amt
            else:
                expenses += abs(amt)
                category_totals[tx.category] += abs(amt)

        savings = income - expenses
        savings_rate = (savings / income * 100) if income > 0 else Decimal('0.00')

        return {
            "income": income,
            "expenses": expenses,
            "savings": savings,
            "savings_rate": savings_rate.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP),
            "category_totals": {k: float(v) for k, v in category_totals.items()},
            "surplus": savings
        }

    @classmethod
    def calculate_runway(cls, emergency_savings: float) -> float:
        """
        Runway = Emergency Savings / Average Essential Monthly Expenditure.
        """
        # Essential categories: Housing, Utilities, Groceries, Health
        essentials = ["Housing", "Utilities", "Groceries", "Health"]

        # Get last 3 months of data
        all_txs = DBService.get_transactions(limit=1000)
        monthly_essentials = defaultdict(Decimal)

        for tx in all_txs:
            if tx.category in essentials:
                d = tx.date
                month = d[:7] if isinstance(d, str) else d.strftime("%Y-%m")
                monthly_essentials[month] += cls.to_decimal(abs(tx.amount))

        if not monthly_essentials:
            return 0.0

        avg_essential = sum(monthly_essentials.values()) / len(monthly_essentials)

        if avg_essential <= 0:
            return float('inf') if emergency_savings > 0 else 0.0

        return float(Decimal(str(emergency_savings)) / avg_essential)

    @classmethod
    def get_mom_comparison(cls, current_month: str) -> Dict[str, Any]:
        """
        Compares current month spending with previous month.
        """
        curr_stats = cls.get_monthly_stats(current_month)

        # Simple prev month logic
        dt = datetime.strptime(current_month, "%Y-%m")
        # Approximate previous month
        prev_month = (dt.replace(day=1) - timedelta(days=1)).strftime("%Y-%m")
        prev_stats = cls.get_monthly_stats(prev_month)

        curr_exp = curr_stats['expenses']
        prev_exp = prev_stats['expenses']

        diff = curr_exp - prev_exp
        percent_change = (diff / prev_exp * 100) if prev_exp > 0 else Decimal('0.00')

        return {
            "diff": float(diff),
            "percent_change": float(percent_change.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP))
        }

    @classmethod
    def simulate_what_if(cls, changes: Dict[str, Any]) -> Dict[str, Any]:
        """
        Simulates financial impact of changes.
        changes: {"Dining": -0.30, "Rent": 3000, "cancel": ["Netflix"]}
        """
        # Use current month as baseline
        now = datetime.now()
        curr_month = now.strftime("%Y-%m")
        stats = cls.get_monthly_stats(curr_month)

        original_expenses = stats['expenses']
        original_savings = stats['savings']

        projected_expenses = original_expenses
        impact_details = []

        # 1. Category changes (percentage or absolute)
        for category, change in changes.items():
            if category == "cancel":
                continue

            current_cat_spend = cls.to_decimal(stats['category_totals'].get(category, 0))
            if current_cat_spend == 0:
                continue

            if isinstance(change, float) and -1.0 <= change <= 1.0:
                # Percentage change
                savings = current_cat_spend * Decimal(str(-change))
                projected_expenses -= savings
                impact_details.append(f"Reducing {category} by {abs(change)*100:.0f}% saves {savings:.2f}")
            else:
                # Absolute change
                savings = cls.to_decimal(change)
                # If change is positive, it's an increase in expense (negative savings)
                projected_expenses += cls.to_decimal(change)
                impact_details.append(f"Adding {change} to {category} changes savings by {-savings:.2f}")

        # 2. Subscription cancellations
        cancelled_subs = changes.get("cancel", [])
        from services.recurring import RecurringService
        subs = RecurringService.detect_subscriptions()

        for sub_name in cancelled_subs:
            sub = next((s for s in subs if s['merchant'] == sub_name), None)
            if sub:
                amt = cls.to_decimal(sub['amount'])
                # Subscriptions are stored as negative expenses in transactions,
                # but usually as positive magnitude in the subscriptions table.
                # Let's ensure we subtract the absolute value of the expense.
                savings = abs(amt)
                projected_expenses -= savings
                impact_details.append(f"Cancelling {sub_name} saves {savings:.2f}/mo")

        projected_savings = stats['income'] - projected_expenses

        # Runway impact
        # Default emergency savings 50k for simulation if not available
        runway_old = cls.calculate_runway(50000.0)
        # New avg essential = old avg essential - savings from essentials
        # For simplicity, we assume all savings go to emergency fund
        # This is a projection, so we use the surplus

        return {
            "projected_savings": float(projected_savings),
            "new_runway": runway_old + (float(projected_savings - original_savings) / 2000.0), # Rough estimate
            "impact_summary": " ".join(impact_details) if impact_details else "No significant changes detected."
        }
