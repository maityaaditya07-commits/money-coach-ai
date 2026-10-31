from fastapi import APIRouter
from schemas import Goal, WhatIfRequest, WhatIfResult, Preset
from typing import List
from services.engine import FinancialEngine

router = APIRouter(prefix="/whatif", tags=["What-If"])

@router.post("", response_model=WhatIfResult)
async def run_whatif(payload: WhatIfRequest):
    return FinancialEngine.simulate_what_if(payload.changes)

@router.get("/presets", response_model=List[Preset])
async def get_presets():
    return [
        Preset(name="Minimalist", description="Cut all luxury", changes={"Dining": -0.8, "Entertainment": -1.0}),
        Preset(name="Aggressive Saver", description="Save 50% of income", changes={"Dining": -0.5, "Shopping": -0.7}),
    ]

@router.post("/presets/{name}/apply", response_model=WhatIfResult)
async def apply_preset(name: str):
    presets = {
        "Minimalist": {"Dining": -0.8, "Entertainment": -1.0},
        "Aggressive Saver": {"Dining": -0.5, "Shopping": -0.7},
    }
    changes = presets.get(name, {})
    return FinancialEngine.simulate_what_if(changes)
