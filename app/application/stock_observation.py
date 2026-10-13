"""Opening physical observations checked under the caller's stock table fence."""
from datetime import datetime
from fractions import Fraction
from uuid import UUID
from sqlalchemy.orm import Session
from app.application.contracts.auth import AuthError
from app.repositories.stock_observation import observation_evidence


def opening_observation_issue(lots, movements, counts, observed_at, lot_code):
    """Same policy for detached preview evidence and transaction-owned N6 evidence."""
    def instant(value):
        return datetime.fromisoformat(value) if isinstance(value, str) else value
    if any(instant(m["occurred_at"]) > observed_at or instant(m["created_at"]) > observed_at for m in movements):
        return "STALE_STOCK_OBSERVATION"
    for recorded_at, lot_ids in counts:
        if set(lot_ids) & {str(l["id"]) for l in lots}:
            return "STALE_STOCK_OBSERVATION" if instant(recorded_at) > observed_at else "STOCK_OBSERVATION_UNVERIFIABLE"
    for lot in lots:
        evidence = [m for m in movements if str(m["lot_id"]) == str(lot["id"])]
        if (instant(lot["updated_at"]) > observed_at or not evidence or
                sum((Fraction(m["quantity_delta"]) for m in evidence), Fraction(0)) != Fraction(lot["on_hand_quantity"])):
            return "STOCK_OBSERVATION_UNVERIFIABLE"
        if Fraction(lot["on_hand_quantity"]) > 0 and (lot_code is None or lot["lot_code"] is None or lot["lot_code"] == lot_code):
            return "OPENING_STOCK_ALREADY_RECORDED"
    return None


def validate_opening_observation(session: Session, store: UUID, ingredient: UUID,
                                 observed_at: datetime, lot_code: str | None) -> None:
    evidence = observation_evidence(session,store,ingredient,observed_at)
    def values(record):
        return {c.name: getattr(record, c.name) for c in record.__table__.columns}
    code = opening_observation_issue(tuple(map(values, evidence.lots)),
        tuple(map(values, evidence.movements)), evidence.counts, observed_at, lot_code)
    if code:
        raise AuthError(code, 409)
