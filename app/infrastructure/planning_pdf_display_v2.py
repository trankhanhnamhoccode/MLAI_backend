"""Display-only exact rounding and retained labels for the owner report."""
from collections import OrderedDict
from fractions import Fraction
from uuid import UUID
from app.application.contracts.planning_pdf import PlanningPDFDocument
from app.application.contracts.planning_public import ExactQuantity, Service, PlanningNotification

UNKNOWN = 'Chưa biết / chưa đánh giá'
PATHS = {'LOW': 'Nhu cầu thấp', 'BASE': 'Nhu cầu cơ sở', 'HIGH': 'Nhu cầu cao'}
STRATEGIES = {'lean': 'Tinh gọn', 'balanced': 'Cân bằng', 'protected': 'Bảo vệ'}
SYNTHETIC_PROVENANCE = frozenset({
    'synthetic_fixture/1',
    'User-requested SYNTHETIC local demo; no real inventory/sales/order evidence',
})


def fraction(value: ExactQuantity | Service) -> Fraction:
    return Fraction(int(value.numerator), int(value.denominator))


def number(value: Fraction | None, places: int = 3) -> str:
    """Half-up; explicit approximation; never round positive evidence to zero."""
    if value is None:
        return UNKNOWN
    scale = 10 ** places
    if 0 < value < Fraction(1, scale):
        return '< ' + number(Fraction(1, scale), places)
    rounded = (value.numerator * scale * 2 + value.denominator) // (2 * value.denominator)
    whole, remainder = divmod(rounded, scale)
    result = f'{whole:,}'.replace(',', '.')
    if remainder:
        result += ',' + str(remainder).zfill(places).rstrip('0')
    return ('~ ' if Fraction(rounded, scale) != value else '') + result


def quantity(value: ExactQuantity | None, unit: str = '') -> str:
    return number(fraction(value) if value is not None else None) + (' ' + unit if unit and value is not None else '')


def money(value: ExactQuantity | str | None, currency: str) -> str:
    amount = fraction(value) if isinstance(value, ExactQuantity) else Fraction(value) if value is not None else None
    places = {'VND': 0, 'JPY': 0, 'KRW': 0, 'USD': 2, 'EUR': 2, 'GBP': 2,
              'AUD': 2, 'CAD': 2, 'SGD': 2, 'THB': 2, 'KWD': 3, 'BHD': 3}.get(currency, 3)
    return number(amount, places) + (' ₫' if currency == 'VND' else ' ' + currency)


def percent(value: Service | None) -> str:
    return number(fraction(value) * 100, 1) + ' %' if value is not None else UNKNOWN


class RetainedLabels:
    """Report-wide collision-free suffix map, without current-catalog reads."""
    def __init__(self, document: PlanningPDFDocument):
        view = document.view
        self.products = {p.product_id: p.name for p in view.scope.menu_products} if view.scope else {}
        self.ingredients = {i.ingredient_id: i.display_name for i in document.ingredients}
        ids = {view.store_id, *self.products, *self.ingredients}
        for row in document.option.purchases:
            ids.update((row.ingredient_id, row.supplier_id, row.supplier_term_id))
        for row in document.option.product_services:
            ids.add(row.product_id)
        for fee in document.option.costs.fee_components:
            ids.add(fee.entity_id)
        for item in (*document.explanation.blockers, *document.explanation.warnings, *document.option.issues):
            if item.details.entity_id:
                ids.add(item.details.entity_id)
        for item in document.explanation.exclusions:
            ids.add(item.product_id)
        self.codes = {}
        for ident in sorted(ids):
            text = str(ident).replace('-', '')
            length = 4
            while any(other != ident and str(other).replace('-', '')[-length:] == text[-length:] for other in ids):
                length += 1
            self.codes[ident] = text[-length:]

    def name(self, kind: str, ident: UUID) -> str:
        names = self.products if kind == 'Món' else self.ingredients if kind == 'Nguyên liệu' else {}
        return names.get(ident) or f'{kind} chưa lưu tên — mã …{self.codes[ident]}'


def grouped_notices(items: tuple[PlanningNotification, ...]) -> list[tuple[PlanningNotification, tuple[str, ...]]]:
    """Merge identical cause/entity/scope/action only; retain all affected dates."""
    groups = OrderedDict()
    for item in items:
        key = (item.code, item.message, item.details.model_dump_json(exclude={'affected_dates'}))
        if key not in groups:
            groups[key] = (item, set())
        groups[key][1].update(str(day) for day in item.details.affected_dates or ())
    return [(item, tuple(sorted(days))) for item, days in groups.values()]
