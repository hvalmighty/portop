"""BDO TIG sample portfolios: mandate set-up, demo market data and benchmark-relative optimisation.

The three scenarios come from BDO's sample-portfolio brief:

  BDO-PEQ  Peso Equity Fund                 PHP, Philippine equities, max 20% per stock,   +100 bps vs PSEi TR
  BDO-GEQ  Institutional Global EQ Port     USD, global feeder funds, no security cap,     +100 bps vs MSCI ACWI TR
  BDO-HTF  Peso Health Tech Fund            USD, 10 listed funds/ETFs, max 20% per fund,   +200 bps vs 50% NDWUIT / 50% NDWUHC

Everything that is not in BDO's brief is a placeholder for demonstration: the BDO-GEQ feeder-fund universe uses
existing global equities, the health-tech fund names are unconfirmed, benchmark levels and price history are
synthetic. Replace them with BDO's master data and licensed history before any real use.

The goal is applied as a constraint: minimise portfolio variance subject to expected return >= benchmark expected
return + excess goal, within the position cap. If no portfolio can reach the goal, the result says so and gives the
best achievable excess return instead of forcing a weight set.
"""

from __future__ import annotations

import math
import zlib

import numpy as np
from fastapi import HTTPException
from sqlalchemy.orm import Session

from ..models import AssetClass, Instrument, ModelPortfolio, ModelVersion, PriceHistory
from .optimizer import OptimizationError, OptInputs, max_return, optimise, stats
from .risk import instrument_stats

RF = 0.04

US_EQ = ["MSFT", "NVDA", "AMZN", "GOOGL", "META", "TSLA", "JPM", "BRK.B", "XOM", "UNH", "V", "JNJ", "AAPL"]
PH_EQ = ["BDO", "SM", "ALI", "AC", "JFC", "TEL", "ICT", "MER"]
HEALTH_TECH_FUNDS = ["EQQU LN", "IUIT LN", "IYW US", "SEMI NA", "CEMA LN", "BGWTD2U LX", "MLWORHD LX",
                     "JHHBA2U LX", "GMOQIEU ID", "ISAC LN"]
# PLACEHOLDER long-run return per fund (annual). No fund-level data was supplied, so the funds are spread from
# 6% to 14%. Replace with BDO's expected returns: the health-tech result depends entirely on these numbers.
FUND_RETURN_PLACEHOLDERS = dict(zip(HEALTH_TECH_FUNDS, (round(x, 4) for x in np.linspace(0.06, 0.14, 10))))
EPS = 0.00005  # half a basis point: solver and weight-rounding tolerance

# symbol, name, ccy, level, annual drift, annual vol (synthetic demo history)
BENCHMARKS = [
    ("PSEI", "PSEi Total Return Index", "PHP", 7000.0, 0.07, 0.17),
    ("MSCIACWI", "MSCI ACWI Total Return Index (USD)", "USD", 1000.0, 0.08, 0.15),
    ("NDWUIT", "MSCI World Information Technology Index (NDWUIT)", "USD", 5000.0, 0.12, 0.22),
    ("NDWUHC", "MSCI World Health Care Index (NDWUHC)", "USD", 8000.0, 0.07, 0.16),
]

