from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from ..models import Account, Instrument, User
from ..security import allowed_entities


def get_account(db: Session, user: User, code: str) -> Account:
    a = db.query(Account).filter(Account.code == code).one_or_none()
    if a is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Account {code} not found")
    allowed = allowed_entities(user)
    if allowed is not None and a.entity_code not in allowed:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Not entitled to this account")
    return a


def get_instrument(db: Session, symbol: str) -> Instrument:
    i = db.query(Instrument).filter(Instrument.symbol == symbol).one_or_none()
    if i is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Instrument {symbol} not found")
    return i


def check_entity(user: User, entity: str | None) -> None:
    allowed = allowed_entities(user)
    if entity and allowed is not None and entity not in allowed:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Not entitled to this entity")
