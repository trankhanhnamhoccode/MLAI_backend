import pytest
from pydantic import ValidationError
from uuid import UUID
from app.application.contracts.forecast_model import ExecutionDetails, ModelReadiness


def test_details_capture_nested_warning_by_value():
    values = [dict(code='FALLBACK', severity='WARNING', field='model_type', entity='ForecastRun', impact='baseline')]
    details = ExecutionDetails(selection_reason='NO_ARTIFACT', warnings=values)
    values[0]['impact'] = 'mutated'
    values.append(values[0])
    assert len(details.warnings) == 1 and details.warnings[0].impact == 'baseline'
    with pytest.raises(ValidationError):
        details.warnings[0].impact = 'mutated'


@pytest.mark.parametrize('count', [True, -1, 1.0])
def test_readiness_counts_are_strict(count):
    with pytest.raises(ValidationError):
        ModelReadiness(product_id=UUID(int=1), observation_count=count, status='READY')


@pytest.mark.parametrize('version',[True,1.0,'1',2])
def test_metadata_version_is_strict(version):
    with pytest.raises(ValidationError):
        ExecutionDetails(selection_reason='NO_ARTIFACT',schema_version=version)
