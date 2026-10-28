"""Idempotent demo dataset: entities, security master, price history, accounts, models, rules, users.

Disabled in production by MPOWER_SEED_DEMO_DATA=false.
"""

from __future__ import annotations

import math
import os
import random
from datetime import date, datetime, timedelta, timezone

import numpy as np
from sqlalchemy.orm import Session

from .models import (
    Account,
    AssetClass,
    CashBalance,
    ComplianceRule,
    Entity,
    FxRate,
    Instrument,
    ModelPortfolio,
    ModelVersion,
    Position,
    PriceHistory,
    Role,
    RuleVersion,
    Severity,
    User,
)
from .security import hash_password

EQ, FI, DV, FD = AssetClass.EQ, AssetClass.FI, AssetClass.DERIV, AssetClass.FUND

FX = {"USD": 1.0, "SGD": 0.770, "PHP": 0.0173, "JPY": 0.0066, "EUR": 1.08, "HKD": 0.128}

# symbol, name, class, type, ccy, issuer, sector, country, rating, coupon, maturity, duration, size, price, vol, esg, adv
INSTRUMENTS = [
    # US equities
    ("MSFT", "Microsoft Corp", EQ, "cash_equity", "USD", "Microsoft", "Technology", "US", None, None, None, None, 1, 512.71, .26, 78, 2.0e7),
    ("NVDA", "NVIDIA Corp", EQ, "cash_equity", "USD", "NVIDIA", "Technology", "US", None, None, None, None, 1, 178.15, .48, 70, 2.5e8),
    ("AMZN", "Amazon.com Inc", EQ, "cash_equity", "USD", "Amazon", "Consumer Discretionary", "US", None, None, None, None, 1, 224.09, .32, 58, 4.0e7),
    ("GOOGL", "Alphabet Inc Class A", EQ, "cash_equity", "USD", "Alphabet", "Communication Services", "US", None, None, None, None, 1, 205.73, .30, 66, 3.0e7),
    ("META", "Meta Platforms Inc", EQ, "cash_equity", "USD", "Meta", "Communication Services", "US", None, None, None, None, 1, 742.63, .38, 48, 1.5e7),
    ("TSLA", "Tesla Inc", EQ, "cash_equity", "USD", "Tesla", "Consumer Discretionary", "US", None, None, None, None, 1, 343.00, .58, 52, 9.0e7),
    ("JPM", "JPMorgan Chase & Co", EQ, "cash_equity", "USD", "JPMorgan", "Financials", "US", None, None, None, None, 1, 297.61, .24, 61, 9.0e6),
    ("BRK.B", "Berkshire Hathaway Inc B", EQ, "cash_equity", "USD", "Berkshire Hathaway", "Financials", "US", None, None, None, None, 1, 497.86, .18, 55, 4.0e6),
    ("XOM", "Exxon Mobil Corp", EQ, "cash_equity", "USD", "Exxon Mobil", "Energy", "US", None, None, None, None, 1, 118.44, .25, 35, 1.5e7),
    ("UNH", "UnitedHealth Group Inc", EQ, "cash_equity", "USD", "UnitedHealth", "Health Care", "US", None, None, None, None, 1, 322.90, .30, 60, 5.0e6),
    ("V", "Visa Inc Class A", EQ, "cash_equity", "USD", "Visa", "Financials", "US", None, None, None, None, 1, 351.29, .20, 72, 6.0e6),
    ("JNJ", "Johnson & Johnson", EQ, "cash_equity", "USD", "Johnson & Johnson", "Health Care", "US", None, None, None, None, 1, 167.90, .16, 68, 7.0e6),
    ("AAPL", "Apple Inc", EQ, "cash_equity", "USD", "Apple", "Technology", "US", None, None, None, None, 1, 230.57, .27, 74, 5.0e7),
    # Singapore
    ("Z74", "Singapore Telecommunications Ltd", EQ, "cash_equity", "SGD", "Singtel", "Communication Services", "SG", None, None, None, None, 1, 3.83, .20, 71, 2.0e7),
    ("D05", "DBS Group Holdings Ltd", EQ, "cash_equity", "SGD", "DBS Group", "Financials", "SG", None, None, None, None, 1, 44.10, .19, 73, 4.0e6),
    ("DBSSP-2031", "DBS Group 4.250% Subordinated 2031", FI, "corporate_bond", "SGD", "DBS Group", "Financials", "SG", "A", 4.25, date(2031, 5, 28), 4.7, .01, 96.52, .05, 73, 5.0e7),
    ("SGGB-2029", "Singapore Government Bond 2.875% 2029", FI, "govt_bond", "SGD", "Republic of Singapore", "Sovereign", "SG", "AAA", 2.875, date(2029, 9, 1), 2.8, .01, 101.94, .03, 85, 2.0e8),
    ("SGGB-2034", "Singapore Government Bond 3.375% 2034", FI, "govt_bond", "SGD", "Republic of Singapore", "Sovereign", "SG", "AAA", 3.375, date(2034, 8, 1), 7.3, .01, 99.69, .05, 85, 2.0e8),
    ("UST-2044", "US Treasury Bond 4.625% 2044", FI, "govt_bond", "USD", "United States Treasury", "Sovereign", "US", "AA+", 4.625, date(2044, 5, 15), 12.9, .01, 100.56, .09, 80, 1.0e9),
    ("AAPL-2033", "Apple Inc 3.750% Senior Notes 2033", FI, "corporate_bond", "USD", "Apple", "Technology", "US", "AA+", 3.75, date(2033, 2, 8), 6.3, .01, 103.96, .05, 74, 5.0e7),
    ("VZ-2036", "Verizon Communications 5.012% 2036", FI, "corporate_bond", "USD", "Verizon", "Communication Services", "US", "BBB+", 5.012, date(2036, 4, 15), 8.0, .01, 91.78, .06, 57, 3.0e7),
    ("IRS-USD-5Y", "USD 5Y Interest Rate Swap (pay fixed)", DV, "otc_swap", "USD", "OTC Swap CCP", "Rates", "US", None, None, date(2031, 3, 15), -4.4, 1, 101.07, .03, None, 1.0e9),
    ("FWD-SGDUSD-3M", "SGD/USD 3M FX Forward", DV, "fx_forward", "SGD", "OTC FX", "FX", "SG", None, None, date(2027, 1, 28), None, 1, 1.0, .05, None, 1.0e10),
    ("NKM6", "Nikkei 225 Mini Future Jun26", DV, "future", "JPY", "OSE", "Index", "JP", None, None, date(2027, 6, 11), None, 100, 38450.0, .22, None, 2.0e5),
    # Philippines (BDO TIG book)
    ("BDO", "BDO Unibank Inc", EQ, "cash_equity", "PHP", "BDO Unibank", "Financials", "PH", None, None, None, None, 1, 148.50, .24, 62, 2.0e6),
    ("SM", "SM Investments Corp", EQ, "cash_equity", "PHP", "SM Group", "Industrials", "PH", None, None, None, None, 1, 845.00, .26, 58, 6.0e5),
    ("ALI", "Ayala Land Inc", EQ, "cash_equity", "PHP", "Ayala Group", "Real Estate", "PH", None, None, None, None, 1, 27.40, .30, 64, 1.5e7),
    ("AC", "Ayala Corporation", EQ, "cash_equity", "PHP", "Ayala Group", "Industrials", "PH", None, None, None, None, 1, 612.00, .25, 66, 4.0e5),
    ("JFC", "Jollibee Foods Corp", EQ, "cash_equity", "PHP", "Jollibee", "Consumer Discretionary", "PH", None, None, None, None, 1, 232.80, .28, 55, 1.2e6),
    ("TEL", "PLDT Inc", EQ, "cash_equity", "PHP", "PLDT", "Communication Services", "PH", None, None, None, None, 1, 1290.0, .22, 52, 1.0e5),
    ("ICT", "International Container Terminal Services", EQ, "cash_equity", "PHP", "ICTSI", "Industrials", "PH", None, None, None, None, 1, 402.00, .27, 60, 8.0e5),
    ("MER", "Manila Electric Co", EQ, "cash_equity", "PHP", "Meralco", "Utilities", "PH", None, None, None, None, 1, 520.00, .18, 57, 2.0e5),
    ("RTB-2029", "PH Retail Treasury Bond 6.250% 2029", FI, "govt_bond", "PHP", "Republic of the Philippines", "Sovereign", "PH", "BBB+", 6.25, date(2029, 2, 28), 2.9, .01, 101.35, .04, 60, 5.0e8),
    ("FXTN-2031", "PH Fixed Rate Treasury Note 6.375% 2031", FI, "govt_bond", "PHP", "Republic of the Philippines", "Sovereign", "PH", "BBB+", 6.375, date(2031, 10, 19), 4.6, .01, 100.80, .05, 60, 4.0e8),
    ("FXTN-2036", "PH Fixed Rate Treasury Note 6.750% 2036", FI, "govt_bond", "PHP", "Republic of the Philippines", "Sovereign", "PH", "BBB+", 6.75, date(2036, 9, 24), 7.4, .01, 102.10, .07, 60, 3.0e8),
    ("SMICPM-2030", "SM Investments 5.900% Bond 2030", FI, "corporate_bond", "PHP", "SM Group", "Industrials", "PH", "BBB", 5.9, date(2030, 7, 15), 3.6, .01, 99.25, .05, 58, 4.0e7),
    ("ALIPM-2032", "Ayala Land 6.100% Bond 2032", FI, "corporate_bond", "PHP", "Ayala Group", "Real Estate", "PH", "BBB", 6.1, date(2032, 4, 20), 5.1, .01, 100.40, .05, 64, 3.0e7),
    ("PHTB-364D", "PH Treasury Bill 364-Day", FI, "govt_bond", "PHP", "Republic of the Philippines", "Sovereign", "PH", "BBB+", 0.0, date(2027, 9, 22), 0.9, .01, 94.30, .01, 60, 1.0e9),
    ("ROP-2034", "Republic of the Philippines USD 5.000% 2034", FI, "govt_bond", "USD", "Republic of the Philippines", "Sovereign", "PH", "BBB+", 5.0, date(2034, 7, 17), 7.0, .01, 100.90, .06, 60, 5.0e7),
]

