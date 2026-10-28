"""Request schemas (validated input). Responses are plain JSON structures documented in OpenAPI."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator

from .models import OrderSide, Role, Severity
from .services.compliance import RULE_TYPES


class LoginOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user: dict


class OrderIn(BaseModel):
    account: str = Field(min_length=1, max_length=32)
    symbol: str = Field(min_length=1, max_length=32)
    side: OrderSide
    qty: float = Field(gt=0, le=1e12)
    limit_px: float | None = Field(default=None, gt=0)
    override_reason: str | None = Field(default=None, max_length=500)


class PreTradeIn(BaseModel):
    account: str
    symbol: str
    side: OrderSide
    qty: float = Field(gt=0)


class RejectIn(BaseModel):
    reason: str = Field(min_length=3, max_length=500)


class RuleIn(BaseModel):
    code: str = Field(pattern=r"^[A-Z0-9][A-Z0-9\-_]{1,31}$")
    name: str = Field(min_length=3, max_length=200)
    category: Literal["REGULATORY", "MANDATE", "INTERNAL"] = "MANDATE"
    rule_type: str
    scope: Literal["GLOBAL", "ENTITY", "ACCOUNT"] = "GLOBAL"
    scope_ref: str | None = None
    params: dict = {}
    severity: Severity = Severity.HARD
    is_active: bool = True

    @field_validator("rule_type")
    @classmethod
    def known_type(cls, v: str) -> str:
        if v not in RULE_TYPES:
            raise ValueError(f"Unknown rule type; expected one of {sorted(RULE_TYPES)}")
        return v


class RuleUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=3, max_length=200)
    params: dict | None = None
    severity: Severity | None = None
    is_active: bool | None = None


class BreachAction(BaseModel):
    status: Literal["ACKNOWLEDGED", "RESOLVED"] | None = None
    note: str = Field(min_length=2, max_length=1000)


class ModelVersionIn(BaseModel):
    weights: dict[str, float]
    rationale: str = Field(min_length=3, max_length=2000)

    @field_validator("weights")
    @classmethod
    def sums_to_100(cls, w: dict[str, float]) -> dict[str, float]:
        if any(v < 0 for v in w.values()):
            raise ValueError("Weights must be non-negative")
        tot = sum(w.values())
        if abs(tot - 100) > 0.01:
            raise ValueError(f"Weights must sum to 100 (got {tot:.2f})")
        return w


class ModelIn(BaseModel):
    code: str = Field(pattern=r"^[A-Z0-9][A-Z0-9\-_]{1,31}$")
    name: str = Field(min_length=3, max_length=120)
    benchmark: str = ""
    tolerance_pct: float = Field(default=2.0, gt=0, le=25)
    weights: dict[str, float]
    rationale: str = "Initial version"


class RebalanceIn(BaseModel):
    accounts: list[str] = Field(min_length=1, max_length=500)
    mode: Literal["full", "band"] = "band"
    min_trade_value: float = Field(default=0, ge=0)


class OptimizeIn(BaseModel):
    symbols: list[str] = Field(min_length=2, max_length=60)
    objective: Literal["min_variance", "max_sharpe", "target_return", "risk_parity"] = "max_sharpe"
    min_weight: float = Field(default=0.0, ge=0, le=1)
    max_weight: float = Field(default=0.35, gt=0, le=1)
    rf: float = Field(default=0.04, ge=-0.05, le=0.2)
    target_return: float | None = None
    class_bounds: dict[str, tuple[float, float]] | None = None
    account: str | None = None  # if given: current weights + turnover penalty
    turnover_penalty: float = Field(default=0.0, ge=0, le=1)


class StressIn(BaseModel):
    accounts: list[str] = []
    equity_pct: float = Field(default=0, ge=-100, le=100)
    rates_bp: float = Field(default=0, ge=-1000, le=1000)
    spread_bp: float = Field(default=0, ge=-500, le=2000)
    fx_pct: float = Field(default=0, ge=-100, le=100)


class UserIn(BaseModel):
    username: str = Field(pattern=r"^[a-z0-9._-]{3,64}$")
    full_name: str = Field(min_length=2, max_length=120)
    email: str = Field(pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    role: Role
    password: str
    entities: list[str] = []


class UserUpdate(BaseModel):
    role: Role | None = None
    is_active: bool | None = None
    entities: list[str] | None = None
    password: str | None = None


class InstrumentPatch(BaseModel):
    rating: str | None = None
    esg_score: float | None = Field(default=None, ge=0, le=100)
    is_active: bool | None = None
    price: float | None = Field(default=None, gt=0)