SCENARIOS = [
    {
        "code": "BDO-PEQ",
        "name": "Peso Equity Fund",
        "description": "BDO sample portfolio 1: Philippine equities in PHP. Maximum 20% per stock. "
                       "Goal: 100 bps outperformance vs PSEi Total Return.",
        "benchmark": "PSEi Total Return",
        "tolerance_pct": 2.5,
        "mandate": {
            "currency": "PHP",
            "asset_class_label": "Philippine equities",
            "universe": PH_EQ,
            "universe_source": "PH equities in the security master. PLACEHOLDER: replace with BDO Trust's local "
                               "equity issuer list.",
            "max_weight_pct": 20.0,
            "max_weight_basis": "per stock",
            "benchmark_weights": {"PSEI": 100.0},
            "excess_return_bps": 100,
        },
    },
    {
        "code": "BDO-GEQ",
        "name": "Institutional Global EQ Port",
        "description": "BDO sample portfolio 2: global equity feeder funds in USD. No security-level cap in the brief. "
                       "The firm-wide 20% single-position soft limit still applies. "
                       "Goal: 100 bps outperformance vs MSCI ACWI Total Return.",
        "benchmark": "MSCI ACWI Total Return",
        "tolerance_pct": 2.5,
        "mandate": {
            "currency": "USD",
            "asset_class_label": "Global equities",
            "universe": US_EQ,
            "universe_source": "PLACEHOLDER: existing US equities in the security master, standing in for BDO's "
                               "USD UITF feeder-fund list.",
            "max_weight_pct": 100.0,
            "max_weight_basis": "no cap in BDO brief",
            "benchmark_weights": {"MSCIACWI": 100.0},
            "excess_return_bps": 100,
        },
    },
    {
        "code": "BDO-HTF",
        "name": "Peso Health Tech Fund",
        "description": "BDO sample portfolio 3: 10 listed funds/ETFs in USD. Maximum 20% per fund. "
                       "Goal: 200 bps outperformance vs a 50/50 blend of MSCI World IT (NDWUIT) and MSCI World "
                       "Health Care (NDWUHC).",
        "benchmark": "50% MSCI World IT (NDWUIT) / 50% MSCI World Health Care (NDWUHC)",
        "tolerance_pct": 2.5,
        "mandate": {
            "currency": "USD",
            "asset_class_label": "Global equities (funds/ETFs)",
            "universe": HEALTH_TECH_FUNDS,
            "universe_source": "BDO's list of 10 funds/ETFs. Names and price history are PLACEHOLDERS until "
                               "confirmed against BDO master data.",
            "max_weight_pct": 20.0,
            "max_weight_basis": "per fund",
            "benchmark_weights": {"NDWUIT": 50.0, "NDWUHC": 50.0},
            "excess_return_bps": 200,
        },
    },
]


# ----------------------------------------------------------------------------- demo market data

def _path(sym: str, last: float, vol: float, drift: float, mkt: np.ndarray, beta: float) -> np.ndarray:
    """Daily closes ending at `last`, from a seeded random walk calibrated to `drift` (deterministic per symbol)."""
    n = len(mkt)
    rng = np.random.default_rng(zlib.crc32(sym.encode()))
    daily = vol / math.sqrt(252)
    rets = beta * mkt * (daily / 0.011) + rng.normal(0, daily, n)
    # calibrate the realised mean over the estimation window to the stated long-run assumption, so the goal test
    # reflects the assumption rather than the luck of a random walk
    window = slice(max(n - 500, 1), n)  # the last 500 returns: the window risk.instrument_stats estimates from
    rets[window] = rets[window] - rets[window].mean() + drift / 252
    growth = np.cumprod((1 + rets)[::-1])[::-1]  # growth[k] = product of (1 + r) from day k to today
    return last / np.append(growth[1:], 1.0)


def _add_instrument(db: Session, sym: str, name: str, ccy: str, px: float, asset_class: AssetClass, inst_type: str,
                    issuer: str, sector: str, is_active: bool, drift: float, vol: float,
                    dates: list, mkt: np.ndarray, beta: float) -> None:
    i = Instrument(symbol=sym, name=name, asset_class=asset_class, inst_type=inst_type, ccy=ccy, issuer=issuer,
                   sector=sector, country="", contract_size=1.0, price=px, prev_close=round(px * 0.998, 6),
                   vol=vol, adv=1_000_000, is_active=is_active)
    db.add(i)
    db.flush()
    series = _path(sym, px, vol, drift, mkt, beta)
    db.bulk_save_objects([PriceHistory(instrument_id=i.id, d=d, close=float(c)) for d, c in zip(dates, series)])


