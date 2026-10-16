"""Operator configuration accepts only bounded integer gateway sheet slots."""
import pytest
from pydantic import ValidationError
from app.config import Settings


@pytest.mark.parametrize('limit', [0, 1, 2, 10, '10'])
def test_bounded_operator_limit(limit):
    settings = Settings(_env_file=None, import_semantic_sheet_limit=limit)
    assert settings.import_semantic_sheet_limit == int(limit)


@pytest.mark.parametrize('limit', [-1, 11, 1.5, True, '1.0'])
def test_invalid_operator_limit(limit):
    with pytest.raises(ValidationError):
        Settings(_env_file=None, import_semantic_sheet_limit=limit)


def test_default_limit():
    assert Settings(_env_file=None).import_semantic_sheet_limit == 2
