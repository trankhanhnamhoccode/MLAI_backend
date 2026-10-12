"""Opening physical observations checked under the caller's stock table fence."""
from datetime import datetime
from fractions import Fraction
from uuid import UUID
from sqlalchemy.orm import Session
from app.application.contracts.auth import AuthError
from app.repositories.stock_observation import observation_evidence


def validate_opening_observation(session: Session, store: UUID, ingredient: UUID,
                                 observed_at: datetime, lot_code: str | None) -> None:
    evidence = observation_evidence(session,store,ingredient,observed_at)
    lots, movements = evidence.lots,evidence.movements
    if any(m.occurred_at > observed_at or m.created_at > observed_at for m in movements):
        raise AuthError("STALE_STOCK_OBSERVATION", 409)
    # A NO_OP count still records a physical observation; it need not have a movement.
    for recorded_at, lot_ids in evidence.counts:
        if set(lot_ids) & {str(l.id) for l in lots}:
            raise AuthError("STALE_STOCK_OBSERVATION" if recorded_at > observed_at else "STOCK_OBSERVATION_UNVERIFIABLE", 409)
    for lot in lots:
        evidence = [m for m in movements if m.lot_id == lot.id]
        if (lot.updated_at > observed_at or not evidence or
            sum((Fraction(m.quantity_delta) for m in evidence), Fraction(0)) != Fraction(lot.on_hand_quantity)):
            raise AuthError("STOCK_OBSERVATION_UNVERIFIABLE", 409)
        # lot_code is not canonical identity. Ambiguous physical-lot evidence cannot
        # establish a new baseline; never bind or add to an existing lot by its label.
        if lot.on_hand_quantity > 0 and (lot_code is None or lot.lot_code is None or lot.lot_code == lot_code):
            raise AuthError("OPENING_STOCK_ALREADY_RECORDED", 409)
