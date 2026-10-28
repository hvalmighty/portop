"""Order lifecycle (maker-checker), simulated execution, position and cash booking."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from ..audit import audit, snapshot
from ..models import (
    Account,
    Alert,
    AssetClass,
    CashBalance,
    Instrument,
    Order,
    OrderSide,
    OrderStatus,
    Position,
    Trade,
    User,
)
from .compliance import pre_trade_check

# Indicative execution cost (bps of notional) and transaction taxes, used for estimates and fees.
COST_BPS = {AssetClass.EQ: 15.0, AssetClass.FI: 5.0, AssetClass.DERIV: 1.0, AssetClass.FUND: 0.0, AssetClass.CASH: 0.0}
SELL_TAX_BPS = {("EQ", "PHP"): 60.0}  # e.g. Philippine stock transaction tax on equity sales
SETTLE_DAYS = {AssetClass.EQ: 2, AssetClass.FI: 1, AssetClass.FUND: 3, AssetClass.DERIV: 0, AssetClass.CASH: 0}


def add_business_days(d: date, n: int) -> date:
    while n > 0:
        d += timedelta(days=1)
        if d.weekday() < 5:
            n -= 1
    return d


def estimate_cost(inst: Instrument, side: OrderSide, qty: float, price: float | None = None) -> float:
    gross = abs(qty) * (price or inst.price) * inst.contract_size
    bps = COST_BPS.get(inst.asset_class, 0.0)
    if side == OrderSide.SELL:
        bps += SELL_TAX_BPS.get((inst.asset_class.value, inst.ccy), 0.0)
    return gross * bps / 10_000


def signed(side: OrderSide, qty: float) -> float:
    return qty if side == OrderSide.BUY else -qty


def create_order(
    db: Session, user: User, account: Account, inst: Instrument, side: OrderSide, qty: float,
    limit_px: float | None = None, source: str = "MANUAL", batch_id: str | None = None,
    override_reason: str | None = None, commit: bool = True,
) -> Order:
    if qty <= 0:
        raise HTTPException(422, "Quantity must be positive")
    if not inst.is_active:
        raise HTTPException(422, f"{inst.symbol} is not active")
    outcome = pre_trade_check(db, account, [(inst, signed(side, qty))])
    if outcome.status == "FAIL":
        failed = [r.message for r in outcome.results if not r.passed and r.severity == "HARD"]
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            {"message": "Order blocked by pre-trade compliance", "violations": failed, "compliance": outcome.as_dict()},
        )
    if outcome.status == "WARN" and any(not r.passed and r.severity == "SOFT" for r in outcome.results) and not override_reason:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            {"message": "Soft limit breached - an override reason is required", "compliance": outcome.as_dict(),
             "requires_override": True},
        )
    o = Order(
        account_id=account.id, instrument_id=inst.id, side=side, qty=qty, limit_px=limit_px,
        status=OrderStatus.PENDING_APPROVAL, source=source, batch_id=batch_id, compliance=outcome.as_dict(),
        override_reason=override_reason, est_cost=estimate_cost(inst, side, qty, limit_px), created_by=user.username,
    )
    db.add(o)
    db.flush()
    audit(db, user.username, "ORDER_CREATE", "order", o.id, after=snapshot(o))
    if commit:
        db.commit()
    return o


def _book_position(db: Session, account: Account, inst: Instrument, sqty: float, px: float) -> None:
    pos = db.query(Position).filter_by(account_id=account.id, instrument_id=inst.id).one_or_none()
    if pos is None:
        db.add(Position(account_id=account.id, instrument_id=inst.id, qty=sqty, avg_px=px))
        return
    old = pos.qty
    new = old + sqty
    if abs(new) < 1e-9:
        pos.qty = 0.0
    elif old == 0 or (old > 0) == (sqty > 0):
        pos.avg_px = (old * pos.avg_px + sqty * px) / new
        pos.qty = new
    elif (old > 0) != (new > 0):  # crossed through zero
        pos.qty, pos.avg_px = new, px
    else:  # partial reduction keeps cost basis
        pos.qty = new


def _book_cash(db: Session, account: Account, ccy: str, amount: float) -> None:
    cb = db.query(CashBalance).filter_by(account_id=account.id, ccy=ccy).one_or_none()
    if cb is None:
        db.add(CashBalance(account_id=account.id, ccy=ccy, amount=amount))
    else:
        cb.amount += amount


def execute(db: Session, order: Order) -> Trade:
    """Simulated execution at the current mark (a broker/EMS adapter replaces this in production)."""
    inst, acct = order.instrument, order.account
    px = inst.price
    if order.limit_px is not None:
        if (order.side == OrderSide.BUY and px > order.limit_px) or (order.side == OrderSide.SELL and px < order.limit_px):
            raise HTTPException(status.HTTP_409_CONFLICT, f"Market {px:.4f} outside limit {order.limit_px:.4f}")
    sq = signed(order.side, order.qty)
    gross = order.qty * px * inst.contract_size
    fees = estimate_cost(inst, order.side, order.qty, px)
    today = datetime.now(timezone.utc).date()
    t = Trade(
        order_id=order.id, account_id=acct.id, instrument_id=inst.id, side=order.side, qty=order.qty, price=px,
        gross=gross, fees=fees, trade_date=today,
        settle_date=add_business_days(today, SETTLE_DAYS.get(inst.asset_class, 2)),
    )
    db.add(t)
    _book_position(db, acct, inst, sq, px)
    if inst.asset_class != AssetClass.DERIV:
        _book_cash(db, acct, inst.ccy, -sq * px * inst.contract_size)
    _book_cash(db, acct, inst.ccy, -fees)
    order.status = OrderStatus.FILLED
    order.fill_px = px
    return t


def approve_order(db: Session, user: User, order: Order) -> Order:
    if order.status != OrderStatus.PENDING_APPROVAL:
        raise HTTPException(status.HTTP_409_CONFLICT, f"Order is {order.status.value}")
    if order.created_by == user.username:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Segregation of duties: the maker cannot approve their own order")
    before = snapshot(order)
    # re-check at approval: market or holdings may have moved since the order was entered
    outcome = pre_trade_check(db, order.account, [(order.instrument, signed(order.side, order.qty))])
    order.compliance = outcome.as_dict()
    if outcome.status == "FAIL":
        order.status = OrderStatus.REJECTED
        order.reject_reason = "Failed pre-trade compliance at approval"
        db.add(Alert(level="WARN", category="ORDER", message=f"Order #{order.id} auto-rejected at approval (compliance)",
                     account_code=order.account.code))
    else:
        order.approved_by = user.username
        order.status = OrderStatus.APPROVED
        execute(db, order)
    audit(db, user.username, "ORDER_APPROVE", "order", order.id, before, snapshot(order))
    db.commit()
    return order


def reject_order(db: Session, user: User, order: Order, reason: str) -> Order:
    if order.status != OrderStatus.PENDING_APPROVAL:
        raise HTTPException(status.HTTP_409_CONFLICT, f"Order is {order.status.value}")
    before = snapshot(order)
    order.status = OrderStatus.REJECTED
    order.reject_reason = reason
    order.approved_by = user.username
    audit(db, user.username, "ORDER_REJECT", "order", order.id, before, snapshot(order))
    db.commit()
    return order


def cancel_order(db: Session, user: User, order: Order) -> Order:
    if order.status != OrderStatus.PENDING_APPROVAL:
        raise HTTPException(status.HTTP_409_CONFLICT, f"Order is {order.status.value}")
    if order.created_by != user.username and user.role.value != "ADMIN":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only the maker or an administrator can cancel")
    before = snapshot(order)
    order.status = OrderStatus.CANCELLED
    audit(db, user.username, "ORDER_CANCEL", "order", order.id, before, snapshot(order))
    db.commit()
    return order