def _ensure_market_data(db: Session) -> bool:
    """Benchmarks and BDO universe funds, added only if missing. Aligns dates with the existing history."""
    dates = [d for (d,) in db.query(PriceHistory.d).join(Instrument).filter(Instrument.symbol == "BDO")
             .order_by(PriceHistory.d).all()]
    if len(dates) < 60:
        return False
    rng = np.random.default_rng(2026)
    mkt = rng.normal(0, 0.011, len(dates))
    existing = {s for (s,) in db.query(Instrument.symbol).all()}
    for sym, name, ccy, px, drift, vol in BENCHMARKS:
        if sym not in existing:
            _add_instrument(db, sym, name, ccy, px, AssetClass.EQ, "index", sym, "Index", False,
                            drift, vol, dates, mkt, 1.0)
    for sym in HEALTH_TECH_FUNDS:
        if sym not in existing:
            _add_instrument(db, sym, f"{sym} (BDO universe - name to confirm)", "USD", 100.0, AssetClass.FUND,
                            "etf", sym, "Global equity fund", True, FUND_RETURN_PLACEHOLDERS[sym], 0.20,
                            dates, mkt, 1.0)
    db.flush()
    return True


# ----------------------------------------------------------------------------- optimisation

def benchmark_return(db: Session, weights: dict[str, float]) -> float:
    """Expected annual return of the benchmark blend (weights in %), from the same history the optimiser uses."""
    insts = db.query(Instrument).filter(Instrument.symbol.in_(list(weights))).all()
    kept, mu, _ = instrument_stats(db, insts)
    by_sym = {i.symbol: float(m) for i, m in zip(kept, mu)}
    missing = sorted(set(weights) - set(by_sym))
    if missing:
        raise HTTPException(422, f"Benchmark has no price history: {', '.join(missing)}")
    return sum(by_sym[s] * pct / 100 for s, pct in weights.items())


def _round_to_100(raw: dict[str, float], cap: float) -> dict[str, float]:
    """Round weights (in %) to 2 dp so they sum to exactly 100, keeping every weight under the cap."""
    w = {s: round(v, 2) for s, v in raw.items() if v >= 0.05}
    diff = round(100 - sum(w.values()), 2)
    if diff:
        room = [s for s in w if cap - w[s] >= diff - 1e-9] if diff > 0 else list(w)
        k = max(room or list(w), key=lambda s: w[s])
        w[k] = round(w[k] + diff, 2)
    return w


def scenario_result(db: Session, m: ModelPortfolio) -> dict:
    """Optimise one model against its mandate. Pure calculation: nothing is saved."""
    mandate = m.mandate or {}
    if not mandate.get("universe"):
        raise HTTPException(409, f"Model {m.code} has no mandate configuration")
    universe = mandate["universe"]
    cap = mandate["max_weight_pct"] / 100
    goal = mandate["excess_return_bps"] / 10000
    insts = db.query(Instrument).filter(Instrument.symbol.in_(universe)).all()
    kept, mu, cov = instrument_stats(db, insts)
    if len(kept) < 2:
        raise HTTPException(422, f"Model {m.code}: fewer than two instruments with price history")

    bench = benchmark_return(db, mandate["benchmark_weights"])
    target = bench + goal + EPS
    symbols = [i.symbol for i in kept]
    inp = OptInputs(symbols=symbols, asset_classes=[i.asset_class.value for i in kept], mu=mu, cov=cov,
                    min_w=0.0, max_w=cap, rf=RF, target_return=target)
    result = {
        "model": m.code,
        "name": m.name,
        "currency": mandate.get("currency"),
        "max_weight_pct": mandate["max_weight_pct"],
        "max_weight_basis": mandate.get("max_weight_basis"),
        "goal_bps": mandate["excess_return_bps"],
        "benchmark": m.benchmark,
        "benchmark_return": bench,
        "target_return": target,
        "instruments_used": len(kept),
        "dropped": sorted(set(universe) - set(symbols)),
    }
    ceiling = max_return(inp)
    result["max_achievable_return"] = ceiling
    result["max_achievable_excess_bps"] = round((ceiling - bench) * 10000, 1)
    if ceiling < target - 1e-9:
        result.update(feasible=False, weights={}, message=(
            f"Goal not achievable under the {mandate['max_weight_pct']:.0f}% cap: best excess return is "
            f"{result['max_achievable_excess_bps']} bps against a {mandate['excess_return_bps']} bps goal."))
        return result
    try:
        w = optimise(inp, "target_return")
    except OptimizationError as exc:
        raise HTTPException(422, str(exc)) from exc

    weights = _round_to_100({s: float(x) * 100 for s, x in zip(symbols, w)}, mandate["max_weight_pct"])
    wv = np.array([weights.get(s, 0.0) / 100 for s in symbols])
    st = stats(wv, mu, cov, RF)
    excess = st["exp_return"] - bench
    result.update(
        feasible=True,
        message="Optimised: minimum variance subject to the excess-return goal and the position cap.",
        weights=weights,
        exp_return=st["exp_return"],
        excess_return_bps=round(excess * 10000, 1),
        volatility=st["volatility"],
        sharpe=st["sharpe"],
        max_position_pct=max(weights.values()),
        goal_met=excess >= goal - EPS,
        cap_respected=max(weights.values()) <= mandate["max_weight_pct"] + 1e-6,
        firm_limit_breaches=[s for s, v in weights.items() if v > 20.0 + 1e-9],  # INT-POS-20, global soft limit
    )
    return result


