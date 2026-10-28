from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session, joinedload

from ..db import get_db
from ..models import Account, Order, OrderStatus, User
from ..schemas import OrderIn, PreTradeIn, RejectIn
from ..security import allowed_entities, require
from ..services.compliance import pre_trade_check
from ..services.trading import approve_order, cancel_order, create_order, estimate_cost, reject_order, signed
from .common import get_account, get_instrument

router = APIRouter(prefix="/orders", tags=["orders"])


def order_out(o: Order) -> dict:
    return {
        "id": o.id, "account": o.account.code, "symbol": o.instrument.symbol, "name": o.instrument.name,
        "asset_class": o.instrument.asset_class.value, "ccy": o.instrument.ccy, "side": o.side.value, "qty": o.qty,
        "limit_px": o.limit_px, "mark": o.instrument.price, "status": o.status.value, "source": o.source,
        "batch_id": o.batch_id, "compliance_status": (o.compliance or {}).get("status"), "compliance": o.compliance,
        "override_reason": o.override_reason, "est_cost": o.est_cost, "created_by": o.created_by,
        "approved_by": o.approved_by, "reject_reason": o.reject_reason, "fill_px": o.fill_px,
        "notional": o.qty * (o.fill_px or o.instrument.price) * o.instrument.contract_size,
        "created_at": o.created_at.isoformat(), "updated_at": o.updated_at.isoformat() if o.updated_at else None,
    }


def _load(db: Session, oid: int, user: User) -> Order:
    o = db.get(Order, oid, options=[joinedload(Order.account), joinedload(Order.instrument)])
    if o is None:
        raise HTTPException(404, "Order not found")
    get_account(db, user, o.account.code)  # entitlement check
    return o


@router.get("")
def list_orders(
    status: OrderStatus | None = None, account: str | None = None, limit: int = Query(300, le=2000),
    user: User = Depends(require("portfolio:read")), db: Session = Depends(get_db),
):
    q = db.query(Order).options(joinedload(Order.account), joinedload(Order.instrument)).join(Account)
    allowed = allowed_entities(user)
    if allowed is not None:
        q = q.filter(Account.entity_code.in_(allowed))
    if status:
        q = q.filter(Order.status == status)
    if account:
        q = q.filter(Account.code == account)
    return [order_out(o) for o in q.order_by(Order.id.desc()).limit(limit)]


@router.post("/pretrade")
def pretrade(body: PreTradeIn, user: User = Depends(require("portfolio:read")), db: Session = Depends(get_db)):
    """What-if compliance check without creating an order."""
    a = get_account(db, user, body.account)
    i = get_instrument(db, body.symbol)
    out = pre_trade_check(db, a, [(i, signed(body.side, body.qty))]).as_dict()
    out["est_cost"] = estimate_cost(i, body.side, body.qty)
    out["notional"] = body.qty * i.price * i.contract_size
    return out


@router.post("", status_code=201)
def create(body: OrderIn, user: User = Depends(require("order:create")), db: Session = Depends(get_db)):
    a = get_account(db, user, body.account)
    i = get_instrument(db, body.symbol)
    o = create_order(db, user, a, i, body.side, body.qty, body.limit_px, override_reason=body.override_reason)
    return order_out(_load(db, o.id, user))


@router.post("/{oid}/approve")
def approve(oid: int, user: User = Depends(require("order:approve")), db: Session = Depends(get_db)):
    return order_out(approve_order(db, user, _load(db, oid, user)))


@router.post("/{oid}/reject")
def reject(oid: int, body: RejectIn, user: User = Depends(require("order:approve")), db: Session = Depends(get_db)):
    return order_out(reject_order(db, user, _load(db, oid, user), body.reason))


@router.post("/{oid}/cancel")
def cancel(oid: int, user: User = Depends(require("order:cancel")), db: Session = Depends(get_db)):
    return order_out(cancel_order(db, user, _load(db, oid, user)))
