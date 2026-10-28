"""Authentication (PBKDF2 password hashing, JWT) and role-based access control."""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from .config import get_settings
from .db import get_db
from .models import Role, User

PBKDF2_ITERATIONS = 390_000

# Permission matrix - segregation of duties is enforced here and in the order workflow
# (a maker can never approve their own order).
PERMISSIONS: dict[str, set[Role]] = {
    "portfolio:read": {Role.ADMIN, Role.PM, Role.TRADER, Role.COMPLIANCE, Role.RISK, Role.OPS, Role.VIEWER},
    "order:create": {Role.PM, Role.TRADER},
    "order:approve": {Role.PM, Role.COMPLIANCE},
    "order:cancel": {Role.PM, Role.TRADER, Role.ADMIN},
    "model:write": {Role.PM},
    "model:approve": {Role.PM, Role.COMPLIANCE},
    "rebalance:run": {Role.PM},
    "optimizer:run": {Role.PM, Role.RISK},
    "compliance:read": {Role.ADMIN, Role.PM, Role.COMPLIANCE, Role.RISK, Role.VIEWER},
    "compliance:write": {Role.COMPLIANCE},
    "breach:manage": {Role.COMPLIANCE},
    "risk:read": {Role.ADMIN, Role.PM, Role.RISK, Role.COMPLIANCE, Role.VIEWER},
    "ops:read": {Role.ADMIN, Role.OPS, Role.COMPLIANCE, Role.PM},
    "ops:write": {Role.OPS},
    "audit:read": {Role.ADMIN, Role.COMPLIANCE},
    "system:admin": {Role.ADMIN},
    "reports:read": {Role.ADMIN, Role.PM, Role.COMPLIANCE, Role.RISK, Role.OPS, Role.VIEWER},
}

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, PBKDF2_ITERATIONS)
    return f"pbkdf2_sha256${PBKDF2_ITERATIONS}${base64.b64encode(salt).decode()}${base64.b64encode(dk).decode()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        algo, iters, salt_b64, hash_b64 = stored.split("$")
        if algo != "pbkdf2_sha256":
            return False
        dk = hashlib.pbkdf2_hmac("sha256", password.encode(), base64.b64decode(salt_b64), int(iters))
        return hmac.compare_digest(dk, base64.b64decode(hash_b64))
    except (ValueError, TypeError):
        return False


def validate_password_policy(password: str) -> None:
    if len(password) < 10 or password.isalpha() or password.isdigit():
        raise HTTPException(
            422,
            "Password must be at least 10 characters and mix letters with digits or symbols",
        )


def create_access_token(user: User) -> tuple[str, int]:
    s = get_settings()
    exp_minutes = s.access_token_minutes
    now = datetime.now(timezone.utc)
    payload = {
        "sub": user.username,
        "role": user.role.value,
        "iat": now,
        "exp": now + timedelta(minutes=exp_minutes),
        "jti": secrets.token_hex(8),
    }
    return jwt.encode(payload, s.jwt_secret, algorithm=s.jwt_algorithm), exp_minutes * 60


def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)) -> User:
    s = get_settings()
    cred_exc = HTTPException(
        status.HTTP_401_UNAUTHORIZED, "Invalid or expired credentials", headers={"WWW-Authenticate": "Bearer"}
    )
    try:
        payload = jwt.decode(token, s.jwt_secret, algorithms=[s.jwt_algorithm])
    except jwt.PyJWTError as exc:
        raise cred_exc from exc
    user = db.query(User).filter(User.username == payload.get("sub")).one_or_none()
    if user is None or not user.is_active:
        raise cred_exc
    return user


def decode_token(token: str) -> dict | None:
    s = get_settings()
    try:
        return jwt.decode(token, s.jwt_secret, algorithms=[s.jwt_algorithm])
    except jwt.PyJWTError:
        return None


def has_perm(user: User, perm: str) -> bool:
    if user.role in PERMISSIONS.get(perm, set()):
        return True
    # Administrators may read everything but cannot act as maker/checker on investment decisions.
    return user.role == Role.ADMIN and perm.endswith(":read")


def require(perm: str):
    def dep(user: User = Depends(get_current_user)) -> User:
        if not has_perm(user, perm):
            raise HTTPException(status.HTTP_403_FORBIDDEN, f"Missing permission: {perm}")
        return user

    return dep


def allowed_entities(user: User) -> list[str] | None:
    """None means unrestricted."""
    return list(user.entities) if user.entities else None
