from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..audit import audit, snapshot
from ..db import get_db
from ..models import Alert, Entity, FxRate, Instrument, User
from ..schemas import InstrumentPatch, UserIn, UserUpdate
from ..security import PERMISSIONS, hash_password, require, validate_password_policy
from .common import get_instrument

router = APIRouter(prefix="/system", tags=["system"])


def u_out(u: User) -> dict:
    return {"id": u.id, "username": u.username, "full_name": u.full_name, "email": u.email, "role": u.role.value,
            "entities": u.entities or [], "is_active": u.is_active, "locked": u.failed_logins >= 5,
            "last_login": u.last_login.isoformat() if u.last_login else None}


@router.get("/users")
def users(_: User = Depends(require("system:admin")), db: Session = Depends(get_db)):
    return [u_out(u) for u in db.query(User).order_by(User.username)]


@router.get("/permissions")
def permissions(_: User = Depends(require("system:admin"))):
    return {p: sorted(r.value for r in roles) for p, roles in PERMISSIONS.items()}


def _check_entities(db: Session, codes: list[str]) -> None:
    known = {e.code for e in db.query(Entity)}
    bad = set(codes) - known
    if bad:
        raise HTTPException(422, f"Unknown entities: {sorted(bad)}")


@router.post("/users", status_code=201)
def create_user(body: UserIn, admin: User = Depends(require("system:admin")), db: Session = Depends(get_db)):
    if db.query(User).filter(User.username == body.username).count():
        raise HTTPException(409, "Username exists")
    validate_password_policy(body.password)
    _check_entities(db, body.entities)
    u = User(username=body.username, full_name=body.full_name, email=body.email, role=body.role,
             entities=body.entities, password_hash=hash_password(body.password))
    db.add(u)
    db.flush()
    audit(db, admin.username, "USER_CREATE", "user", u.username, after=snapshot(u))
    db.commit()
    return u_out(u)


@router.patch("/users/{username}")
def update_user(username: str, body: UserUpdate, admin: User = Depends(require("system:admin")),
                db: Session = Depends(get_db)):
    u = db.query(User).filter(User.username == username).one_or_none()
    if u is None:
        raise HTTPException(404, "User not found")
    if u.username == admin.username and (body.role or body.is_active is False):
        raise HTTPException(409, "Administrators cannot change their own role or deactivate themselves")
    before = snapshot(u)
    if body.role:
        u.role = body.role
    if body.is_active is not None:
        u.is_active = body.is_active
    if body.entities is not None:
        _check_entities(db, body.entities)
        u.entities = body.entities
    if body.password:
        validate_password_policy(body.password)
        u.password_hash = hash_password(body.password)
        u.failed_logins = 0  # password reset also unlocks
    audit(db, admin.username, "USER_UPDATE", "user", u.username, before, snapshot(u))
    db.commit()
    return u_out(u)


@router.post("/users/{username}/unlock")
def unlock(username: str, admin: User = Depends(require("system:admin")), db: Session = Depends(get_db)):
    u = db.query(User).filter(User.username == username).one_or_none()
    if u is None:
        raise HTTPException(404, "User not found")
    u.failed_logins = 0
    audit(db, admin.username, "USER_UNLOCK", "user", u.username)
    db.commit()
    return u_out(u)


@router.patch("/instruments/{symbol}")
def patch_instrument(symbol: str, body: InstrumentPatch, user: User = Depends(require("ops:write")),
                     db: Session = Depends(get_db)):
    """Static-data maintenance (e.g. rating changes). Rating moves can create passive breaches on the next scan."""
    i: Instrument = get_instrument(db, symbol)
    before = snapshot(i)
    changes = body.model_dump(exclude_none=True)
    for k, v in changes.items():
        setattr(i, k, v)
    if "rating" in changes and before.get("rating") != i.rating:
        db.add(Alert(level="WARN", category="REFERENCE_DATA",
                     message=f"Rating change {symbol}: {before.get('rating')} -> {i.rating}"))
    audit(db, user.username, "INSTRUMENT_UPDATE", "instrument", symbol, before, snapshot(i))
    db.commit()
    return {"symbol": i.symbol, **changes}


class FxIn(BaseModel):
    usd_per_unit: float = Field(gt=0)


@router.get("/fx")
def fx_rates(_: User = Depends(require("portfolio:read")), db: Session = Depends(get_db)):
    return [{"ccy": r.ccy, "usd_per_unit": r.usd_per_unit} for r in db.query(FxRate).order_by(FxRate.ccy)]


@router.put("/fx/{ccy}")
def set_fx(ccy: str, body: FxIn, user: User = Depends(require("ops:write")), db: Session = Depends(get_db)):
    r = db.get(FxRate, ccy.upper())
    if r is None:
        r = FxRate(ccy=ccy.upper(), usd_per_unit=body.usd_per_unit)
        db.add(r)
        before = None
    else:
        before = {"usd_per_unit": r.usd_per_unit}
        r.usd_per_unit = body.usd_per_unit
    audit(db, user.username, "FX_UPDATE", "fx", ccy.upper(), before, {"usd_per_unit": body.usd_per_unit})
    db.commit()
    return {"ccy": r.ccy, "usd_per_unit": r.usd_per_unit}
