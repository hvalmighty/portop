from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session, joinedload

from ..audit import audit, snapshot
from ..db import get_db
from ..models import Account, Breach, BreachStatus, ComplianceRule, RuleVersion, User
from ..schemas import BreachAction, RuleIn, RuleUpdate
from ..security import allowed_entities, require
from ..services.compliance import RULE_TYPES, applicable_rules, evaluate_snapshot, load_snapshot, run_post_trade_scan
from ..services.valuation import Fx, load_accounts
from .common import check_entity, get_account

router = APIRouter(prefix="/compliance", tags=["compliance"])


def rule_out(r: ComplianceRule) -> dict:
    return {"id": r.id, "code": r.code, "name": r.name, "category": r.category, "rule_type": r.rule_type,
            "scope": r.scope, "scope_ref": r.scope_ref, "params": r.params, "severity": r.severity.value,
            "is_active": r.is_active, "version": r.version, "updated_by": r.updated_by,
            "updated_at": r.updated_at.isoformat()}


def breach_out(b: Breach) -> dict:
    return {"id": b.id, "rule": b.rule.code, "rule_name": b.rule.name, "category": b.rule.category,
            "severity": b.rule.severity.value, "account": b.account.code, "kind": b.kind, "subject": b.subject,
            "observed": b.observed, "limit": b.limit, "message": b.message, "status": b.status.value,
            "detected_at": b.detected_at.isoformat(), "resolved_at": b.resolved_at.isoformat() if b.resolved_at else None,
            "notes": b.notes or [],
            "age_hours": (datetime.now(timezone.utc) - _aware(b.detected_at)).total_seconds() / 3600}


def _aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


@router.get("/rule-types")
def rule_types(_: User = Depends(require("compliance:read"))):
    return RULE_TYPES


@router.get("/rules")
def list_rules(_: User = Depends(require("compliance:read")), db: Session = Depends(get_db)):
    return [rule_out(r) for r in db.query(ComplianceRule).order_by(ComplianceRule.category, ComplianceRule.code)]


@router.get("/rules/{rid}/history")
def rule_history(rid: int, _: User = Depends(require("compliance:read")), db: Session = Depends(get_db)):
    return [{"version": v.version, "snapshot": v.snapshot, "changed_by": v.changed_by, "changed_at": v.changed_at.isoformat()}
            for v in db.query(RuleVersion).filter(RuleVersion.rule_id == rid).order_by(RuleVersion.version.desc())]


def _version(db: Session, r: ComplianceRule, user: str) -> None:
    db.add(RuleVersion(rule_id=r.id, version=r.version, changed_by=user, snapshot={
        "name": r.name, "rule_type": r.rule_type, "scope": r.scope, "scope_ref": r.scope_ref, "params": r.params,
        "severity": r.severity.value, "is_active": r.is_active}))


@router.post("/rules", status_code=201)
def create_rule(body: RuleIn, user: User = Depends(require("compliance:write")), db: Session = Depends(get_db)):
    if db.query(ComplianceRule).filter(ComplianceRule.code == body.code).count():
        raise HTTPException(409, "Rule code already exists")
    if body.scope != "GLOBAL" and not body.scope_ref:
        raise HTTPException(422, "scope_ref required for ENTITY/ACCOUNT scope")
    r = ComplianceRule(**body.model_dump(), updated_by=user.username)
    db.add(r)
    db.flush()
    _version(db, r, user.username)
    audit(db, user.username, "RULE_CREATE", "rule", r.code, after=snapshot(r))
    db.commit()
    return rule_out(r)


@router.patch("/rules/{rid}")
def update_rule(rid: int, body: RuleUpdate, user: User = Depends(require("compliance:write")), db: Session = Depends(get_db)):
    r = db.get(ComplianceRule, rid)
    if r is None:
        raise HTTPException(404, "Rule not found")
    before = snapshot(r)
    for k, v in body.model_dump(exclude_none=True).items():
        setattr(r, k, v)
    r.version += 1
    r.updated_by, r.updated_at = user.username, datetime.now(timezone.utc)
    _version(db, r, user.username)
    audit(db, user.username, "RULE_UPDATE", "rule", r.code, before, snapshot(r))
    db.commit()
    return rule_out(r)


@router.get("/breaches")
def list_breaches(
    status: BreachStatus | None = None, account: str | None = None, limit: int = Query(500, le=5000),
    user: User = Depends(require("compliance:read")), db: Session = Depends(get_db),
):
    q = db.query(Breach).options(joinedload(Breach.rule), joinedload(Breach.account)).join(Account)
    allowed = allowed_entities(user)
    if allowed is not None:
        q = q.filter(Account.entity_code.in_(allowed))
    if status:
        q = q.filter(Breach.status == status)
    if account:
        q = q.filter(Account.code == account)
    return [breach_out(b) for b in q.order_by(Breach.detected_at.desc()).limit(limit)]


@router.post("/breaches/{bid}")
def act_on_breach(bid: int, body: BreachAction, user: User = Depends(require("breach:manage")), db: Session = Depends(get_db)):
    b = db.get(Breach, bid, options=[joinedload(Breach.rule), joinedload(Breach.account)])
    if b is None:
        raise HTTPException(404, "Breach not found")
    get_account(db, user, b.account.code)
    before = snapshot(b)
    now = datetime.now(timezone.utc)
    b.notes = [*(b.notes or []), {"ts": now.isoformat(), "user": user.username, "text": body.note,
                                  "status": body.status}]
    if body.status:
        b.status = BreachStatus(body.status)
        if body.status == "RESOLVED":
            b.resolved_at = now
    audit(db, user.username, "BREACH_UPDATE", "breach", b.id, before, snapshot(b))
    db.commit()
    return breach_out(b)


@router.post("/scan")
def scan(entity: str | None = None, user: User = Depends(require("compliance:read")), db: Session = Depends(get_db)):
    check_entity(user, entity)
    res = run_post_trade_scan(db, load_accounts(db, entity, allowed_entities(user)))
    audit(db, user.username, "COMPLIANCE_SCAN", "compliance", entity or "ALL", after=res)
    db.commit()
    return res


@router.get("/accounts/{code}")
def account_status(code: str, user: User = Depends(require("compliance:read")), db: Session = Depends(get_db)):
    a = get_account(db, user, code)
    res = evaluate_snapshot(applicable_rules(db, a), load_snapshot(db, a, Fx.load(db)))
    return {"account": code, "results": [r.__dict__ for r in res],
            "failing": sum(1 for r in res if not r.passed)}