ENTITIES = [("PH", "BDO Trust & Investments Group (PH)", "PHP"), ("SG", "Singapore Booking Centre", "SGD"),
            ("US", "US Advisory Entity", "USD")]

MODELS = {
    "PH-BAL": ("PH Balanced Trust Model", "50% PSEi / 50% BPI Govt Index", 2.0,
               {"BDO": 8, "SM": 6, "ALI": 5, "AC": 4, "ICT": 6, "MER": 5, "JFC": 5, "TEL": 6,
                "RTB-2029": 14, "FXTN-2031": 14, "FXTN-2036": 8, "SMICPM-2030": 5, "ALIPM-2032": 4, "PHTB-364D": 7,
                "CASH": 3}),
    "PH-INC": ("PH Fixed Income UITF Model", "BPI Philippine Govt Bond Index", 1.5,
               {"RTB-2029": 22, "FXTN-2031": 22, "FXTN-2036": 12, "SMICPM-2030": 12, "ALIPM-2032": 12,
                "PHTB-364D": 13, "ROP-2034": 5, "CASH": 2}),
    "PH-EQ": ("PH Equity Index-Plus Model", "PSEi", 2.5,
              {"BDO": 14, "SM": 13, "ALI": 6, "AC": 6, "ICT": 14, "MER": 13, "JFC": 15, "TEL": 14, "CASH": 5}),
    "US-GROWTH": ("US Large-Cap Growth Model", "S&P 500", 2.0,
                  {"MSFT": 14, "NVDA": 12, "AMZN": 11, "GOOGL": 10, "META": 8, "AAPL": 12, "V": 8, "JPM": 7, "UNH": 6,
                   "JNJ": 5, "CASH": 7}),
}

