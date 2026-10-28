"""Market, rate, liquidity and concentration risk plus scenario stress testing."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

import numpy as np
from sqlalchemy.orm import Session

from ..models import AssetClass, Instrument, PriceHistory
from .compliance import Holding, Snapshot

Z = {95: 1.6448536, 99: 2.3263479}

SCENARIOS: dict[str, dict] = {
    "GFC_2008": {"label": "Global Financial Crisis 2008", "equity_pct": -40, "rates_bp": -150, "spread_bp": 300, "fx_pct": -10},
    "TAPER_2013": {"label": "Taper Tantrum 2013", "equity_pct": -10, "rates_bp": 100, "spread_bp": 50, "fx_pct": -5},
    "COVID_2020": {"label": "COVID-19 Drawdown 2020", "equity_pct": -30, "rates_bp": -100, "spread_bp": 200, "fx_pct": -5},
    "RATES_2022": {"label": "Global Rate Shock 2022", "equity_pct": -20, "rates_bp": 250, "spread_bp": 100, "fx_pct": -8},
    "RATES_UP_100": {"label": "Parallel rates +100bp", "equity_pct": 0, "rates_bp": 100, "spread_bp": 0, "fx_pct": 0},
    "EQ_DOWN_15": {"label": "Equities -15%", "equity_pct": -15, "rates_bp": 0, "spread_bp": 0, "fx_pct": 0},
}


def returns_matrix(db: Session, inst_ids: list[int], lookback: int = 500) -> tuple[list[int], np.ndarray]:
    """Aligned daily simple returns, shape (T, N). Instruments without history are dropped."""
    if not inst_ids:
        return [], np.zeros((0, 0))
    rows = (
        db.query(PriceHistory.instrument_id, PriceHistory.d, PriceHistory.close)
        .filter(PriceHistory.instrument_id.in_(inst_ids))
        .order_by(PriceHistory.d)
        .all()
    )
    series: dict[int, dict] = defaultdict(dict)
    for iid, d, c in rows:
        series[iid][d] = c
    ids = [i for i in inst_ids if len(series.get(i, {})) > 30]
    if not ids:
        return [], np.zeros((0, 0))
    dates = sorted(set.intersection(*(set(series[i]) for i in ids)))[-(lookback + 1):]
    px = np.array([[series[i][d] for i in ids] for d in dates], dtype=float)
    rets = px[1:] / px[:-1] - 1.0
    return ids, rets


@dataclass
class Exposures:
    rows: list[tuple[Holding, float]]  # holding, base-ccy signed exposure


def _exposures(snap: Snapshot) -> Exposures:
    return Exposures([(h, snap.exp(h)) for h in snap.holdings.values() if abs(h.qty) > 1e-9])


def account_risk(db: Session, snap: Snapshot) -> dict:
    ex = _exposures(snap)
    nav = snap.nav
    gross = sum(abs(e) for _, e in ex.rows)
    # ---- historical & parametric VaR on exposure-weighted P&L
    ids, rets = returns_matrix(db, [h.inst.id for h, _ in ex.rows])
    exp_vec = np.array([dict((h.inst.id, e) for h, e in ex.rows)[i] for i in ids]) if ids else np.zeros(0)
    var = {}
    if ids and rets.size:
        pnl = rets @ exp_vec
        for cl in (95, 99):
            var[f"hist_var_{cl}"] = float(-np.percentile(pnl, 100 - cl))
            tail = pnl[pnl <= np.percentile(pnl, 100 - cl)]
            var[f"es_{cl}"] = float(-tail.mean()) if tail.size else 0.0
            var[f"param_var_{cl}"] = float(Z[cl] * pnl.std(ddof=1))
        var["vol_ann_pct"] = float(pnl.std(ddof=1) * np.sqrt(252) / nav * 100) if nav else 0.0
        var["observations"] = int(len(pnl))
    # ---- rates
    rate_rows = [(h, e) for h, e in ex.rows if h.inst.duration is not None]
    dv01 = sum(e * h.inst.duration * 1e-4 for h, e in rate_rows)
    fi_exp = sum(abs(e) for h, e in rate_rows if h.inst.asset_class == AssetClass.FI)
    port_dur = (dv01 / 1e-4) / nav if nav else 0.0
    # ---- concentration
    weights = sorted(((h.inst.symbol, abs(e) / nav * 100 if nav else 0) for h, e in ex.rows), key=lambda x: -x[1])
    hhi = sum((abs(e) / gross) ** 2 for _, e in ex.rows) * 10_000 if gross else 0.0
    by_issuer: dict[str, float] = defaultdict(float)
    by_sector: dict[str, float] = defaultdict(float)
    by_rating: dict[str, float] = defaultdict(float)
    by_ccy: dict[str, float] = defaultdict(float)
    for h, e in ex.rows:
        if h.inst.asset_class != AssetClass.DERIV:
            by_issuer[h.inst.issuer] += abs(e)
            by_sector[h.inst.sector or "Unclassified"] += abs(e)
        if h.inst.asset_class == AssetClass.FI:
            by_rating[h.inst.rating or "NR"] += abs(e)
        by_ccy[h.inst.ccy] += e
    # ---- liquidity (25% participation of ADV)
    buckets = {"<1d": 0.0, "1-5d": 0.0, "5-20d": 0.0, ">20d": 0.0}
    for h, e in ex.rows:
        days = abs(h.qty) / max(h.inst.adv * 0.25, 1)
        k = "<1d" if days < 1 else "1-5d" if days < 5 else "5-20d" if days < 20 else ">20d"
        buckets[k] += abs(e)
    credit = sum(abs(e) for h, e in ex.rows if h.inst.inst_type == "corporate_bond")

    def top(d: dict, n: int = 8):
        return [{"name": k, "exposure": v, "pct": v / nav * 100 if nav else 0} for k, v in
                sorted(d.items(), key=lambda x: -abs(x[1]))[:n]]

    return {
        "account": snap.account.code,
        "base_ccy": snap.account.base_ccy,
        "nav": nav,
        "gross": gross,
        "leverage_pct": gross / nav * 100 if nav else 0,
        "market": var,
        "rates": {"dv01": dv01, "duration": port_dur, "fi_exposure": fi_exp},
        "credit": {"corporate_exposure": credit, "by_rating": top(by_rating)},
        "concentration": {"top5": [{"symbol": s, "pct": w} for s, w in weights[:5]], "hhi": hhi,
                          "by_issuer": top(by_issuer), "by_sector": top(by_sector)},
        "fx": top(by_ccy),
        "liquidity": [{"bucket": k, "exposure": v, "pct": v / gross * 100 if gross else 0} for k, v in buckets.items()],
    }


def stress(snap: Snapshot, equity_pct: float = 0, rates_bp: float = 0, spread_bp: float = 0, fx_pct: float = 0) -> dict:
    """First-order shock P&L in account base currency."""
    lines = []
    tot = {"equity": 0.0, "rates": 0.0, "spread": 0.0, "fx": 0.0}
    for h, e in _exposures(snap).rows:
        eq = e * equity_pct / 100 if h.inst.asset_class in (AssetClass.EQ, AssetClass.FUND) else 0.0
        rt = -e * (h.inst.duration or 0) * rates_bp / 10_000
        sp = -e * (h.inst.duration or 0) * spread_bp / 10_000 if h.inst.inst_type == "corporate_bond" else 0.0
        fx = e * fx_pct / 100 if (h.inst.ccy != snap.account.base_ccy and h.inst.asset_class != AssetClass.DERIV) else 0.0
        t = eq + rt + sp + fx
        tot["equity"] += eq
        tot["rates"] += rt
        tot["spread"] += sp
        tot["fx"] += fx
        lines.append({"symbol": h.inst.symbol, "exposure": e, "pnl": t})
    lines.sort(key=lambda x: x["pnl"])
    nav = snap.nav
    total = sum(tot.values())
    return {
        "account": snap.account.code,
        "nav": nav,
        "pnl": total,
        "pnl_pct": total / nav * 100 if nav else 0,
        "by_factor": tot,
        "worst_lines": lines[:10],
    }


def scenario_pnl(snap: Snapshot, key: str) -> dict:
    sc = SCENARIOS[key]
    r = stress(snap, sc["equity_pct"], sc["rates_bp"], sc["spread_bp"], sc["fx_pct"])
    r["scenario"] = key
    r["label"] = sc["label"]
    return r


def instrument_stats(db: Session, insts: list[Instrument]) -> tuple[list[Instrument], np.ndarray, np.ndarray]:
    ids, rets = returns_matrix(db, [i.id for i in insts])
    by = {i.id: i for i in insts}
    kept = [by[i] for i in ids]
    if not kept:
        return [], np.zeros(0), np.zeros((0, 0))
    mu = rets.mean(axis=0) * 252
    cov = np.cov(rets, rowvar=False) * 252
    cov = np.atleast_2d(cov)
    # light shrinkage toward the diagonal for numerical stability
    cov = 0.9 * cov + 0.1 * np.diag(np.diag(cov))
    return kept, mu, cov
