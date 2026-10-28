from fastapi import APIRouter, Depends, Query
from sqlalchemy import or_
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import CashBalance, Instrument, PriceHistory, User
from ..security import allowed_entities, require
from ..services.compliance import load_snapshot
from ..services.rebalance import drift
from ..services.valuation import Fx, load_accounts, reporting_ccy, to_dict, value_accounts
from .common import check_entity, get_account, get_instrument

router = APIRouter(tags=["portfolio"])


@router.get("/portfolio/overview")
def overview(
    entity: str | None = None,
    accounts: list[str] | None = Query(default=None),
    asset_class: str | None = None,
    user: User = Depends(require("portfolio:read")),
    db: Session = Depends(get_db),
):
    """Firm-wide cross-asset positions and exposure, in the entity's reporting currency."""
    check_entity(user, entity)
    rep = reporting_ccy(db, entity)
    accts = load_accounts(db, entity, allowed_entities(user), accounts)
    summaries, views = value_accounts(db, accts, rep)
    if asset_class:
        views = [v for v in views if v.asset_class == asset_class]
    views.sort(key=lambda v: -abs(v.exposure_rep))
    return {
        "reporting_ccy": rep,
        "totals": {
            "positions": len(views),
            "gross": sum(abs(v.exposure_rep) for v in views),
            "net": sum(v.exposure_rep for v in views),
            "mtm_pnl": sum(v.mtm_pnl_rep for v in views),
            "day_pnl": sum(v.day_pnl_rep for v in views),
            "aum": sum(s.aum for s in summaries),
            "nav": sum(s.nav for s in summaries),
        },
        "accounts": [to_dict(s) for s in summaries],
        "positions": [to_dict(v) for v in views],
    }


@router.get("/portfolio/accounts/{code}")
def account_detail(code: str, user: User = Depends(require("portfolio:read")), db: Session = Depends(get_db)):
    a = get_account(db, user, code)
    fx = Fx.load(db)
    summaries, views = value_accounts(db, [a], a.base_ccy, fx)
    cash = db.query(CashBalance).filter(CashBalance.account_id == a.id).all()
    out = {
        "account": {
            "code": a.code, "name": a.name, "entity": a.entity_code, "base_ccy": a.base_ccy, "mandate": a.mandate,
            "risk_profile": a.risk_profile, "tax_status": a.tax_status, "restrictions": a.restrictions,
            "model": a.model.code if a.model else None,
        },
        "summary": to_dict(summaries[0]),
        "positions": [to_dict(v) for v in sorted(views, key=lambda v: -abs(v.exposure_rep))],
        "cash": [{"ccy": c.ccy, "amount": c.amount} for c in cash],
    }
    if a.model:
        out["drift"] = drift(db, load_snapshot(db, a, fx), a.model)
    return out


@router.get("/instruments")
def instruments(
    q: str | None = None, asset_class: str | None = None, limit: int = Query(200, le=1000),
    _: User = Depends(require("portfolio:read")), db: Session = Depends(get_db),
):
    query = db.query(Instrument)
    if q:
        like = f"%{q}%"
        query = query.filter(or_(Instrument.symbol.ilike(like), Instrument.name.ilike(like), Instrument.issuer.ilike(like)))
    if asset_class:
        query = query.filter(Instrument.asset_class == asset_class)
    return [
        {
            "id": i.id, "symbol": i.symbol, "name": i.name, "asset_class": i.asset_class.value, "type": i.inst_type,
            "ccy": i.ccy, "issuer": i.issuer, "sector": i.sector, "country": i.country, "rating": i.rating,
            "coupon": i.coupon, "maturity": i.maturity.isoformat() if i.maturity else None, "duration": i.duration,
            "price": i.price, "prev_close": i.prev_close, "chg_pct": (i.price / i.prev_close - 1) * 100 if i.prev_close else 0,
            "esg_score": i.esg_score, "is_active": i.is_active,
        }
        for i in query.order_by(Instrument.asset_class, Instrument.symbol).limit(limit)
    ]


@router.get("/market/history/{symbol}")
def history(symbol: str, days: int = Query(250, ge=5, le=2000), _: User = Depends(require("portfolio:read")),
            db: Session = Depends(get_db)):
    i = get_instrument(db, symbol)
    rows = (db.query(PriceHistory).filter(PriceHistory.instrument_id == i.id)
            .order_by(PriceHistory.d.desc()).limit(days).all())
    return {"symbol": symbol, "points": [{"d": r.d.isoformat(), "close": r.close} for r in reversed(rows)]}
