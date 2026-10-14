"""Permission union and terminal request policy without persistence or transport."""
import pytest
from app.domain.collaboration import permission_request_state,grant_union


def test_subset_union_preserves_unrelated_grants_and_reports_actual_additions():
    result=grant_union(('sales.read','budget.read'),('sales.read',),('menu.read','budget.read'))
    assert result.grants==('budget.read','menu.read','sales.read')
    assert result.added==('sales.read',)
    assert grant_union(('menu.read','sales.read'),('menu.read',),('menu.read',)).added==()


@pytest.mark.parametrize('selected',((),('budget.read',)))
def test_empty_or_unrequested_subset_cannot_be_approved(selected):
    with pytest.raises(ValueError):
        grant_union(('sales.read',),selected,('menu.read',))


def test_pending_reconciliation_and_terminal_state_do_not_reopen_after_revoke():
    assert permission_request_state('pending',('sales.read',),('menu.read',),eligible=True)=='pending'
    assert permission_request_state('pending',('sales.read',),('sales.read',),eligible=True)=='satisfied'
    assert permission_request_state('pending',('sales.read',),('sales.read',),eligible=False)=='invalidated'
    for terminal in ('approved','rejected','cancelled','satisfied','invalidated'):
        assert permission_request_state(terminal,('sales.read',),(),eligible=False)==terminal
