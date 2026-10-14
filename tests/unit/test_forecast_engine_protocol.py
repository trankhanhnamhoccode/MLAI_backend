"""Small offline E1 gates; no conftest, persistence, native model or provider."""
from copy import deepcopy
from datetime import date
from decimal import Decimal
import json
from pathlib import Path
import unittest

from app.domain.forecasting.stockout import Observation, reconstruct
from scripts.forecast_benchmark_protocol import (
    Outcome, ProtocolError, canonical_digest, materialize_fixture,
    validate_case, validate_manifest,
)

FIXTURES = Path(__file__).resolve().parents[1] / 'fixtures' / 'forecast_engine'


class ForecastEngineProtocolTests(unittest.TestCase):
    def setUp(self):
        self.manifest = json.loads((FIXTURES / 'benchmark_manifest.json').read_text())
        self.fixtures = json.loads((FIXTURES / 'compatibility_cases.json').read_text())

    def reject_manifest(self, mutate, code):
        manifest = deepcopy(self.manifest)
        mutate(manifest)
        with self.assertRaises(ProtocolError) as caught:
            validate_manifest(manifest)
        self.assertEqual(caught.exception.code, code)

    def test_portable_admission_failure_cases(self):
        original = canonical_digest(self.fixtures['base'])
        for fixture in self.fixtures['cases']:
            with self.subTest(fixture=fixture['name']):
                case = materialize_fixture(self.fixtures['base'], fixture['changes'])
                try:
                    validate_case(case)
                    actual = 'VALID'
                except ProtocolError as error:
                    actual = f'{error.outcome.value}:{error.code}'
                self.assertEqual(actual, fixture['expected'])
        self.assertEqual(canonical_digest(self.fixtures['base']), original)

    def test_manifest_has_disjoint_target_windows(self):
        tasks = validate_manifest(self.manifest)
        self.assertEqual(len(tasks), 4)
        self.reject_manifest(lambda m: m['tasks'][1].update(
            origin='2026-10-07', calibration_end='2026-10-07'),
                             'TARGET_WINDOW_OVERLAP')

    def test_training_point_and_calibration_cannot_leak(self):
        for field, value in [('train_end', '2026-10-02'),
                             ('point_end', '2026-10-02'),
                             ('calibration_end', '2026-10-02')]:
            with self.subTest(field=field):
                self.reject_manifest(lambda m: m['tasks'][0].update({field: value}),
                                     'WINDOW_LEAKAGE')

    def test_holdout_cannot_select_or_precede_validation(self):
        self.reject_manifest(lambda m: m['selection'].update(partition='holdout'),
                             'SELECTION_CHANGED')
        self.reject_manifest(lambda m: m['tasks'][0].update(partition='holdout'),
                             'INSUFFICIENT_ORIGINS')
        self.reject_manifest(lambda m: m['tasks'][0].update(partition='holdout') or
                             m['tasks'][2].update(partition='validation'), 'PARTITION_ORDER')

    def test_scores_cannot_hide_stockout_or_drop_hard_targets(self):
        self.reject_manifest(lambda m: m['comparison'].update(primary_mask='all_sales'),
                             'SCORING_MASK_CHANGED')
        self.reject_manifest(lambda m: m['comparison'].update(coverage='paired_only'),
                             'SCORING_MASK_CHANGED')

    def test_no_e1_training_benchmark_or_promotion_enablement(self):
        for flag in ['benchmark_enabled', 'promotion_enabled']:
            self.reject_manifest(lambda m: m.update({flag: True}), 'E1_EXECUTION_DISABLED')
        self.reject_manifest(lambda m: m['promotion'].update(automatic=True), 'PROMOTION_CHANGED')
        self.reject_manifest(lambda m: m['arms'][2].update(reconstruction_policy='causal_stockout_v1'),
                             'ARM_SET_CHANGED')

    def test_configuration_edits_invalidate_manifest_pin(self):
        self.reject_manifest(lambda m: m['arm_configuration']['C_engine_native_reconstruction_v1']
                             .update(residual_blend_lambda=0.5), 'CONFIG_DIGEST_MISMATCH')

    def test_manifest_schema_requires_all_fields(self):
        self.reject_manifest(lambda m: m.pop('tasks'), 'MANIFEST_FIELDS')
        self.reject_manifest(lambda m: m.update(schema_version=True), 'MANIFEST_VERSION')

    def test_missing_day_and_observed_zero_stay_distinct(self):
        rows = self.fixtures['base']['observations']
        self.assertNotIn('2026-09-28', [r['date'] for r in rows])
        self.assertEqual(rows[0]['quantity'], '0')
        self.assertIs(rows[0]['stockout'], False)

    def test_host_causal_support_and_unknown_are_not_canonical_rewrites(self):
        rows = tuple(Observation(date.fromisoformat(r['date']), Decimal(r['quantity']), r['stockout'])
                     for r in self.fixtures['base']['observations'])
        supported = reconstruct(rows, date(2026, 10, 1))
        self.assertEqual(supported[-1].observed_quantity, Decimal('2'))
        self.assertEqual(supported[-1].demand_quantity, Decimal('10'))
        self.assertEqual(supported[-1].evidence_dates, (date(2026, 9, 27),
                         date(2026, 9, 29), date(2026, 9, 30)))
        unsupported = reconstruct(rows[1:], date(2026, 10, 1))
        self.assertIsNone(unsupported[-1].demand_quantity)
        unknown = reconstruct((Observation(date(2026, 10, 1), Decimal('2'), None),),
                              date(2026, 10, 1))
        self.assertEqual(unknown[0].method, 'UNKNOWN_OBSERVED_COMPATIBILITY')
        self.assertEqual(rows[-1].quantity, Decimal('2'))

    def test_future_support_and_derived_estimates_cannot_support_host_reconstruction(self):
        rows = (Observation(date(2026, 9, 27), Decimal('100'), False),
                Observation(date(2026, 9, 28), Decimal('1'), True),
                Observation(date(2026, 9, 29), Decimal('1'), True),
                Observation(date(2026, 9, 30), Decimal('1'), True),
                Observation(date(2026, 10, 2), Decimal('100'), False))
        result = reconstruct(rows, date(2026, 10, 1))
        self.assertEqual(len(result), 4)
        self.assertTrue(all(r.demand_quantity is None for r in result[1:]))

    def test_digest_is_order_independent_for_object_keys_and_rejects_nan(self):
        self.assertEqual(canonical_digest({'a': 1, 'b': 2}),
                         canonical_digest({'b': 2, 'a': 1}))
        with self.assertRaises(ValueError):
            canonical_digest({'bad': float('nan')})
        case = deepcopy(self.fixtures['base'])
        case['quantity_basis'] = 'be_reconstructed_demand'
        with self.assertRaises(ProtocolError) as caught:
            validate_case(case)
        self.assertEqual(caught.exception.outcome, Outcome.UNSUPPORTED)


if __name__ == '__main__':
    unittest.main()
