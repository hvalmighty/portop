"""Drift detection against model portfolios and rebalancing proposal generation."""

from __future__ import annotations

import math

from sqlalchemy.orm import Session

from ..models import Account, AssetClass, Instrument, ModelPortfolio, ModelVersion, OrderSide
from .compliance import Snapshot, pre_trade_check
from .trading import estimate_cost, signed
from .valuation import Fx, market_value

LOT = {AssetClass.EQ: 100, AssetClass.FI: 10_000, AssetClass.FUND: 1, AssetClass.DERIV: 1}


def active_version(model: ModelPortfolio) -> ModelVersion | None:
    act = [v for v in model.versions if v.status == "ACTIVE"]
    return act[-1] if act else None


def drift(db: Session, snap: Snapshot, model: ModelPortfolio) -> dict:
    v = active_version(model)
    if v is None:
        return {"model": model.code, "version": None, "rows": [], "max_abs_drift": 0, "out_of_band": 0}
    nav = snap.nav
    fx = snap.fx
    cur: dict[str, float] = {}
    for h in snap.holdings.values():
        if abs(h.qty) > 1e-9 and h.inst.asset_class != AssetClass.DERIV:
            cur[h.inst.symbol] = fx.convert(market_value(h.inst, h.qty, h.avg_px), h.inst.ccy, snap.account.base_ccy) / nav * 100
    cur["CASH"] = snap.cash / nav * 100 if nav else 0
    targets = dict(v.weights)
    targets.setdefault("CASH", 0.0)
    rows = []
    for sym in sorted(set(cur) | set(targets)):
        c, t = cur.get(sym, 0.0), float(targets.get(sym, 0.0))
        d = c - t
        rows.append({"symbol": sym, "current_pct": c, "target_pct": t, "drift_pct": d,
                     "out_of_band": abs(d) > model.tolerance_pct})
    rows.sort(key=lambda r: -abs(r["drift_pct"]))
    return {
        "model": model.code, "version": v.version, "tolerance_pct": model.tolerance_pct, "nav": nav,
        "rows": rows, "max_abs_drift": max((abs(r["drift_pct"]) for r in rows), default=0),
        "out_of_band": sum(1 for r in rows if r["out_of_band"]),
    }


def propose(db: Session, snap: Snapshot, model: ModelPortfolio, mode: str = "full", min_trade_value: float = 0.0) -> dict:
    """mode='full' trades every line back to target; mode='band' only lines outside tolerance."""
    dr = drift(db, snap, model)
    fx: Fx = snap.fx
    nav = snap.nav
    insts = {i.symbol: i for i in db.query(Instrument).filter(Instrument.symbol.in_([r["symbol"] for r in dr["rows"]]))}
    lines, trades = [], []
    for r in dr["rows"]:
        if r["symbol"] == "CASH" or (mode == "band" and not r["out_of_band"]):
            continue
        inst = insts.get(r["symbol"])
        if inst is None:
            continue
        value_base = -r["drift_pct"] / 100 * nav
        value_local = fx.convert(value_base, snap.account.base_ccy, inst.ccy)
        unit = inst.price * inst.contract_size
        lot = LOT.get(inst.asset_class, 1)
        qty = math.floor(abs(value_local) / unit / lot) * lot if unit > 0 else 0
        if qty <= 0 or abs(value_base) < min_trade_value:
            continue
        side = OrderSide.BUY if value_local > 0 else OrderSide.SELL
        held = snap.holdings.get(inst.id)
        if side == OrderSide.SELL and held is not None:
            qty = min(qty, max(held.qty, 0))  # never flip to short when rebalancing
        if qty <= 0:
            continue
        cost = estimate_cost(inst, side, qty)
        lines.append({"symbol": inst.symbol, "instrument_id": inst.id, "side": side.value, "qty": qty,
                      "price": inst.price, "value_base": fx.convert(qty * unit, inst.ccy, snap.account.base_ccy),
                      "est_cost": cost, "drift_pct": r["drift_pct"]})
        trades.append((inst, signed(side, qty)))
    # sells first so cash is available for buys
    lines.sort(key=lambda x: x["side"] != "SELL")
    comp = pre_trade_check(db, snap.account, trades).as_dict() if trades else {"status": "PASS", "results": []}
    return {
        "account": snap.account.code, "model": model.code, "version": dr["version"], "mode": mode,
        "lines": lines, "turnover_base": sum(ln["value_base"] for ln in lines),
        "est_cost_total": sum(ln["est_cost"] for ln in lines), "compliance": comp, "drift": dr,
    }


def accounts_for_model(db: Session, model_id: int) -> list[Account]:
    return db.query(Account).filter(Account.model_id == model_id, Account.is_active.is_(True)).all()
