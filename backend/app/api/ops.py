import csv
import io
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session, joinedload

from ..audit import audit
from ..db import get_db
from ..models import Account, Alert, AuditLog, Breach, CashBalance, Position, Trade, User
from ..security import allowed_entities, require
from ..services.valuation import load_accounts, reporting_ccy, value_accounts
from .common import check_entity, get_account

router = APIRouter(tags=["back-office"])

MAX_UPLOAD_BYTES = 5 * 1024 * 1024


def _scoped(q, user: User):
    allowed = allowed_entities(user)
    return q.filter(Account.entity_code.in_(allowed)) if allowed is not None else q


def trade_out(t: Trade) -> dict:
    return {"id": t.id, "order_id": t.order_id, "account": t.account.code, "symbol": t.instrument.symbol,
            "name": t.instrument.name, "side": t.side.value, "qty": t.qty, "price": t.price, "gross": t.gross,
            "fees": t.fees, "ccy": t.instrument.ccy, "trade_date": t.trade_date.isoformat(),
            "settle_date": t.settle_date.isoformat(), "settle_status": t.settle_status}


@router.get("/trades")
def trades(account: str | None = None, settle_status: str | None = None, limit: int = Query(500, le=5000),
           user: User = Depends(require("ops:read")), db: Session = Depends(get_db)):
    q = _scoped(db.query(Trade).options(joinedload(Trade.account), joinedload(Trade.instrument)).join(Account), user)
    if account:
        q = q.filter(Account.code == account)
    if settle_status:
        q = q.filter(Trade.settle_status == settle_status)
    return [trade_out(t) for t in q.order_by(Trade.id.desc()).limit(limit)]


@router.post("/trades/{tid}/settle")
def settle(tid: int, user: User = Depends(require("ops:write")), db: Session = Depends(get_db)):
    t = db.get(Trade, tid, options=[joinedload(Trade.account), joinedload(Trade.instrument)])
    if t is None:
        raise HTTPException(404, "Trade not found")
    get_account(db, user, t.account.code)
    if t.settle_status == "SETTLED":
        raise HTTPException(409, "Already settled")
    t.settle_status = "SETTLED"
    audit(db, user.username, "TRADE_SETTLE", "trade", t.id, {"settle_status": "PENDING"}, {"settle_status": "SETTLED"})
    db.commit()
    return trade_out(t)


@router.get("/cash")
def cash(user: User = Depends(require("ops:read")), db: Session = Depends(get_db)):
    rows = _scoped(db.query(CashBalance, Account).join(Account, CashBalance.account_id == Account.id), user).all()
    return [{"account": a.code, "entity": a.entity_code, "ccy": c.ccy, "amount": c.amount} for c, a in rows]


@router.post("/reconciliation")
async def reconcile(file: UploadFile = File(...), tolerance: float = 0.0, user: User = Depends(require("ops:read")),
                    db: Session = Depends(get_db)):
    """Compare a custodian holdings statement (CSV: account,symbol,qty) with the book of record."""
    raw = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(raw) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, "File exceeds 5 MB limit")
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise HTTPException(422, "File must be UTF-8 CSV") from exc
    reader = csv.DictReader(io.StringIO(text))
    need = {"account", "symbol", "qty"}
    if not reader.fieldnames or not need.issubset({f.strip().lower() for f in reader.fieldnames}):
        raise HTTPException(422, "CSV must have columns: account,symbol,qty")
    custodian: dict[tuple[str, str], float] = {}
    errors = []
    for n, row in enumerate(reader, start=2):
        row = {k.strip().lower(): (v or "").strip() for k, v in row.items() if k}
        try:
            key = (row["account"], row["symbol"])
            custodian[key] = custodian.get(key, 0.0) + float(row["qty"].replace(",", ""))
        except ValueError:
            errors.append({"line": n, "error": f"Invalid qty '{row.get('qty')}'"})
    codes = sorted({k[0] for k in custodian})
    accts = {a.code: a for a in db.query(Account).filter(Account.code.in_(codes))}
    for c in codes:
        if c not in accts:
            errors.append({"line": None, "error": f"Unknown account {c}"})
        else:
            get_account(db, user, c)
    book: dict[tuple[str, str], float] = {}
    for p in db.query(Position).options(joinedload(Position.instrument), joinedload(Position.account)).filter(
            Position.account_id.in_([a.id for a in accts.values()])):
        if abs(p.qty) > 1e-9:
            book[(p.account.code, p.instrument.symbol)] = p.qty
    breaks, matched = [], 0
    for key in sorted(set(book) | set(custodian)):
        b, c = book.get(key, 0.0), custodian.get(key, 0.0)
        if abs(b - c) <= tolerance:
            matched += 1
        else:
            breaks.append({"account": key[0], "symbol": key[1], "book_qty": b, "custodian_qty": c, "diff": c - b,
                           "type": "MISSING_AT_CUSTODIAN" if key not in custodian else
                           "MISSING_IN_BOOK" if key not in book else "QTY_MISMATCH"})
    audit(db, user.username, "RECONCILIATION", "file", file.filename or "upload",
          after={"matched": matched, "breaks": len(breaks), "errors": len(errors)})
    db.commit()
    return {"file": file.filename, "matched": matched, "breaks": breaks, "errors": errors,
            "run_at": datetime.now(timezone.utc).isoformat()}


