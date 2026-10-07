"""Observed-sales execution semantics; plain values, no model or I/O."""
from datetime import date, timedelta
from decimal import Decimal
from uuid import UUID

ProductUnit = tuple[UUID, str]
ObservedSale = tuple[UUID, UUID, date, Decimal, str]
PredictionKey = tuple[UUID, date]


class ForecastSemanticError(ValueError):
    """Internal semantic rejection; codes are not a public HTTP contract."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


def forecast_dates(cutoff_date: date) -> tuple[date, ...]:
    """Business dates D+1..D+7; deliberately no end-of-day timestamp."""
    try:
        return tuple(cutoff_date + timedelta(days=i) for i in range(1, 8))
    except OverflowError as error:
        raise ForecastSemanticError('INVALID_HORIZON', 'Cutoff cannot represent seven future dates') from error


def validate_request(product_ids: tuple[UUID, ...], history_start_date: date,
                     cutoff_date: date) -> None:
    if not product_ids or len(set(product_ids)) != len(product_ids):
        raise ForecastSemanticError('INVALID_PRODUCT_SCOPE', 'Product scope must be nonempty and unique')
    if history_start_date > cutoff_date:
        raise ForecastSemanticError('INVALID_HISTORY_WINDOW', 'History start must be <= cutoff')
    forecast_dates(cutoff_date)


def validate_prepared_input(store_id: UUID, product_ids: tuple[UUID, ...],
                            history_start_date: date, cutoff_date: date,
                            products: tuple[ProductUnit, ...],
                            observations: tuple[ObservedSale, ...],
                            dates: tuple[date, ...]) -> None:
    """Reject malformed canonical input; never filter, aggregate or fill gaps."""
    validate_request(product_ids, history_start_date, cutoff_date)
    units = dict(products)
    if len(units) != len(products) or set(units) != set(product_ids):
        raise ForecastSemanticError('INVALID_PRODUCT_SCOPE', 'Captured Products must exactly match requested scope')
    if any(not unit.strip() for unit in units.values()):
        raise ForecastSemanticError('INVALID_UNIT', 'Captured selling units must be nonblank')
    if len(dates) != 7 or set(dates) != set(forecast_dates(cutoff_date)):
        raise ForecastSemanticError('INVALID_HORIZON', 'Forecast dates must be exactly D+1 through D+7')
    keys: set[PredictionKey] = set()
    for observed_store, product, day, quantity, unit in observations:
        if observed_store != store_id or product not in units:
            raise ForecastSemanticError('OBSERVATION_SCOPE', 'Observation outside captured Store/Product scope')
        if not history_start_date <= day <= cutoff_date:
            raise ForecastSemanticError('OBSERVATION_WINDOW', 'Observation outside inclusive history window')
        if unit != units[product]:
            raise ForecastSemanticError('OBSERVATION_UNIT', 'Observation unit must exactly match captured selling_unit')
        if not isinstance(quantity, Decimal) or not quantity.is_finite() or quantity < 0:
            raise ForecastSemanticError('INVALID_QUANTITY', 'Observed quantity must be finite nonnegative Decimal')
        key = (product, day)
        if key in keys:
            raise ForecastSemanticError('DUPLICATE_OBSERVATION', 'Canonical Product/date observations must be unique')
        keys.add(key)


def validate_quantiles(p25: Decimal, p50: Decimal, p75: Decimal) -> None:
    if (any(not isinstance(v, Decimal) or not v.is_finite() for v in (p25, p50, p75))
            or not 0 <= p25 <= p50 <= p75):
        raise ForecastSemanticError('INVALID_QUANTILES', 'Finite Decimal quantiles must satisfy 0 <= p25 <= p50 <= p75')


def validate_output_coverage(product_ids: tuple[UUID, ...], cutoff_date: date,
                             actual_keys: tuple[PredictionKey, ...]) -> None:
    if not product_ids or len(set(product_ids)) != len(product_ids):
        raise ForecastSemanticError('INVALID_PRODUCT_SCOPE', 'Product scope must be nonempty and unique')
    if not actual_keys:
        raise ForecastSemanticError('EMPTY_OUTPUT', 'Execution output cannot be empty')
    actual = set(actual_keys)
    if len(actual) != len(actual_keys):
        raise ForecastSemanticError('DUPLICATE_OUTPUT', 'Execution output contains duplicate Product/date keys')
    expected = {(product, day) for product in product_ids for day in forecast_dates(cutoff_date)}
    if actual != expected:
        missing, unexpected = expected - actual, actual - expected
        raise ForecastSemanticError('OUTPUT_COVERAGE',
            f'Execution output must exactly cover requested Products x 7 dates; '
            f'missing={len(missing)}, unexpected={len(unexpected)}')
