import time
from collections import defaultdict, deque
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from ..audit import audit
from ..db import get_db
from ..models import Entity, User
from ..security import PERMISSIONS, allowed_entities, create_access_token, get_current_user, has_perm, verify_password

router = APIRouter(prefix="/auth", tags=["auth"])

MAX_FAILED = 5
_attempts: dict[str, deque] = defaultdict(deque)  # per-IP sliding window (single-instance; use Redis behind a LB)


def _throttle(ip: str) -> None:
    now = time.monotonic()
    q = _attempts[ip]
    while q and now - q[0] > 60:
        q.popleft()
    if len(q) >= 20:
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Too many login attempts, try again shortly")
    q.append(now)


def user_out(u: User) -> dict:
    return {
        "username": u.username,
        "full_name": u.full_name,
        "email": u.email,
        "role": u.role.value,
        "entities": u.entities or [],
        "permissions": sorted(p for p in PERMISSIONS if has_perm(u, p)),
    }


@router.post("/login")
def login(request: Request, form: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    _throttle(request.client.host if request.client else "unknown")
    u = db.query(User).filter(User.username == form.username.strip().lower()).one_or_none()
    if u is None or not u.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid username or password")
    if u.failed_logins >= MAX_FAILED:
        raise HTTPException(status.HTTP_423_LOCKED, "Account locked after repeated failures - contact an administrator")
    if not verify_password(form.password, u.password_hash):
        u.failed_logins += 1
        audit(db, u.username, "LOGIN_FAILED", "user", u.username)
        db.commit()
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid username or password")
    u.failed_logins = 0
    u.last_login = datetime.now(timezone.utc)
    audit(db, u.username, "LOGIN", "user", u.username)
    db.commit()
    token, ttl = create_access_token(u)
    return {"access_token": token, "token_type": "bearer", "expires_in": ttl, "user": user_out(u)}


@router.get("/me")
def me(user: User = Depends(get_current_user)):
    return user_out(user)


@router.get("/entities")
def entities(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    allowed = allowed_entities(user)
    q = db.query(Entity)
    if allowed is not None:
        q = q.filter(Entity.code.in_(allowed))
    return [{"code": e.code, "name": e.name, "reporting_ccy": e.reporting_ccy} for e in q.order_by(Entity.code)]
