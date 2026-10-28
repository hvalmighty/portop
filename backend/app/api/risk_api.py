import numpy as np
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..audit import audit
from ..db import get_db
from ..models import AssetClass, Instrument, User
from ..schemas import OptimizeIn, StressIn
from ..security import allowed_entities, require
from ..services.compliance import load_snapshot
from ..services.optimizer import OptimizationError, OptInputs, frontier, optimise, stats
from ..services.risk import SCENARIOS, account_risk, instrument_stats, scenario_pnl, stress
from ..services.valuation import Fx, load_accounts, market_value
from .common import check_entity, get_account

router = APIRouter(tags=["risk"])


@router.get("/risk/summary")
def risk_summary(entity: str | None = None, user: User = Depends(require("risk:read")), db: Session = Depends(get_db)):
    """Enterprise view: key risk metrics for every account (account base currency)."""
    check_entity(user, entity)
    fx = Fx.load(db)
    rows = []
    for a in load_accounts(db, entity, allowed_entities(user)):
        r = account_risk(db, load_snapshot(db, a, fx))
        rows.append({
            "account": a.code, "name": a.name, "entity": a.entity_code, "ccy": a.base_ccy, "nav": r["nav"],
            "gross": r["gross"], "leverage_pct": r["leverage_pct"],
            "var95": r["market"].get("hist_var_95", 0), "var99": r["market"].get("hist_var_99", 0),
            "es99": r["market"].get("es_99", 0), "vol_pct": r["market"].get("vol_ann_pct", 0),
            "dv01": r["rates"]["dv01"], "duration": r["rates"]["duration"], "hhi": r["concentration"]["hhi"],
            "top_weight": r["concentration"]["top5"][0]["pct"] if r["concentration"]["top5"] else 0,
            "illiquid_pct": next((b["pct"] for b in r["liquidity"] if b["bucket"] == ">20d"), 0),
        })
    return {"accounts": rows, "scenarios": SCENARIOS}


@router.get("/risk/accounts/{code}")
def risk_account(code: str, user: User = Depends(require("risk:read")), db: Session = Depends(get_db)):
    a = get_account(db, user, code)
    snap = load_snapshot(db, a, Fx.load(db))
    r = account_risk(db, snap)
    r["scenarios"] = [scenario_pnl(snap, k) for k in SCENARIOS]
    return r


@router.post("/risk/stress")
def run_stress(body: StressIn, user: User = Depends(require("risk:read")), db: Session = Depends(get_db)):
    fx = Fx.load(db)
    codes = body.accounts or [a.code for a in load_accounts(db, None, allowed_entities(user))]
    return {"results": [stress(load_snapshot(db, get_account(db, user, c), fx), body.equity_pct, body.rates_bp,
                               body.spread_bp, body.fx_pct) for c in codes]}


@router.post("/optimize")
def run_optimizer(body: OptimizeIn, user: User = Depends(require("optimizer:run")), db: Session = Depends(get_db)):
    insts = db.query(Instrument).filter(Instrument.symbol.in_(body.symbols)).all()
    if any(i.asset_class == AssetClass.DERIV for i in insts):
        raise HTTPException(422, "Derivatives are handled as overlays and cannot be optimised as weights")
    kept, mu, cov = instrument_stats(db, insts)
    current = None
    if body.account:
        a = get_account(db, user, body.account)
        snap = load_snapshot(db, a, Fx.load(db))
        nav = snap.nav or 1
        held = {h.inst.symbol: snap.fx.convert(market_value(h.inst, h.qty, h.avg_px), h.inst.ccy, a.base_ccy) / nav
                for h in snap.holdings.values()}
        current = np.array([held.get(i.symbol, 0.0) for i in kept])
        s = current.sum()
        current = current / s if s > 0 else None
    inp = OptInputs(
        symbols=[i.symbol for i in kept], asset_classes=[i.asset_class.value for i in kept], mu=mu, cov=cov,
        min_w=body.min_weight, max_w=body.max_weight, rf=body.rf,
        class_bounds={k: (v[0] / 100, v[1] / 100) for k, v in (body.class_bounds or {}).items()},
        target_return=body.target_return, current=current, turnover_penalty=body.turnover_penalty,
    )
    try:
        w = optimise(inp, body.objective)
    except OptimizationError as exc:
        raise HTTPException(422, str(exc)) from exc
    st = stats(w, mu, cov, body.rf)
    eq = np.full(len(kept), 1 / len(kept))
    audit(db, user.username, "OPTIMIZE", "optimizer", body.objective,
          after={"symbols": inp.symbols, "weights": [round(x, 6) for x in w.tolist()]})
    db.commit()
    return {
        "objective": body.objective,
        "dropped": sorted(set(body.symbols) - set(inp.symbols)),
        "weights": [
            {"symbol": s, "asset_class": ac, "weight": float(x), "exp_return": float(m), "vol": float(np.sqrt(cov[k, k])),
             "risk_contrib": float(st["risk_contrib"][k]), "current": float(current[k]) if current is not None else None}
            for k, (s, ac, x, m) in enumerate(zip(inp.symbols, inp.asset_classes, w, mu))
        ],
        "portfolio": {k: v for k, v in st.items() if k != "risk_contrib"},
        "equal_weight": {k: v for k, v in stats(eq, mu, cov, body.rf).items() if k != "risk_contrib"},
        "current": ({k: v for k, v in stats(current, mu, cov, body.rf).items() if k != "risk_contrib"}
                    if current is not None else None),
        "frontier": frontier(inp),
        "assets": [{"symbol": s, "exp_return": float(m), "vol": float(np.sqrt(cov[k, k]))}
                   for k, (s, m) in enumerate(zip(inp.symbols, mu))],
    }
