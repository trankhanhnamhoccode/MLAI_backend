"""CAT12 editor validation independent of database/provider/solver."""
from datetime import date
from uuid import uuid4
import pytest
from pydantic import ValidationError
from app.application.contracts.recipe_schedule import PreviewRequest, CommitRequest
from app.domain.recipe_calendar import Period, overlaps, gaps, history_unchanged


def test_exact_quantity_and_explicit_commit_confirmation():
    p = PreviewRequest(phase="preview", new_recipes=[], operations=[], reason="Review same calendar")
    assert p.phase == "preview"
    with pytest.raises(ValidationError):
        CommitRequest(phase="commit", change_id=uuid4(), preview_digest="v", confirm=1,
                      acknowledged_warning_codes=[])
    for changes in ({"yield_quantity":"0"}, {"yield_quantity":1}, {"process_loss_rate":"1"}, {"ingredients":[]}):
        recipe = dict(client_reference="r",yield_quantity="1",yield_unit="cup",process_loss_rate="0",
            ingredients=[dict(ingredient_id=str(uuid4()),quantity="0.00000000000000000001",unit="g")])
        with pytest.raises(ValidationError):
            PreviewRequest(phase="preview",new_recipes=[{**recipe, **changes}],operations=[],reason="New content")


def test_inclusive_calendar_and_history_identity():
    today = date(2026,10,10); old, new = uuid4(), uuid4()
    before = (Period(old,date(2026,10,1),None),)
    after = (Period(old,date(2026,10,1),today),Period(new,date(2026,10,11),None))
    assert history_unchanged(before,after,today) and not overlaps(after)
    assert gaps(after,date(2026,10,11)) == ()
    overlap = (after[0],Period(new,today,None))
    assert overlaps(overlap) and not history_unchanged(before,overlap,today)
    future_gap = (after[0],Period(new,date(2026,10,13),None))
    assert gaps(future_gap,date(2026,10,11)) == ((date(2026,10,11),date(2026,10,12)),)