# code, name, entity, ccy, aum, model, mandate, risk_profile, tax, restrictions, drift_seed
ACCOUNTS = [
    ("PH-BAL-01", "Santos Family Balanced Trust", "PH", "PHP", 2_450_000_000, "PH-BAL", "Discretionary Trust", "Moderate", "TAXABLE", ["JFC"]),
    ("PH-BAL-02", "Manila Holdings Balanced IMA", "PH", "PHP", 1_120_000_000, "PH-BAL", "Investment Management Account", "Moderate", "TAXABLE", []),
    ("PH-INC-01", "BDO Peso Bond UITF (demo)", "PH", "PHP", 8_600_000_000, "PH-INC", "UITF", "Conservative", "TAXABLE", []),
    ("PH-RET-01", "Corp Employees Retirement Fund", "PH", "PHP", 5_300_000_000, "PH-INC", "Employee Retirement Plan", "Conservative", "EXEMPT", []),
    ("PH-EQ-01", "Equity Index-Plus Trust", "PH", "PHP", 3_900_000_000, "PH-EQ", "Discretionary Trust", "Aggressive", "TAXABLE", []),
    ("US-GRW-01", "Global Growth Sleeve", "US", "USD", 185_000_000, "US-GROWTH", "Discretionary", "Growth", "TAXABLE", ["XOM"]),
]

