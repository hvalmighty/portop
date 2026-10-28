"""Append-only audit trail with request correlation."""

from __future__ import annotations

from contextvars import ContextVar
from datetime import date, datetime
from enum import Enum
from typing import Any

from sqlalchemy.orm import Session

from .models import AuditLog

request_id_var: ContextVar[str | None] = ContextVar("request_id", default=None)
client_ip_var: ContextVar[str | None] = ContextVar("client_ip", default=None)


def _jsonable(v: Any) -> Any:
    if isinstance(v, (datetime, date)):
        return v.isoformat()
    if isinstance(v, Enum):
        return v.value
    if isinstance(v, dict):
        return {k: _jsonable(x) for k, x in v.items()}
    if isinstance(v, (list, tuple)):
        return [_jsonable(x) for x in v]
    return v


def snapshot(obj: Any, exclude: set[str] | None = None) -> dict:
    exclude = (exclude or set()) | {"password_hash"}
    return {
        c.key: _jsonable(getattr(obj, c.key))
        for c in obj.__table__.columns
        if c.key not in exclude
    }


def audit(
    db: Session,
    username: str,
    action: str,
    object_type: str,
    object_id: Any,
    before: dict | None = None,
    after: dict | None = None,
) -> None:
    db.add(
        AuditLog(
            username=username,
            action=action,
            object_type=object_type,
            object_id=str(object_id),
            before=_jsonable(before) if before else None,
            after=_jsonable(after) if after else None,
            request_id=request_id_var.get(),
            ip=client_ip_var.get(),
        )
    )
