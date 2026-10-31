from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from datetime import date

# --- Common ---
class ErrorDetail(BaseModel):
    code: str
    message: str

class ErrorResponse(BaseModel):
    error: ErrorDetail

# --- Transactions ---
class Transaction(BaseModel):
    id: int
    date: date
    description: str
    amount: float
    category: str
    merchant: str

class CategoryUpdateRequest(BaseModel):
    category: str

class CategoryUpdateResponse(BaseModel):
    rule: str
    affected_count: int
    transactions_updated: int

class Rule(BaseModel):
    id: int
    pattern: str
    category: str

# --- Subscriptions ---
class Subscription(BaseModel):
    merchant: str
    amount: float
    billing_cycle: str
    last_billed_date: date
    is_unused: bool = False
    alert: Optional[str] = None

class SubscriptionUnusedRequest(BaseModel):
    unused: bool

# --- Profile ---
class Profile(BaseModel):
    user_id: str
    monthly_budget: Optional[float] = None
    monthly_income: Optional[float] = None
    fixed_costs: Optional[float] = None
    emergency_fund: Optional[float] = None
    currency: str = "INR"
    risk_tolerance: Optional[str] = None
    goals_enabled: bool = True

# --- Goals ---
class Goal(BaseModel):
    id: int
    name: str
    target_amount: float
    current_amount: float
    deadline: Optional[date] = None

# --- What-If ---
class WhatIfRequest(BaseModel):
    changes: Dict[str, Any] # e.g., {"Dining": -0.30, "Rent": 3000, "cancel": ["Netflix"]}

class WhatIfResult(BaseModel):
    projected_savings: float
    new_runway: float
    impact_summary: str

class Preset(BaseModel):
    name: str
    description: str
    changes: Dict[str, Any]

# --- Dashboard ---
class Dashboard(BaseModel):
    runway: float
    goal_progress: float
    projected_goal_date: Optional[date]
    category_totals: Dict[str, float]
    top_nudges: List[str]
    subscription_alert_count: int

class Nudge(BaseModel):
    id: int
    message: str
    priority: str # "low", "medium", "high"

# --- Reports ---
class MonthlyReport(BaseModel):
    month: str
    total_spent: float
    total_income: float
    top_categories: List[Dict[str, Any]]
    savings_rate: float

# --- Coach ---
class ChatRequest(BaseModel):
    message: str

class ChatResponse(BaseModel):
    intent: str
    reply: str
    numbers_used: List[float]
    blocked: bool

# --- Guardrails ---
class GuardrailLog(BaseModel):
    timestamp: str
    input: str
    action: str # "blocked", "sanitized", "passed"
    reason: Optional[str] = None

# --- Ingest ---
class IngestResponse(BaseModel):
    message: str
    transactions_count: Optional[int] = None
    detected_amount: Optional[float] = None