SG_BOOK = {
    # code: (name, aum SGD, cash SGD, [(symbol, qty, avg_px)])
    "APAC-EQ-01": ("APAC Equity Overlay", 742_500_000, 735_000_000, [("DBSSP-2031", 5_000_000, 96.249), ("XOM", 10_400, 64.45 * 1.0 + 0), ("IRS-USD-5Y", 1_200_000, 100.62), ("Z74", 520_000, 3.71)]),
    "EM-DEBT-07": ("EM Debt Opportunities", 354_100_000, 350_000_000, [("SGGB-2034", 1_600_000, 99.54), ("FWD-SGDUSD-3M", 162_000_000, 0.9962)]),
    "GLB-AGG-04": ("Global Aggregate", 965_200_000, 958_000_000, [("AAPL", 8_000, 100.79 + 130), ("NKM6", 1_600, 38_610.0)]),
    "SGD-CR-03": ("SGD Credit", 430_750_000, 400_000_000, [("SGGB-2029", 2_800_000, 102.093), ("AAPL-2033", 11_000_000, 103.981), ("VZ-2036", 11_000_000, 91.523)]),
    "SGD-CR-03A": ("SGD Credit Long/Short", 145_300_000, 152_000_000, [("Z74", -15_000, 3.84), ("UST-2044", -2_000_000, 100.278)]),
    "MULTI-06": ("Multi-Asset Income", 612_900_000, 605_000_000, [("MSFT", 9_000, 287.86 + 225), ("D05", 24_000, 43.2)]),
}

