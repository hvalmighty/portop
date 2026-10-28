"""Long-only portfolio optimisation (mean-variance family) with weight and asset-class constraints."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.optimize import minimize

OBJECTIVES = ("min_variance", "max_sharpe", "target_return", "risk_parity")


@dataclass
class OptInputs:
    symbols: list[str]
    asset_classes: list[str]
    mu: np.ndarray
    cov: np.ndarray
    min_w: float = 0.0
    max_w: float = 1.0
    rf: float = 0.04
    class_bounds: dict[str, tuple[float, float]] | None = None  # asset class -> (min, max) as fractions
    target_return: float | None = None
    current: np.ndarray | None = None  # current weights, for turnover penalty
    turnover_penalty: float = 0.0


class OptimizationError(ValueError):
    pass


def _constraints(inp: OptInputs, extra: list | None = None):
    cons = [{"type": "eq", "fun": lambda w: w.sum() - 1.0}]
    for ac, (lo, hi) in (inp.class_bounds or {}).items():
        mask = np.array([1.0 if a == ac else 0.0 for a in inp.asset_classes])
        if mask.sum() == 0:
            continue
        cons.append({"type": "ineq", "fun": lambda w, m=mask, lo=lo: m @ w - lo})
        cons.append({"type": "ineq", "fun": lambda w, m=mask, hi=hi: hi - m @ w})
    return cons + (extra or [])


def _solve(inp: OptInputs, objective, extra_cons=None) -> np.ndarray:
    n = len(inp.symbols)
    if n == 0:
        raise OptimizationError("No instruments with sufficient price history")
    if inp.max_w * n < 1 - 1e-9:
        raise OptimizationError(f"Max weight {inp.max_w:.2%} too low for {n} instruments")
    if inp.min_w * n > 1 + 1e-9:
        raise OptimizationError("Min weight too high")
    x0 = np.full(n, 1.0 / n)

    def obj(w):
        v = objective(w)
        if inp.turnover_penalty and inp.current is not None:
            v += inp.turnover_penalty * np.abs(w - inp.current).sum()
        return v

    res = minimize(
        obj, x0, method="SLSQP", bounds=[(inp.min_w, inp.max_w)] * n,
        constraints=_constraints(inp, extra_cons), options={"maxiter": 500, "ftol": 1e-10},
    )
    if not res.success:
        raise OptimizationError(f"Optimiser did not converge: {res.message}")
    w = np.clip(res.x, 0, None)
    return w / w.sum()


def optimise(inp: OptInputs, objective: str) -> np.ndarray:
    cov, mu = inp.cov, inp.mu
    if objective == "min_variance":
        return _solve(inp, lambda w: w @ cov @ w)
    if objective == "max_sharpe":
        return _solve(inp, lambda w: -(w @ mu - inp.rf) / np.sqrt(max(w @ cov @ w, 1e-12)))
    if objective == "target_return":
        if inp.target_return is None:
            raise OptimizationError("target_return required")
        return _solve(inp, lambda w: w @ cov @ w,
                      [{"type": "ineq", "fun": lambda w: w @ mu - inp.target_return}])
    if objective == "risk_parity":
        def rp(w):
            port = w @ cov @ w
            rc = w * (cov @ w) / max(port, 1e-12)
            return float(((rc - 1.0 / len(w)) ** 2).sum())
        return _solve(inp, rp)
    raise OptimizationError(f"Unknown objective {objective}")


def stats(w: np.ndarray, mu: np.ndarray, cov: np.ndarray, rf: float) -> dict:
    ret = float(w @ mu)
    vol = float(np.sqrt(max(w @ cov @ w, 0)))
    rc = w * (cov @ w) / (vol**2) if vol > 0 else np.zeros_like(w)
    return {"exp_return": ret, "volatility": vol, "sharpe": (ret - rf) / vol if vol else 0.0,
            "risk_contrib": rc.tolist()}


def frontier(inp: OptInputs, points: int = 15) -> list[dict]:
    try:
        wmin = optimise(inp, "min_variance")
    except OptimizationError:
        return []
    r_lo = float(wmin @ inp.mu)
    # highest achievable return under constraints: maximise return
    try:
        wmax = _solve(inp, lambda w: -(w @ inp.mu))
    except OptimizationError:
        return []
    r_hi = float(wmax @ inp.mu)
    out = []
    for t in np.linspace(r_lo, r_hi, points):
        try:
            w = _solve(inp, lambda w: w @ inp.cov @ w, [{"type": "ineq", "fun": lambda w, t=t: w @ inp.mu - t}])
        except OptimizationError:
            continue
        s = stats(w, inp.mu, inp.cov, inp.rf)
        out.append({"exp_return": s["exp_return"], "volatility": s["volatility"]})
    return out
