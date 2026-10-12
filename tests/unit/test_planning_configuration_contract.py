import pytest
from pydantic import ValidationError
from app.application.contracts.planning_configuration import SaveRequest, ReplaceRequest, ArchiveRequest, BudgetRequest


def test_presence_null_zero_and_archive_are_distinct():
    value = SaveRequest.model_validate({'name': '  test  ', 'requirements': {'paths': [{'path': 'BASE'}]}})
    assert value.name == 'test'
    assert value.requirements.paths[0].product_overrides is None
    assert 'product_overrides' not in value.requirements.paths[0].model_fields_set
    with pytest.raises(ValidationError):
        SaveRequest.model_validate({'name': 'test', 'requirements': {'paths': [{'path': 'BASE', 'product_overrides': None}]}})
    assert BudgetRequest(amount='0').amount == '0'
    with pytest.raises(ValidationError):
        BudgetRequest(amount=None)
    assert ArchiveRequest(state='archived').state == 'archived'
    with pytest.raises(ValidationError):
        ArchiveRequest(state='archived', name='bad')
    with pytest.raises(ValidationError):
        ReplaceRequest(state='archived', name='bad', requirements={'paths':[{'path':'BASE'}]})