RULES = [
    ("REG-PH-ISSUER", "Single-issuer/group limit 15% of NAV (govt securities exempt)", "REGULATORY", "MAX_ISSUER_WEIGHT", "ENTITY", "PH", {"limit_pct": 15, "exempt_sectors": ["Sovereign"]}, Severity.HARD),
    ("REG-PH-RATING", "Minimum credit rating BBB- for fixed income", "REGULATORY", "MIN_RATING", "ENTITY", "PH", {"min_rating": "BBB-"}, Severity.HARD),
    ("REG-PH-FX", "Foreign-currency exposure max 20% of NAV", "REGULATORY", "MAX_FX_EXPOSURE", "ENTITY", "PH", {"limit_pct": 20}, Severity.HARD),
    ("INT-NO-SHORT-PH", "No short positions in cash securities", "INTERNAL", "NO_SHORT_CASH", "ENTITY", "PH", {}, Severity.HARD),
    ("INT-NO-SHORT-US", "No short positions in cash securities", "INTERNAL", "NO_SHORT_CASH", "ENTITY", "US", {}, Severity.HARD),
    ("INT-POS-20", "Single position soft cap 20% of NAV", "INTERNAL", "MAX_POSITION_WEIGHT", "GLOBAL", None, {"limit_pct": 20, "exempt_sectors": ["Sovereign"]}, Severity.SOFT),
    ("INT-LEV-300", "Gross exposure max 300% of NAV", "INTERNAL", "MAX_GROSS_LEVERAGE", "GLOBAL", None, {"limit_pct": 300}, Severity.HARD),
    ("INT-CASH-1", "Minimum liquidity buffer 1% of NAV", "INTERNAL", "MIN_CASH_PCT", "ENTITY", "PH", {"min_pct": 1}, Severity.SOFT),
    ("INT-SANCTIONS", "Sanctions & restricted list", "INTERNAL", "RESTRICTED_LIST", "GLOBAL", None, {"symbols": [], "issuers": ["Sanctioned Holdings Ltd"]}, Severity.HARD),
    ("MAN-BAL-EQ", "Balanced mandate equity band 30-60%", "MANDATE", "ASSET_CLASS_BAND", "ACCOUNT", "PH-BAL-01", {"asset_class": "EQ", "min_pct": 30, "max_pct": 60}, Severity.HARD),
    ("MAN-BAL-FI", "Balanced mandate fixed income band 35-65%", "MANDATE", "ASSET_CLASS_BAND", "ACCOUNT", "PH-BAL-01", {"asset_class": "FI", "min_pct": 35, "max_pct": 65}, Severity.HARD),
    ("MAN-INC-DUR", "Bond UITF duration max 6.0 years", "MANDATE", "MAX_DURATION", "ACCOUNT", "PH-INC-01", {"limit_years": 6.0}, Severity.HARD),
    ("MAN-INC-EQ", "Bond UITF: no equities", "MANDATE", "ASSET_CLASS_BAND", "ACCOUNT", "PH-INC-01", {"asset_class": "EQ", "min_pct": 0, "max_pct": 0}, Severity.HARD),
    ("MAN-RET-DUR", "Retirement fund duration max 5.5 years", "MANDATE", "MAX_DURATION", "ACCOUNT", "PH-RET-01", {"limit_years": 5.5}, Severity.SOFT),
    ("MAN-GRW-ESG", "Growth sleeve ESG score floor 55", "MANDATE", "MIN_ESG_SCORE", "ACCOUNT", "US-GRW-01", {"min_score": 55}, Severity.HARD),
    ("MAN-SGCR-DUR", "SGD Credit duration max 7.5 years", "MANDATE", "MAX_DURATION", "ACCOUNT", "SGD-CR-03", {"limit_years": 7.5}, Severity.SOFT),
]

USERS = [
    ("admin", "Platform Admin", Role.ADMIN),
    ("pm.santos", "Maria Santos", Role.PM),
    ("pm.reyes", "Jose Reyes", Role.PM),
    ("trader.lim", "Daniel Lim", Role.TRADER),
    ("compliance.cruz", "Ana Cruz", Role.COMPLIANCE),
    ("risk.tan", "Kevin Tan", Role.RISK),
    ("ops.garcia", "Liza Garcia", Role.OPS),
    ("viewer", "Read Only", Role.VIEWER),
]


def _history(rng: np.random.Generator, last: float, vol: float, n: int, mkt: np.ndarray, beta: float) -> np.ndarray:
    daily = vol / math.sqrt(252)
    idio = rng.normal(0, daily * math.sqrt(max(1 - beta**2 * 0.5, 0.2)), n)
    rets = beta * mkt * (daily / 0.012) * 0.7 + idio + 0.06 / 252
    path = np.cumprod(1 + rets[::-1])  # backwards from today
    return np.concatenate([[last], last / path])[::-1][1:]


def business_days(end: date, n: int) -> list[date]:
    out, d = [], end
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d)
        d -= timedelta(days=1)
    return out[::-1]


