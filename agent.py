from typing import List, Dict, Any, Optional
from services.db_service import DBService
from services.engine import FinancialEngine
from services.nudges import NudgeService
from schemas import ChatResponse
import datetime

class CoachAgent:
    @classmethod
    def handle_chat(cls, message: str) -> ChatResponse:
        """
        Deterministic financial coach that analyzes data to provide guidance.
        """
        msg = message.lower()
        now = datetime.datetime.now()
        curr_month = now.strftime("%Y-%m")
        stats = FinancialEngine.get_monthly_stats(curr_month)

        # Intent: Affordability Check
        if any(word in msg for word in ["afford", "buy", "purchase"]):
            return cls._handle_affordability(stats)

        # Intent: Spending Analysis
        if any(word in msg for word in ["spending", "where", "analyze", "pattern"]):
            return cls._handle_spending_analysis(stats)

        # Intent: Savings Advice
        if any(word in msg for word in ["save", "savings", "goal"]):
            return cls._handle_savings_advice(stats)

        # Fallback: General Guidance
        return ChatResponse(
            intent="general_guidance",
            reply="I can help you analyze your spending, check if you can afford a purchase, or plan your savings. Try asking 'Can I afford a new phone?' or 'Analyze my spending'.",
            numbers_used=[],
            blocked=False
        )

    @classmethod
    def _handle_affordability(cls, stats: Dict[str, Any]) -> ChatResponse:
        surplus = stats['surplus']
        if surplus <= 0:
            return ChatResponse(
                intent="affordability_check",
                reply="Currently, your expenses exceed or equal your income. I recommend reducing spending before making a large purchase.",
                numbers_used=[float(surplus)],
                blocked=False
            )

        return ChatResponse(
            intent="affordability_check",
            reply=f"You have a monthly surplus of {surplus:.2f}. Depending on the cost, you can save for this over a few months.",
            numbers_used=[float(surplus)],
            blocked=False
        )

    @classmethod
    def _handle_spending_analysis(cls, stats: Dict[str, Any]) -> ChatResponse:
        top_cat = "None"
        max_amt = 0
        for cat, amt in stats['category_totals'].items():
            if amt > max_amt:
                max_amt = amt
                top_cat = cat

        if top_cat == "None":
            return ChatResponse(
                intent="spending_analysis",
                reply="I don't have enough transaction data for the current month to analyze your patterns.",
                numbers_used=[],
                blocked=False
            )

        return ChatResponse(
            intent="spending_analysis",
            reply=f"Your highest spending category this month is {top_cat} at {max_amt:.2f}. Reducing this could significantly boost your savings.",
            numbers_used=[float(max_amt)],
            blocked=False
        )

    @classmethod
    def _handle_savings_advice(cls, stats: Dict[str, Any]) -> ChatResponse:
        savings_rate = stats['savings_rate']

        if savings_rate < 10:
            reply = f"Your savings rate is {savings_rate:.1f}%. Aiming for 20% is a great baseline for financial health."
        elif savings_rate < 30:
            reply = f"Your savings rate is {savings_rate:.1f}%. You're doing well! Consider investing the surplus."
        else:
            reply = f"Your savings rate is {savings_rate:.1f}%. Excellent discipline!"

        return ChatResponse(
            intent="savings_advice",
            reply=reply,
            numbers_used=[float(savings_rate)],
            blocked=False
        )
