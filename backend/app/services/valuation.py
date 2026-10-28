"""Position valuation, FX conversion and portfolio aggregation."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import asdict, dataclass, field

from sqlalchemy.orm import Session, joinedload

from ..models import Account, AssetClass, CashBalance, Entity, FxRate, Instrument, Position


class Fx:
    def __init__(self, rates: dict[str, float]):
        self.rates = rates

    @classmethod
    def load(cls, db: Session) -> Fx:
        return cls({r.ccy: r.usd_per_unit for r in db.query(FxRate).all()})

    def convert(self, amount: float, frm: str, to: str) -> float:
        if frm == to:
            return amount
        try:
            return amount * self.rates[frm] / self.rates[to]
        except KeyError as exc:
            raise ValueError(f"Missing FX rate for {exc.args[0]}") from exc


def notional(inst: Instrument, qty: float, price: float | None = None) -> float:
    return qty * (inst.price if price is None else price) * inst.contract_size


def market_value(inst: Instrument, qty: float, avg_px: float) -> float:
    """Contribution to NAV. Derivatives contribute their MTM, not their notional."""
    if inst.asset_class == AssetClass.DERIV:
        return qty * (inst.price - avg_px) * inst.contract_size
    return notional(inst, qty)


@dataclass
class PositionView:
    position_id: int
    account: str
    account_id: int
    instrument_id: int
    symbol: str
    name: str
    asset_class: str
    inst_type: str
    ccy: str
    issuer: str
    sector: str
    rating: str | None
    qty: float
    avg_px: float
    mark: float
    prev_close: float
    exposure: float  # local ccy, signed notional
    exposure_rep: float  # reporting ccy
    market_value_rep: float
    mtm_pnl_rep: float
    day_pnl_rep: float
    pnl_pct: float
    weight_pct: float  # of account NAV, by exposure
    maturity: str | None
    duration: float | None


@dataclass
class AccountSummary:
    account_id: int
    code: str
    name: str
    entity: str
    base_ccy: str
    mandate: str
    model_id: int | None
    aum: float  # mandate size in reporting ccy
    nav: float
    cash: float
    gross: float
    net: float
    pnl: float
    day_pnl: float
    gross_vs_aum_pct: float
    largest_symbol: str | None
    largest_pct: float
    share: dict = field(default_factory=dict)  # asset-class share of gross exposure (%)
    positions: int = 0


def load_accounts(db: Session, entity: str | None, allowed: list[str] | None, account_codes: list[str] | None = None):
    q = db.query(Account).filter(Account.is_active.is_(True))
    if entity:
        q = q.filter(Account.entity_code == entity)
    if allowed is not None:
        q = q.filter(Account.entity_code.in_(allowed))
    if account_codes:
        q = q.filter(Account.code.in_(account_codes))
    return q.order_by(Account.code).all()


def reporting_ccy(db: Session, entity: str | None) -> str:
    if entity:
        e = db.get(Entity, entity)
        if e:
            return e.reporting_ccy
    return "USD"


def value_accounts(db: Session, accounts: list[Account], rep_ccy: str, fx: Fx | None = None):
    fx = fx or Fx.load(db)
    ids = [a.id for a in accounts]
    positions = (
        db.query(Position)
        .options(joinedload(Position.instrument))
        .filter(Position.account_id.in_(ids))
        .all()
        if ids
        else []
    )
    cash_rows = db.query(CashBalance).filter(CashBalance.account_id.in_(ids)).all() if ids else []
    by_acct: dict[int, list[Position]] = defaultdict(list)
    for p in positions:
        if abs(p.qty) > 1e-9:
            by_acct[p.account_id].append(p)
    cash_by: dict[int, float] = defaultdict(float)
    for c in cash_rows:
        cash_by[c.account_id] += fx.convert(c.amount, c.ccy, rep_ccy)

    summaries: list[AccountSummary] = []
    views: list[PositionView] = []
    for a in accounts:
        rows = by_acct.get(a.id, [])
        mv_total = sum(fx.convert(market_value(p.instrument, p.qty, p.avg_px), p.instrument.ccy, rep_ccy) for p in rows)
        nav = cash_by[a.id] + mv_total
        gross = net = pnl = day = 0.0
        cls_gross: dict[str, float] = defaultdict(float)
        largest = (None, 0.0)
        acct_views = []
        for p in rows:
            i = p.instrument
            exp_local = notional(i, p.qty)
            exp_rep = fx.convert(exp_local, i.ccy, rep_ccy)
            pnl_rep = fx.convert(p.qty * (i.price - p.avg_px) * i.contract_size, i.ccy, rep_ccy)
            day_rep = fx.convert(p.qty * (i.price - i.prev_close) * i.contract_size, i.ccy, rep_ccy)
            cost = abs(p.qty * p.avg_px * i.contract_size)
            gross += abs(exp_rep)
            net += exp_rep
            pnl += pnl_rep
            day += day_rep
            cls_gross[i.asset_class.value] += abs(exp_rep)
            if abs(exp_rep) > largest[1]:
                largest = (i.symbol, abs(exp_rep))
            acct_views.append(
                PositionView(
                    position_id=p.id,
                    account=a.code,
                    account_id=a.id,
                    instrument_id=i.id,
                    symbol=i.symbol,
                    name=i.name,
                    asset_class=i.asset_class.value,
                    inst_type=i.inst_type,
                    ccy=i.ccy,
                    issuer=i.issuer,
                    sector=i.sector,
                    rating=i.rating,
                    qty=p.qty,
                    avg_px=round(p.avg_px, 6),
                    mark=round(i.price, 6),
                    prev_close=i.prev_close,
                    exposure=exp_local,
                    exposure_rep=exp_rep,
                    market_value_rep=fx.convert(market_value(i, p.qty, p.avg_px), i.ccy, rep_ccy),
                    mtm_pnl_rep=pnl_rep,
                    day_pnl_rep=day_rep,
                    pnl_pct=(p.qty * (i.price - p.avg_px) * i.contract_size / cost * 100) if cost else 0.0,
                    weight_pct=0.0,
                    maturity=i.maturity.isoformat() if i.maturity else None,
                    duration=i.duration,
                )
            )
        for v in acct_views:
            v.weight_pct = v.exposure_rep / nav * 100 if nav else 0.0
        views.extend(acct_views)
        aum_rep = fx.convert(a.aum, a.base_ccy, rep_ccy)
        summaries.append(
            AccountSummary(
                account_id=a.id,
                code=a.code,
                name=a.name,
                entity=a.entity_code,
                base_ccy=a.base_ccy,
                mandate=a.mandate,
                model_id=a.model_id,
                aum=aum_rep,
                nav=nav,
                cash=cash_by[a.id],
                gross=gross,
                net=net,
                pnl=pnl,
                day_pnl=day,
                gross_vs_aum_pct=gross / aum_rep * 100 if aum_rep else 0.0,
                largest_symbol=largest[0],
                largest_pct=largest[1] / aum_rep * 100 if aum_rep else 0.0,
                share={k: round(v / gross * 100, 2) if gross else 0.0 for k, v in cls_gross.items()},
                positions=len(rows),
            )
        )
    return summaries, views


def to_dict(obj) -> dict:
    return asdict(obj)