def seed(db: Session) -> bool:
    if db.query(Entity).count():
        return False
    rng = np.random.default_rng(42)
    prng = random.Random(7)
    pwd = os.environ.get("MPOWER_DEMO_PASSWORD", "Mpower@2026!")

    for c, n, rc in ENTITIES:
        db.add(Entity(code=c, name=n, reporting_ccy=rc))
    for ccy, r in FX.items():
        db.add(FxRate(ccy=ccy, usd_per_unit=r))
    for u, n, r in USERS:
        db.add(User(username=u, full_name=n, email=f"{u}@example.com", password_hash=hash_password(pwd), role=r, entities=[]))

    insts: dict[str, Instrument] = {}
    for (sym, name, ac, typ, ccy, iss, sec, cty, rat, cpn, mat, dur, size, px, vol, esg, adv) in INSTRUMENTS:
        prev = round(px * (1 - prng.uniform(-0.004, 0.004)), 6)
        i = Instrument(symbol=sym, name=name, asset_class=ac, inst_type=typ, ccy=ccy, issuer=iss, sector=sec, country=cty,
                       rating=rat, coupon=cpn, maturity=mat, duration=dur, contract_size=size, price=px, prev_close=prev,
                       vol=vol, esg_score=esg, adv=adv)
        db.add(i)
        insts[sym] = i
    db.flush()

    days = business_days(datetime.now(timezone.utc).date() - timedelta(days=1), 520)
    mkt = rng.normal(0, 0.011, len(days))
    for i in insts.values():
        beta = 1.0 if i.asset_class == EQ else (-0.25 if i.asset_class == FI else 0.3)
        series = _history(rng, i.prev_close, i.vol, len(days), mkt, beta)
        db.bulk_save_objects([PriceHistory(instrument_id=i.id, d=d, close=float(c)) for d, c in zip(days, series)])

    models: dict[str, ModelPortfolio] = {}
    for code, (name, bm, tol, w) in MODELS.items():
        m = ModelPortfolio(code=code, name=name, benchmark=bm, tolerance_pct=tol, description=f"{name} - strategic allocation")
        m.versions.append(ModelVersion(version=1, weights=w, status="ACTIVE", rationale="Initial strategic allocation",
                                       created_by="pm.santos", approved_by="compliance.cruz",
                                       effective_at=datetime.now(timezone.utc)))
        db.add(m)
        models[code] = m
    db.flush()

    def fx(amount: float, frm: str, to: str) -> float:
        return amount * FX[frm] / FX[to]

    for code, name, ent, ccy, aum, model, mandate, prof, tax, restr in ACCOUNTS:
        a = Account(code=code, name=name, entity_code=ent, base_ccy=ccy, aum=aum, model_id=models[model].id,
                    mandate=mandate, risk_profile=prof, tax_status=tax, restrictions=restr)
        db.add(a)
        db.flush()
        weights = MODELS[model][3]
        lines = {s: w * (1 + prng.uniform(-0.3, 0.3)) for s, w in weights.items() if s != "CASH" and s not in restr}
        scale = (100 - weights.get("CASH", 0) - prng.uniform(0, 1.5)) / sum(lines.values())  # realistic drift
        invested = 0.0
        for sym, wt in lines.items():
            i = insts[sym]
            val_base = aum * wt * scale / 100
            unit = fx(i.price * i.contract_size, i.ccy, ccy)
            lot = 100 if i.asset_class == EQ else 10_000
            qty = max(lot, round(val_base / unit / lot) * lot)
            avg = i.price * (1 - prng.uniform(-0.12, 0.10))
            db.add(Position(account_id=a.id, instrument_id=i.id, qty=qty, avg_px=round(avg, 4)))
            invested += qty * unit
        db.add(CashBalance(account_id=a.id, ccy=ccy, amount=round(aum - invested, 2)))

    for code, (name, aum, cash, holdings) in SG_BOOK.items():
        a = Account(code=code, name=name, entity_code="SG", base_ccy="SGD", aum=aum, mandate="Institutional Mandate",
                    risk_profile="Institutional", restrictions=[])
        db.add(a)
        db.flush()
        for sym, qty, avg in holdings:
            db.add(Position(account_id=a.id, instrument_id=insts[sym].id, qty=qty, avg_px=avg))
        db.add(CashBalance(account_id=a.id, ccy="SGD", amount=cash))

    for code, name, cat, typ, scope, ref, params, sev in RULES:
        r = ComplianceRule(code=code, name=name, category=cat, rule_type=typ, scope=scope, scope_ref=ref, params=params,
                           severity=sev, updated_by="compliance.cruz")
        db.add(r)
        db.flush()
        db.add(RuleVersion(rule_id=r.id, version=1, changed_by="compliance.cruz",
                           snapshot={"name": name, "rule_type": typ, "scope": scope, "scope_ref": ref, "params": params,
                                     "severity": sev.value, "is_active": True}))
    db.commit()
    return True
