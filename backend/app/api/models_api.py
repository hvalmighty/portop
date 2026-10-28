import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..audit import audit
from ..db import get_db
from ..models import Account, Instrument, ModelPortfolio, ModelVersion, OrderSide, User
from ..schemas import ModelIn, ModelVersionIn, RebalanceIn
from ..security import require
from ..services.compliance import load_snapshot
from ..services.rebalance import accounts_for_model, active_version, drift, propose
from ..services.trading import create_order
from ..services.valuation import Fx
from .common import get_account

router = APIRouter(tags=["models"])


def version_out(v: ModelVersion) -> dict:
    return {"id": v.id, "version": v.version, "weights": v.weights, "status": v.status, "rationale": v.rationale,
            "created_by": v.created_by, "approved_by": v.approved_by, "created_at": v.created_at.isoformat(),
            "effective_at": v.effective_at.isoformat() if v.effective_at else None}


def model_out(db: Session, m: ModelPortfolio, detail: bool = False) -> dict:
    av = active_version(m)
    out = {"id": m.id, "code": m.code, "name": m.name, "benchmark": m.benchmark, "tolerance_pct": m.tolerance_pct,
           "active_version": av.version if av else None, "weights": av.weights if av else {},
           "accounts": [a.code for a in accounts_for_model(db, m.id)],
           "pending_versions": sum(1 for v in m.versions if v.status == "DRAFT")}
    if detail:
        out["versions"] = [version_out(v) for v in reversed(m.versions)]
    return out


def _model(db: Session, code: str) -> ModelPortfolio:
    m = db.query(ModelPortfolio).filter(ModelPortfolio.code == code).one_or_none()
    if m is None:
        raise HTTPException(404, f"Model {code} not found")
    return m


def _validate_symbols(db: Session, weights: dict) -> None:
    syms = [s for s in weights if s != "CASH"]
    found = {i.symbol for i in db.query(Instrument).filter(Instrument.symbol.in_(syms))}
    missing = sorted(set(syms) - found)
    if missing:
        raise HTTPException(422, f"Unknown instruments: {', '.join(missing)}")


@router.get("/models")
def list_models(_: User = Depends(require("portfolio:read")), db: Session = Depends(get_db)):
    return [model_out(db, m) for m in db.query(ModelPortfolio).order_by(ModelPortfolio.code)]


@router.get("/models/{code}")
def get_model(code: str, _: User = Depends(require("portfolio:read")), db: Session = Depends(get_db)):
    return model_out(db, _model(db, code), detail=True)


@router.post("/models", status_code=201)
def create_model(body: ModelIn, user: User = Depends(require("model:write")), db: Session = Depends(get_db)):
    if db.query(ModelPortfolio).filter(ModelPortfolio.code == body.code).count():
        raise HTTPException(409, "Model code already exists")
    ModelVersionIn(weights=body.weights, rationale=body.rationale)  # reuse validation
    _validate_symbols(db, body.weights)
    m = ModelPortfolio(code=body.code, name=body.name, benchmark=body.benchmark, tolerance_pct=body.tolerance_pct)
    m.versions.append(ModelVersion(version=1, weights=body.weights, rationale=body.rationale, status="DRAFT",
                                   created_by=user.username))
    db.add(m)
    db.flush()
    audit(db, user.username, "MODEL_CREATE", "model", m.code, after={"weights": body.weights})
    db.commit()
    return model_out(db, m, True)


@router.post("/models/{code}/versions", status_code=201)
def propose_version(code: str, body: ModelVersionIn, user: User = Depends(require("model:write")),
                    db: Session = Depends(get_db)):
    m = _model(db, code)
    _validate_symbols(db, body.weights)
    v = ModelVersion(version=max((x.version for x in m.versions), default=0) + 1, weights=body.weights,
                     rationale=body.rationale, status="DRAFT", created_by=user.username)
    m.versions.append(v)
    db.flush()
    audit(db, user.username, "MODEL_VERSION_PROPOSE", "model", f"{code}/v{v.version}", after={"weights": body.weights})
    db.commit()
    return model_out(db, m, True)


@router.post("/models/{code}/versions/{version}/approve")
def approve_version(code: str, version: int, user: User = Depends(require("model:approve")),
                    db: Session = Depends(get_db)):
    m = _model(db, code)
    v = next((x for x in m.versions if x.version == version), None)
    if v is None or v.status != "DRAFT":
        raise HTTPException(409, "Only DRAFT versions can be approved")
    if v.created_by == user.username:
        raise HTTPException(403, "Segregation of duties: the proposer cannot approve the version")
    for x in m.versions:
        if x.status == "ACTIVE":
            x.status = "RETIRED"
    v.status, v.approved_by, v.effective_at = "ACTIVE", user.username, datetime.now(timezone.utc)
    audit(db, user.username, "MODEL_VERSION_APPROVE", "model", f"{code}/v{version}")
    db.commit()
    return model_out(db, m, True)


@router.get("/models/{code}/drift")
def model_drift(code: str, user: User = Depends(require("portfolio:read")), db: Session = Depends(get_db)):
    m = _model(db, code)
    fx = Fx.load(db)
    out = []
    for a in accounts_for_model(db, m.id):
        try:
            get_account(db, user, a.code)
        except HTTPException:
            continue
        d = drift(db, load_snapshot(db, a, fx), m)
        out.append({"account": a.code, "name": a.name, "nav": d.get("nav", 0), "max_abs_drift": d["max_abs_drift"],
                    "out_of_band": d["out_of_band"], "rows": d["rows"]})
    return {"model": m.code, "tolerance_pct": m.tolerance_pct, "accounts": out}


@router.post("/rebalance/preview")
def rebalance_preview(body: RebalanceIn, user: User = Depends(require("portfolio:read")), db: Session = Depends(get_db)):
    fx = Fx.load(db)
    out = []
    for code in body.accounts:
        a = get_account(db, user, code)
        if a.model is None:
            out.append({"account": code, "error": "No model assigned"})
            continue
        out.append(propose(db, load_snapshot(db, a, fx), a.model, body.mode, body.min_trade_value))
    return {"proposals": out}


@router.post("/rebalance/submit", status_code=201)
def rebalance_submit(body: RebalanceIn, user: User = Depends(require("rebalance:run")), db: Session = Depends(get_db)):
    """Generate proposals and stage them as orders for checker approval (one batch id per run)."""
    fx = Fx.load(db)
    batch = f"RB-{uuid.uuid4().hex[:10].upper()}"
    created, skipped = [], []
    for code in body.accounts:
        a: Account = get_account(db, user, code)
        if a.model is None:
            skipped.append({"account": code, "reason": "No model assigned"})
            continue
        prop = propose(db, load_snapshot(db, a, fx), a.model, body.mode, body.min_trade_value)
        for line in prop["lines"]:
            inst = db.get(Instrument, line["instrument_id"])
            try:
                o = create_order(db, user, a, inst, OrderSide(line["side"]), line["qty"], source="REBALANCE",
                                 batch_id=batch, override_reason="Model rebalance (soft limits reviewed by checker)",
                                 commit=False)
                db.flush()
                created.append(o.id)
            except HTTPException as exc:
                skipped.append({"account": code, "symbol": line["symbol"], "reason": exc.detail})
    audit(db, user.username, "REBALANCE_SUBMIT", "batch", batch, after={"orders": created, "skipped": len(skipped)})
    db.commit()
    return {"batch_id": batch, "orders_created": len(created), "order_ids": created, "skipped": skipped}
