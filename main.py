import os
import datetime
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
from typing import List

from routers import ingest, transactions, subscriptions, profile, whatif, coach, report, goals
from schemas import Rule, Nudge, Dashboard, GuardrailLog, Preset, WhatIfResult
from db import init_db, get_db_connection
from services.db_service import DBService
from services.engine import FinancialEngine
from services.nudges import NudgeService

load_dotenv()

# Initialize Database
init_db()

app = FastAPI(title="Personal Finance Coach API", version="0.1.0")

# CORS configuration
allowed_origins = os.getenv("ALLOWED_ORIGINS", "*").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Root endpoints
@app.get("/health", tags=["System"])
async def health():
    return {"status": "ok"}


@app.post("/reset", tags=["System"])
async def reset_data():
    """Wipes all data — intended for demo/testing use only. Disabled by default and in production."""
    environment = os.getenv("ENVIRONMENT", "development").lower()
    enable_reset = os.getenv("ENABLE_RESET", "false").lower() in ("true", "1", "yes")

    if environment == "production" or not enable_reset:
        raise HTTPException(
            status_code=403,
            detail="Reset endpoint is disabled. Set ENABLE_RESET=true in development to enable.",
        )

    with get_db_connection() as conn:
        conn.execute("DELETE FROM transactions")
        conn.execute("DELETE FROM subscriptions")
        conn.execute("DELETE FROM goals")
        conn.execute("DELETE FROM rules")
        conn.execute("DELETE FROM guardrail_logs")
        conn.execute("DELETE FROM profile")
        conn.commit()
    return {"message": "Data reset successfully"}


# Rule management — backed by real database
@app.get("/rules", response_model=List[Rule], tags=["System"])
async def get_rules():
    return DBService.get_rules()


@app.delete("/rules/{id}", tags=["System"])
async def delete_rule(id: int):
    DBService.delete_rule(id)
    return {"message": "Rule deleted"}


# Dashboard & Nudges
@app.get("/dashboard", response_model=Dashboard, tags=["Dashboard"])
async def get_dashboard():
    now = datetime.datetime.now()
    curr_month = now.strftime("%Y-%m")

    stats = FinancialEngine.get_monthly_stats(curr_month)

    # Use profile emergency_fund if available, otherwise fall back to 50k
    profile_data = DBService.get_profile("default")
    emergency_savings = 50000.0
    if profile_data and profile_data.emergency_fund is not None:
        emergency_savings = profile_data.emergency_fund

    # Calculate total goal progress (simple average across all goals)
    all_goals = DBService.get_goals()
    goal_progress = 0.0
    if all_goals:
        total_target = sum(g.target_amount for g in all_goals if g.target_amount > 0)
        total_current = sum(g.current_amount for g in all_goals)
        if total_target > 0:
            goal_progress = round(total_current / total_target, 4)

    subs = DBService.get_subscriptions()
    alert_count = len([s for s in subs if s.alert])

    return Dashboard(
        runway=FinancialEngine.calculate_runway(emergency_savings),
        goal_progress=goal_progress,
        projected_goal_date=None,
        category_totals=stats["category_totals"],
        top_nudges=[n.message for n in NudgeService.generate_nudges()],
        subscription_alert_count=alert_count,
    )


@app.get("/nudges", response_model=List[Nudge], tags=["Dashboard"])
async def get_nudges():
    return NudgeService.generate_nudges()


# Top-level Presets endpoints (API contract specifies /presets, not /whatif/presets)
_PRESETS = [
    Preset(name="Minimalist", description="Cut all luxury", changes={"Dining": -0.8, "Entertainment": -1.0}),
    Preset(name="Aggressive Saver", description="Save 50% of income", changes={"Dining": -0.5, "Shopping": -0.7}),
]


@app.get("/presets", response_model=List[Preset], tags=["What-If"])
async def get_presets_toplevel():
    return _PRESETS


@app.post("/presets/{name}/apply", response_model=WhatIfResult, tags=["What-If"])
async def apply_preset_toplevel(name: str):
    from fastapi import HTTPException
    preset = next((p for p in _PRESETS if p.name == name), None)
    if not preset:
        raise HTTPException(status_code=404, detail=f"Preset '{name}' not found")
    return FinancialEngine.simulate_what_if(preset.changes)


# Guardrails — backed by real database
@app.get("/guardrail/log", response_model=List[GuardrailLog], tags=["System"])
async def get_guardrail_logs():
    return DBService.get_guardrail_logs()


# Include routers
app.include_router(ingest.router)
app.include_router(transactions.router)
app.include_router(subscriptions.router)
app.include_router(profile.router)
app.include_router(goals.router)
app.include_router(whatif.router)
app.include_router(coach.router)
app.include_router(report.router)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
