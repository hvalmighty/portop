"""Rule-based compliance engine: pre-trade checks, post-trade scans and passive breach detection.

Every rule evaluates a *holdings snapshot* of one account, so the same rule definitions are used
for pre-trade (snapshot with hypothetical orders applied), post-trade and what-if analysis.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone

from sqlalchemy.orm import Session, joinedload

from ..models import (
    Account,
    Alert,
    AssetClass,
    Breach,
    BreachStatus,
    CashBalance,
    ComplianceRule,
    Instrument,
    Position,
    Severity,
)
from .valuation import Fx, market_value, notional

RATING_SCALE = [
    "AAA", "AA+", "AA", "AA-", "A+", "A", "A-", "BBB+", "BBB", "BBB-",
    "BB+", "BB", "BB-", "B+", "B", "B-", "CCC+", "CCC", "CCC-", "CC", "C", "D",
]

RULE_TYPES: dict[str, dict] = {
    "MAX_ISSUER_WEIGHT": {"params": {"limit_pct": "number", "exempt_sectors": "list"}, "desc": "Max exposure to a single issuer, % of NAV"},
    "MAX_POSITION_WEIGHT": {"params": {"limit_pct": "number", "exempt_sectors": "list"}, "desc": "Max single position, % of NAV"},
    "MAX_SECTOR_WEIGHT": {"params": {"limit_pct": "number"}, "desc": "Max exposure to a sector, % of NAV"},
    "ASSET_CLASS_BAND": {
        "params": {"asset_class": "EQ|FI|DERIV|FUND", "min_pct": "number", "max_pct": "number"},
        "desc": "Asset-class gross exposure band, % of NAV",
    },
    "MIN_RATING": {"params": {"min_rating": "rating"}, "desc": "Minimum credit rating for fixed income"},
    "RESTRICTED_LIST": {"params": {"symbols": "list", "issuers": "list"}, "desc": "Prohibited securities/issuers"},
    "MAX_GROSS_LEVERAGE": {"params": {"limit_pct": "number"}, "desc": "Gross exposure / NAV"},
    "MAX_DURATION": {"params": {"limit_years": "number"}, "desc": "Exposure-weighted modified duration of FI book"},
    "MIN_ESG_SCORE": {"params": {"min_score": "number"}, "desc": "Exposure-weighted ESG score floor"},
    "MAX_FX_EXPOSURE": {"params": {"limit_pct": "number"}, "desc": "Non-base-currency exposure, % of NAV"},
    "NO_SHORT_CASH": {"params": {}, "desc": "No short positions in cash instruments"},
    "MIN_CASH_PCT": {"params": {"min_pct": "number"}, "desc": "Minimum cash buffer, % of NAV"},
}


def rating_rank(r: str | None) -> int:
    if not r:
        return len(RATING_SCALE)  # unrated = worst
    return RATING_SCALE.index(r) if r in RATING_SCALE else len(RATING_SCALE)


@dataclass
class Holding:
    inst: Instrument
    qty: float
    avg_px: float


@dataclass
class Snapshot:
    account: Account
    holdings: dict[int, Holding]
    cash: float  # base ccy
    fx: Fx

    def exp(self, h: Holding) -> float:
        return self.fx.convert(notional(h.inst, h.qty), h.inst.ccy, self.account.base_ccy)

    @property
    def nav(self) -> float:
        mv = sum(
            self.fx.convert(market_value(h.inst, h.qty, h.avg_px), h.inst.ccy, self.account.base_ccy)
            for h in self.holdings.values()
        )
        return self.cash + mv

    def apply(self, inst: Instrument, signed_qty: float) -> None:
        h = self.holdings.get(inst.id)
        cost = self.fx.convert(notional(inst, signed_qty), inst.ccy, self.account.base_ccy)
        if inst.asset_class != AssetClass.DERIV:
            self.cash -= cost
        if h is None:
            self.holdings[inst.id] = Holding(inst, signed_qty, inst.price)
        else:
            h.qty += signed_qty


@dataclass
class RuleResult:
    rule_id: int
    code: str
    name: str
    severity: str
    passed: bool
    observed: float
    limit: float
    subject: str = ""
    message: str = ""
    direction: str = "max"  # "max": higher observed is worse; "min": lower observed is worse


@dataclass
class CheckOutcome:
    status: str  # PASS / WARN / FAIL
    results: list[RuleResult] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "status": self.status,
            "checked_at": datetime.now(timezone.utc).isoformat(),
            "results": [r.__dict__ for r in self.results],
        }


def load_snapshot(db: Session, account: Account, fx: Fx) -> Snapshot:
    rows = (
        db.query(Position).options(joinedload(Position.instrument)).filter(Position.account_id == account.id).all()
    )
    cash = sum(
        fx.convert(c.amount, c.ccy, account.base_ccy)
        for c in db.query(CashBalance).filter(CashBalance.account_id == account.id)
    )
    return Snapshot(account, {p.instrument_id: Holding(p.instrument, p.qty, p.avg_px) for p in rows}, cash, fx)


def applicable_rules(db: Session, account: Account) -> list[ComplianceRule]:
    rules = db.query(ComplianceRule).filter(ComplianceRule.is_active.is_(True)).all()
    out = []
    for r in rules:
        if r.scope == "GLOBAL" or (r.scope == "ENTITY" and r.scope_ref == account.entity_code) or (
            r.scope == "ACCOUNT" and r.scope_ref == account.code
        ):
            out.append(r)
    # client-specific restrictions captured on the account behave as an implicit hard rule
    return out


def _grouped(snap: Snapshot, key) -> dict[str, float]:
    g: dict[str, float] = defaultdict(float)
    for h in snap.holdings.values():
        if abs(h.qty) > 1e-9:
            g[key(h)] += abs(snap.exp(h))
    return g


def evaluate_rule(rule: ComplianceRule, snap: Snapshot) -> list[RuleResult]:
    """Return one result per breached subject, or a single passing result."""
    p = rule.params or {}
    nav = snap.nav
    live = [h for h in snap.holdings.values() if abs(h.qty) > 1e-9]
    res: list[RuleResult] = []

    def mk(passed: bool, observed: float, limit: float, subject: str = "", msg: str = "",
           direction: str = "max") -> RuleResult:
        return RuleResult(rule.id, rule.code, rule.name, rule.severity.value, passed, round(observed, 4),
                          round(limit, 4), subject, msg, direction)

    pct = (lambda x: x / nav * 100) if nav > 0 else (lambda x: float("inf") if x else 0.0)
    t = rule.rule_type

    if t in ("MAX_ISSUER_WEIGHT", "MAX_SECTOR_WEIGHT", "MAX_POSITION_WEIGHT"):
        keyf = {
            "MAX_ISSUER_WEIGHT": lambda h: h.inst.issuer,
            "MAX_SECTOR_WEIGHT": lambda h: h.inst.sector or "Unclassified",
            "MAX_POSITION_WEIGHT": lambda h: h.inst.symbol,
        }[t]
        # derivatives are excluded from issuer/sector concentration (counterparty limits apply separately)
        exempt = set(p.get("exempt_sectors", []))
        g: dict[str, float] = defaultdict(float)
        for h in live:
            if h.inst.asset_class != AssetClass.DERIV and h.inst.sector not in exempt:
                g[keyf(h)] += abs(snap.exp(h))
        limit = float(p.get("limit_pct", 100))
        worst = 0.0
        for subj, v in g.items():
            w = pct(v)
            worst = max(worst, w)
            if w > limit + 1e-9:
                res.append(mk(False, w, limit, subj, f"{subj} at {w:.2f}% exceeds {limit:.2f}%"))
        return res or [mk(True, worst, limit)]

    if t == "ASSET_CLASS_BAND":
        ac = p.get("asset_class", "EQ")
        v = pct(sum(abs(snap.exp(h)) for h in live if h.inst.asset_class.value == ac))
        lo, hi = float(p.get("min_pct", 0)), float(p.get("max_pct", 100))
        if v > hi + 1e-9:
            return [mk(False, v, hi, ac, f"{ac} at {v:.2f}% above max {hi:.2f}%")]
        if v < lo - 1e-9:
            return [mk(False, v, lo, ac, f"{ac} at {v:.2f}% below min {lo:.2f}%", "min")]
        return [mk(True, v, hi, ac)]

    if t == "MIN_RATING":
        floor = p.get("min_rating", "BBB-")
        for h in live:
            if h.inst.asset_class == AssetClass.FI and h.qty > 0 and rating_rank(h.inst.rating) > rating_rank(floor):
                res.append(mk(False, pct(abs(snap.exp(h))), 0, h.inst.symbol,
                              f"{h.inst.symbol} rated {h.inst.rating or 'NR'} below floor {floor}"))
        return res or [mk(True, 0, 0)]

    if t == "RESTRICTED_LIST":
        syms = set(p.get("symbols", [])) | set(snap.account.restrictions or [])
        issuers = set(p.get("issuers", []))
        for h in live:
            if h.inst.symbol in syms or h.inst.issuer in issuers:
                res.append(mk(False, pct(abs(snap.exp(h))), 0, h.inst.symbol,
                              f"{h.inst.symbol} ({h.inst.issuer}) is restricted"))
        return res or [mk(True, 0, 0)]

    if t == "MAX_GROSS_LEVERAGE":
        v = pct(sum(abs(snap.exp(h)) for h in live))
        lim = float(p.get("limit_pct", 100))
        return [mk(v <= lim + 1e-9, v, lim, "GROSS", "" if v <= lim else f"Gross {v:.1f}% > {lim:.1f}%")]

    if t == "MAX_DURATION":
        fi = [h for h in live if h.inst.duration is not None and h.inst.asset_class == AssetClass.FI]
        tot = sum(abs(snap.exp(h)) for h in fi)
        dur = sum(abs(snap.exp(h)) * (h.inst.duration or 0) * (1 if h.qty > 0 else -1) for h in fi) / tot if tot else 0
        lim = float(p.get("limit_years", 10))
        return [mk(dur <= lim + 1e-9, dur, lim, "FI", "" if dur <= lim else f"Duration {dur:.2f}y > {lim:.2f}y")]

    if t == "MIN_ESG_SCORE":
        sc = [h for h in live if h.inst.esg_score is not None and h.inst.asset_class != AssetClass.DERIV]
        tot = sum(abs(snap.exp(h)) for h in sc)
        v = sum(abs(snap.exp(h)) * h.inst.esg_score for h in sc) / tot if tot else 100
        lim = float(p.get("min_score", 50))
        return [mk(v >= lim - 1e-9, v, lim, "ESG", "" if v >= lim else f"ESG {v:.1f} < {lim:.1f}", "min")]

    if t == "MAX_FX_EXPOSURE":
        v = pct(sum(abs(snap.exp(h)) for h in live if h.inst.ccy != snap.account.base_ccy
                    and h.inst.asset_class != AssetClass.DERIV))
        lim = float(p.get("limit_pct", 100))
        return [mk(v <= lim + 1e-9, v, lim, "FX", "" if v <= lim else f"Non-base ccy {v:.1f}% > {lim:.1f}%")]

    if t == "NO_SHORT_CASH":
        for h in live:
            if h.qty < 0 and h.inst.asset_class in (AssetClass.EQ, AssetClass.FI, AssetClass.FUND):
                res.append(mk(False, h.qty, 0, h.inst.symbol, f"Short position in {h.inst.symbol}", "min"))
        return res or [mk(True, 0, 0)]

    if t == "MIN_CASH_PCT":
        v = pct(snap.cash)
        lim = float(p.get("min_pct", 0))
        return [mk(v >= lim - 1e-9, v, lim, "CASH", "" if v >= lim else f"Cash {v:.2f}% < {lim:.2f}%", "min")]

    return [mk(True, 0, 0, msg=f"Unknown rule type {t}")]


def evaluate_snapshot(rules: list[ComplianceRule], snap: Snapshot) -> list[RuleResult]:
    out: list[RuleResult] = []
    for r in rules:
        out.extend(evaluate_rule(r, snap))
    return out


def _failing(results: list[RuleResult]) -> dict[tuple[int, str], RuleResult]:
    return {(r.rule_id, r.subject): r for r in results if not r.passed}


def pre_trade_check(db: Session, account: Account, trades: list[tuple[Instrument, float]], fx: Fx | None = None) -> CheckOutcome:
    """Check hypothetical trades (instrument, signed qty). A rule fails only if the trade causes or worsens a breach."""
    fx = fx or Fx.load(db)
    rules = applicable_rules(db, account)
    before = load_snapshot(db, account, fx)
    after = load_snapshot(db, account, fx)
    for inst, q in trades:
        after.apply(inst, q)
    pre = _failing(evaluate_snapshot(rules, before))
    post_all = evaluate_snapshot(rules, after)
    status = "PASS"
    final: list[RuleResult] = []
    for r in post_all:
        if not r.passed:
            prior = pre.get((r.rule_id, r.subject))
            worsened = prior is None or _worse(r, prior)
            if not worsened:
                r.message = f"Pre-existing breach not worsened: {r.message}"
                r.severity = "INFO"
                status = "WARN" if status == "PASS" else status
            elif r.severity == Severity.HARD.value:
                status = "FAIL"
            elif status != "FAIL":
                status = "WARN"
        final.append(r)
    return CheckOutcome(status, final)


def _worse(now: RuleResult, prior: RuleResult) -> bool:
    if now.direction == "min":
        return now.observed < prior.observed - 1e-6
    return now.observed > prior.observed + 1e-6


def run_post_trade_scan(db: Session, accounts: list[Account] | None = None) -> dict:
    """Scan all accounts, open new (passive) breaches, auto-resolve cleared ones, raise alerts."""
    fx = Fx.load(db)
    accounts = accounts or db.query(Account).filter(Account.is_active.is_(True)).all()
    opened = resolved = 0
    now = datetime.now(timezone.utc)
    for a in accounts:
        rules = applicable_rules(db, a)
        failing = _failing(evaluate_snapshot(rules, load_snapshot(db, a, fx)))
        open_rows = (
            db.query(Breach)
            .filter(Breach.account_id == a.id, Breach.status != BreachStatus.RESOLVED)
            .all()
        )
        open_keys = {(b.rule_id, b.subject): b for b in open_rows}
        for key, r in failing.items():
            if key in open_keys:
                b = open_keys[key]
                b.observed = r.observed
                continue
            db.add(
                Breach(
                    rule_id=r.rule_id, account_id=a.id, kind="PASSIVE", subject=r.subject,
                    observed=r.observed, limit=r.limit, message=r.message,
                )
            )
            db.add(Alert(level="CRIT" if r.severity == "HARD" else "WARN", category="COMPLIANCE",
                         message=f"{a.code}: {r.code} {r.message}", account_code=a.code))
            opened += 1
        for key, b in open_keys.items():
            if key not in failing:
                b.status = BreachStatus.RESOLVED
                b.resolved_at = now
                b.notes = [*(b.notes or []), {"ts": now.isoformat(), "user": "system", "text": "Auto-resolved: back within limit"}]
                resolved += 1
    db.commit()
    return {"accounts": len(accounts), "opened": opened, "resolved": resolved}
