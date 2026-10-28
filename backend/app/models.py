"""ORM models for the mPower investment management platform."""

from __future__ import annotations

import enum
from datetime import date, datetime, timezone

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Role(str, enum.Enum):
    ADMIN = "ADMIN"
    PM = "PM"
    TRADER = "TRADER"
    COMPLIANCE = "COMPLIANCE"
    RISK = "RISK"
    OPS = "OPS"
    VIEWER = "VIEWER"


class AssetClass(str, enum.Enum):
    EQ = "EQ"
    FI = "FI"
    DERIV = "DERIV"
    FUND = "FUND"
    CASH = "CASH"


class OrderSide(str, enum.Enum):
    BUY = "BUY"
    SELL = "SELL"


class OrderStatus(str, enum.Enum):
    PENDING_APPROVAL = "PENDING_APPROVAL"
    APPROVED = "APPROVED"
    FILLED = "FILLED"
    REJECTED = "REJECTED"
    CANCELLED = "CANCELLED"


class Severity(str, enum.Enum):
    HARD = "HARD"
    SOFT = "SOFT"


class BreachStatus(str, enum.Enum):
    OPEN = "OPEN"
    ACKNOWLEDGED = "ACKNOWLEDGED"
    RESOLVED = "RESOLVED"


class Entity(Base):
    """Legal entity / booking centre (e.g. PH, SG, US)."""

    __tablename__ = "entities"
    code: Mapped[str] = mapped_column(String(8), primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    reporting_ccy: Mapped[str] = mapped_column(String(3))


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    full_name: Mapped[str] = mapped_column(String(120))
    email: Mapped[str] = mapped_column(String(200))
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[Role] = mapped_column(Enum(Role, native_enum=False))
    entities: Mapped[list] = mapped_column(JSON, default=list)  # entity codes user may see; [] = all
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    failed_logins: Mapped[int] = mapped_column(Integer, default=0)
    last_login: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Instrument(Base):
    __tablename__ = "instruments"
    id: Mapped[int] = mapped_column(primary_key=True)
    symbol: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(200))
    asset_class: Mapped[AssetClass] = mapped_column(Enum(AssetClass, native_enum=False))
    inst_type: Mapped[str] = mapped_column(String(32))  # cash_equity, govt_bond, corporate_bond, otc_swap, fx_forward, future, etf
    ccy: Mapped[str] = mapped_column(String(3))
    issuer: Mapped[str] = mapped_column(String(120))
    sector: Mapped[str] = mapped_column(String(64), default="")
    country: Mapped[str] = mapped_column(String(2), default="")
    rating: Mapped[str | None] = mapped_column(String(8))
    coupon: Mapped[float | None] = mapped_column(Float)
    maturity: Mapped[date | None] = mapped_column(Date)
    duration: Mapped[float | None] = mapped_column(Float)  # modified duration (years) for rate-sensitive
    contract_size: Mapped[float] = mapped_column(Float, default=1.0)  # price x qty x size = notional
    adv: Mapped[float] = mapped_column(Float, default=1_000_000)  # average daily volume (units)
    esg_score: Mapped[float | None] = mapped_column(Float)
    price: Mapped[float] = mapped_column(Float)
    prev_close: Mapped[float] = mapped_column(Float)
    vol: Mapped[float] = mapped_column(Float, default=0.2)  # annualised vol used by the simulator
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class PriceHistory(Base):
    __tablename__ = "price_history"
    __table_args__ = (UniqueConstraint("instrument_id", "d"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    instrument_id: Mapped[int] = mapped_column(ForeignKey("instruments.id", ondelete="CASCADE"), index=True)
    d: Mapped[date] = mapped_column(Date)
    close: Mapped[float] = mapped_column(Float)


class FxRate(Base):
    """Units of quote currency per 1 unit of base (ccy -> USD pivot)."""

    __tablename__ = "fx_rates"
    ccy: Mapped[str] = mapped_column(String(3), primary_key=True)
    usd_per_unit: Mapped[float] = mapped_column(Float)


class ModelPortfolio(Base):
    __tablename__ = "model_portfolios"
    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(32), unique=True)
    name: Mapped[str] = mapped_column(String(120))
    description: Mapped[str] = mapped_column(Text, default="")
    benchmark: Mapped[str] = mapped_column(String(120), default="")
    tolerance_pct: Mapped[float] = mapped_column(Float, default=2.0)  # drift band, % points
    versions: Mapped[list[ModelVersion]] = relationship(
        back_populates="model", order_by="ModelVersion.version", cascade="all, delete-orphan"
    )


class ModelVersion(Base):
    __tablename__ = "model_versions"
    __table_args__ = (UniqueConstraint("model_id", "version"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    model_id: Mapped[int] = mapped_column(ForeignKey("model_portfolios.id", ondelete="CASCADE"))
    version: Mapped[int] = mapped_column(Integer)
    weights: Mapped[dict] = mapped_column(JSON)  # {symbol: weight_pct}; "CASH" allowed
    status: Mapped[str] = mapped_column(String(16), default="DRAFT")  # DRAFT / ACTIVE / RETIRED
    rationale: Mapped[str] = mapped_column(Text, default="")
    created_by: Mapped[str] = mapped_column(String(64))
    approved_by: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    effective_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    model: Mapped[ModelPortfolio] = relationship(back_populates="versions")


class Account(Base):
    __tablename__ = "accounts"
    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(200))
    entity_code: Mapped[str] = mapped_column(ForeignKey("entities.code"))
    base_ccy: Mapped[str] = mapped_column(String(3))
    mandate: Mapped[str] = mapped_column(String(64), default="Discretionary")
    aum: Mapped[float] = mapped_column(Float)  # mandate size in base ccy
    risk_profile: Mapped[str] = mapped_column(String(32), default="Moderate")
    tax_status: Mapped[str] = mapped_column(String(16), default="TAXABLE")
    model_id: Mapped[int | None] = mapped_column(ForeignKey("model_portfolios.id"))
    restrictions: Mapped[list] = mapped_column(JSON, default=list)  # client-specific restricted symbols
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    model: Mapped[ModelPortfolio | None] = relationship()


class Position(Base):
    __tablename__ = "positions"
    __table_args__ = (UniqueConstraint("account_id", "instrument_id"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id", ondelete="CASCADE"), index=True)
    instrument_id: Mapped[int] = mapped_column(ForeignKey("instruments.id"))
    qty: Mapped[float] = mapped_column(Float)
    avg_px: Mapped[float] = mapped_column(Float)
    account: Mapped[Account] = relationship()
    instrument: Mapped[Instrument] = relationship()


class CashBalance(Base):
    __tablename__ = "cash_balances"
    __table_args__ = (UniqueConstraint("account_id", "ccy"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id", ondelete="CASCADE"), index=True)
    ccy: Mapped[str] = mapped_column(String(3))
    amount: Mapped[float] = mapped_column(Float, default=0.0)


class Order(Base):
    __tablename__ = "orders"
    id: Mapped[int] = mapped_column(primary_key=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id"), index=True)
    instrument_id: Mapped[int] = mapped_column(ForeignKey("instruments.id"))
    side: Mapped[OrderSide] = mapped_column(Enum(OrderSide, native_enum=False))
    qty: Mapped[float] = mapped_column(Float)
    limit_px: Mapped[float | None] = mapped_column(Float)
    status: Mapped[OrderStatus] = mapped_column(Enum(OrderStatus, native_enum=False), index=True)
    source: Mapped[str] = mapped_column(String(32), default="MANUAL")  # MANUAL / REBALANCE / OPTIMIZER
    batch_id: Mapped[str | None] = mapped_column(String(40), index=True)
    compliance: Mapped[dict] = mapped_column(JSON, default=dict)
    override_reason: Mapped[str | None] = mapped_column(Text)
    est_cost: Mapped[float] = mapped_column(Float, default=0.0)
    created_by: Mapped[str] = mapped_column(String(64))
    approved_by: Mapped[str | None] = mapped_column(String(64))
    reject_reason: Mapped[str | None] = mapped_column(Text)
    fill_px: Mapped[float | None] = mapped_column(Float)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
    account: Mapped[Account] = relationship()
    instrument: Mapped[Instrument] = relationship()


class Trade(Base):
    __tablename__ = "trades"
    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int | None] = mapped_column(ForeignKey("orders.id"))
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id"), index=True)
    instrument_id: Mapped[int] = mapped_column(ForeignKey("instruments.id"))
    side: Mapped[OrderSide] = mapped_column(Enum(OrderSide, native_enum=False))
    qty: Mapped[float] = mapped_column(Float)
    price: Mapped[float] = mapped_column(Float)
    gross: Mapped[float] = mapped_column(Float)
    fees: Mapped[float] = mapped_column(Float, default=0.0)
    trade_date: Mapped[date] = mapped_column(Date)
    settle_date: Mapped[date] = mapped_column(Date)
    settle_status: Mapped[str] = mapped_column(String(16), default="PENDING")  # PENDING / SETTLED / FAILED
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    account: Mapped[Account] = relationship()
    instrument: Mapped[Instrument] = relationship()


class ComplianceRule(Base):
    __tablename__ = "compliance_rules"
    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(32), unique=True)
    name: Mapped[str] = mapped_column(String(200))
    category: Mapped[str] = mapped_column(String(16), default="MANDATE")  # REGULATORY / MANDATE / INTERNAL
    rule_type: Mapped[str] = mapped_column(String(40))
    scope: Mapped[str] = mapped_column(String(16), default="GLOBAL")  # GLOBAL / ENTITY / ACCOUNT
    scope_ref: Mapped[str | None] = mapped_column(String(32))
    params: Mapped[dict] = mapped_column(JSON, default=dict)
    severity: Mapped[Severity] = mapped_column(Enum(Severity, native_enum=False), default=Severity.HARD)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    updated_by: Mapped[str] = mapped_column(String(64), default="system")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class RuleVersion(Base):
    """Immutable history of every rule definition (for re-running historical checks and audit)."""

    __tablename__ = "rule_versions"
    id: Mapped[int] = mapped_column(primary_key=True)
    rule_id: Mapped[int] = mapped_column(ForeignKey("compliance_rules.id", ondelete="CASCADE"), index=True)
    version: Mapped[int] = mapped_column(Integer)
    snapshot: Mapped[dict] = mapped_column(JSON)
    changed_by: Mapped[str] = mapped_column(String(64))
    changed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Breach(Base):
    __tablename__ = "breaches"
    id: Mapped[int] = mapped_column(primary_key=True)
    rule_id: Mapped[int] = mapped_column(ForeignKey("compliance_rules.id"), index=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id"), index=True)
    kind: Mapped[str] = mapped_column(String(8))  # ACTIVE / PASSIVE
    subject: Mapped[str] = mapped_column(String(64), default="")
    observed: Mapped[float] = mapped_column(Float)
    limit: Mapped[float] = mapped_column(Float)
    message: Mapped[str] = mapped_column(Text)
    status: Mapped[BreachStatus] = mapped_column(Enum(BreachStatus, native_enum=False), default=BreachStatus.OPEN)
    detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    notes: Mapped[list] = mapped_column(JSON, default=list)
    rule: Mapped[ComplianceRule] = relationship()
    account: Mapped[Account] = relationship()


class Alert(Base):
    __tablename__ = "alerts"
    id: Mapped[int] = mapped_column(primary_key=True)
    level: Mapped[str] = mapped_column(String(8))  # INFO / WARN / CRIT
    category: Mapped[str] = mapped_column(String(32))
    message: Mapped[str] = mapped_column(Text)
    account_code: Mapped[str | None] = mapped_column(String(32))
    is_read: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)


class AuditLog(Base):
    __tablename__ = "audit_log"
    id: Mapped[int] = mapped_column(primary_key=True)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    username: Mapped[str] = mapped_column(String(64), index=True)
    action: Mapped[str] = mapped_column(String(64), index=True)
    object_type: Mapped[str] = mapped_column(String(64))
    object_id: Mapped[str] = mapped_column(String(64))
    before: Mapped[dict | None] = mapped_column(JSON)
    after: Mapped[dict | None] = mapped_column(JSON)
    request_id: Mapped[str | None] = mapped_column(String(40))
    ip: Mapped[str | None] = mapped_column(String(64))