@router.get("/audit")
def audit_log(username: str | None = None, action: str | None = None, object_type: str | None = None,
              limit: int = Query(300, le=5000), _: User = Depends(require("audit:read")), db: Session = Depends(get_db)):
    q = db.query(AuditLog)
    if username:
        q = q.filter(AuditLog.username == username)
    if action:
        q = q.filter(AuditLog.action == action)
    if object_type:
        q = q.filter(AuditLog.object_type == object_type)
    return [{"id": r.id, "ts": r.ts.isoformat(), "username": r.username, "action": r.action,
             "object_type": r.object_type, "object_id": r.object_id, "before": r.before, "after": r.after,
             "request_id": r.request_id, "ip": r.ip} for r in q.order_by(AuditLog.id.desc()).limit(limit)]


@router.get("/alerts")
def alerts(unread: bool = False, limit: int = Query(100, le=1000), user: User = Depends(require("portfolio:read")),
           db: Session = Depends(get_db)):
    q = db.query(Alert)
    if unread:
        q = q.filter(Alert.is_read.is_(False))
    allowed = allowed_entities(user)
    rows = q.order_by(Alert.id.desc()).limit(limit).all()
    if allowed is not None:
        codes = {a.code for a in db.query(Account).filter(Account.entity_code.in_(allowed))}
        rows = [r for r in rows if r.account_code is None or r.account_code in codes]
    return [{"id": r.id, "level": r.level, "category": r.category, "message": r.message, "account": r.account_code,
             "is_read": r.is_read, "created_at": r.created_at.isoformat()} for r in rows]


@router.post("/alerts/read-all")
def alerts_read(_: User = Depends(require("portfolio:read")), db: Session = Depends(get_db)):
    n = db.query(Alert).filter(Alert.is_read.is_(False)).update({"is_read": True})
    db.commit()
    return {"updated": n}


# ------------------------------------------------------------------ reports (CSV)
def _csv(rows: list[dict], name: str) -> StreamingResponse:
    buf = io.StringIO()
    if rows:
        w = csv.DictWriter(buf, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M")
    return StreamingResponse(iter([buf.getvalue()]), media_type="text/csv",
                             headers={"Content-Disposition": f'attachment; filename="{name}-{stamp}.csv"'})


@router.get("/reports/holdings.csv")
def report_holdings(entity: str | None = None, user: User = Depends(require("reports:read")), db: Session = Depends(get_db)):
    check_entity(user, entity)
    rep = reporting_ccy(db, entity)
    _, views = value_accounts(db, load_accounts(db, entity, allowed_entities(user)), rep)
    return _csv([{"account": v.account, "symbol": v.symbol, "name": v.name, "class": v.asset_class, "type": v.inst_type,
                  "ccy": v.ccy, "qty": v.qty, "avg_px": v.avg_px, "mark": v.mark,
                  f"exposure_{rep}": round(v.exposure_rep, 2), f"mtm_pnl_{rep}": round(v.mtm_pnl_rep, 2),
                  "weight_pct": round(v.weight_pct, 4), "maturity": v.maturity or ""} for v in views], "holdings")


@router.get("/reports/breaches.csv")
def report_breaches(user: User = Depends(require("reports:read")), db: Session = Depends(get_db)):
    q = _scoped(db.query(Breach).options(joinedload(Breach.rule), joinedload(Breach.account)).join(Account), user)
    return _csv([{"id": b.id, "detected_at": b.detected_at.isoformat(), "account": b.account.code, "rule": b.rule.code,
                  "category": b.rule.category, "severity": b.rule.severity.value, "kind": b.kind, "subject": b.subject,
                  "observed": b.observed, "limit": b.limit, "status": b.status.value, "message": b.message}
                 for b in q.order_by(Breach.id.desc())], "breach-register")


@router.get("/reports/trades.csv")
def report_trades(user: User = Depends(require("reports:read")), db: Session = Depends(get_db)):
    q = _scoped(db.query(Trade).options(joinedload(Trade.account), joinedload(Trade.instrument)).join(Account), user)
    return _csv([trade_out(t) for t in q.order_by(Trade.id.desc())], "trades")


@router.get("/reports/audit.csv")
def report_audit(_: User = Depends(require("audit:read")), db: Session = Depends(get_db)):
    return _csv([{"ts": r.ts.isoformat(), "user": r.username, "action": r.action, "object": r.object_type,
                  "object_id": r.object_id, "request_id": r.request_id or ""}
                 for r in db.query(AuditLog).order_by(AuditLog.id.desc()).limit(50_000)], "audit-trail")