# ----------------------------------------------------------------------------- seeding

def seed_bdo_scenarios(db: Session) -> dict:
    """Idempotent: safe on fresh and already-seeded databases. Creates what is missing, never overwrites."""
    if not _ensure_market_data(db):
        return {"status": "skipped", "reason": "no base price history"}
    created = []
    for sc in SCENARIOS:
        m = db.query(ModelPortfolio).filter(ModelPortfolio.code == sc["code"]).one_or_none()
        if m is None:
            m = ModelPortfolio(code=sc["code"], name=sc["name"], description=sc["description"],
                               benchmark=sc["benchmark"], tolerance_pct=sc["tolerance_pct"], mandate=sc["mandate"])
            db.add(m)
            db.flush()
            created.append(sc["code"])
        elif not m.mandate:
            m.mandate = sc["mandate"]
        if not m.versions:
            res = scenario_result(db, m)
            if res.get("feasible"):
                # proposed by the PM, awaiting the compliance checker: exercises maker-checker on day one
                m.versions.append(ModelVersion(
                    version=1, weights=res["weights"], status="DRAFT", created_by="pm.santos",
                    rationale=f"Optimised for {sc['name']}: {res['message']} Excess return "
                              f"{res['excess_return_bps']} bps vs goal {res['goal_bps']} bps."))
    db.commit()
    return {"status": "ok", "created": created}


def check_mandate(m: ModelPortfolio, weights: dict[str, float]) -> None:
    """Reject weights that break the model's mandate. Models without a mandate are unaffected."""
    validate_mandate_weights(m.code, m.mandate or {}, weights)


def validate_mandate_weights(code: str, mandate: dict, weights: dict[str, float]) -> None:
    if not mandate.get("universe"):
        return
    outside = sorted(s for s in weights if s != "CASH" and s not in mandate["universe"])
    if outside:
        raise HTTPException(422, f"{code}: securities outside the mandate universe: {', '.join(outside)}")
    cap = mandate["max_weight_pct"]
    over = {s: w for s, w in weights.items() if s != "CASH" and w > cap + 1e-9}
    if over:
        detail = ", ".join(f"{s} {w:.2f}%" for s, w in over.items())
        raise HTTPException(422, f"{code}: weights above the {cap:g}% cap ({mandate.get('max_weight_basis')}): {detail}")


def validate_mandate_definition(db: Session, mandate: dict) -> None:
    """Every universe security and benchmark component must exist in the security master."""
    syms = set(mandate["universe"]) | set(mandate["benchmark_weights"])
    found = {s for (s,) in db.query(Instrument.symbol).filter(Instrument.symbol.in_(syms)).all()}
    missing = sorted(syms - found)
    if missing:
        raise HTTPException(422, f"Unknown instruments in mandate: {', '.join(missing)}")
