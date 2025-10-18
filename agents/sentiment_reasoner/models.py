# models.py
from typing import Optional, Dict
from uagents import Model

class ReasonRequest(Model):
    peg_payload_json: str
    liq_quote: Optional[float] = None
    sentiment_json: Optional[str] = None
    current_weights: Optional[Dict[str, float]] = None

class ReasonResponse(Model):
    ok: bool
    target_weights: Optional[Dict[str, float]] = None  # {"USDC": x, "USDT": y}
    alert_level: Optional[str] = None                  # "GREEN"|"YELLOW"|"RED"
    rationale: Optional[str] = None
    error: Optional[str] = None