"""Only approved missing defaults; invalid facts and explicit values retain meaning."""
from decimal import Decimal
import pytest

from app.application.contracts.import_mapping import ProvenanceValue, PreviewSummary
from uuid import uuid4
from app.application.import_descriptors import options
from tests.unit.test_import_preview import case
from tests.unit.test_import_recipe_basis import recipe, snapshot


@pytest.mark.parametrize('missing_column', [False, True])
def test_missing_recipe_loss_is_effective_zero_with_warning_and_separate_origin(missing_column):
    record=recipe();record['process_loss_rate']=None
    if missing_column:
        del record['process_loss_rate'];del record['effective_to']
    row,=case('recipes',[record],snapshot(record))
    assert not row.blockers and row.after.process_loss_rate=='0' and row.after.effective_to is None
    p=next(p for p in row.provenance if p.field=='process_loss_rate')
    assert p.origin=='SYSTEM_DEFAULT' and p.value_source=='SYSTEM_DEFAULT' and p.source_missing
    assert p.source_value == (None if missing_column else '') and p.declaration_id is None
    assert {w.code for w in row.warnings}=={'RECIPE_PROCESS_LOSS_DEFAULTED_ZERO'}


@pytest.mark.parametrize('loss',['0','0.25'])
def test_explicit_loss_never_becomes_system_default(loss):
    record=recipe();record['process_loss_rate']=loss
    row,=case('recipes',[record],snapshot(record))
    assert not row.blockers and Decimal(row.after.process_loss_rate)==Decimal(loss)
    p=next(p for p in row.provenance if p.field=='process_loss_rate')
    assert p.origin=='SOURCE_EXPLICIT' and not p.source_missing and p.source_value==loss
    assert not row.warnings


@pytest.mark.parametrize('field,bad',[('process_loss_rate',''),('process_loss_rate',' '),
    ('process_loss_rate','NaN'),('process_loss_rate','-0.1'),('process_loss_rate','1'),
    ('effective_to','invalid'),('yield_quantity',None),('unit',None),('quantity',None)])
def test_invalid_or_unapproved_missing_facts_do_not_default(field,bad):
    record=recipe();record[field]=bad
    row,=case('recipes',[record],snapshot(recipe()))
    # Blank source cells are missing, rather than an invalid nonblank declaration.
    if field=='process_loss_rate' and bad=='':
        assert row.after.process_loss_rate=='0' and row.warnings
    else:
        assert row.blockers and row.after is None


def test_descriptors_publish_exact_missing_policy_allowlist():
    fields={o.key:o for o in options() if o.available}
    defaults={key:o.missing_policy for key,o in fields.items() if o.missing_policy not in {'block','optional'}}
    assert defaults=={'recipes.process_loss_rate':'effective_zero','recipes.effective_to':'open_ended',
        'products.sku':'unknown_null','ingredients.sku':'unknown_null'}
    assert fields['recipes.process_loss_rate'].effective_default=='0'
    assert fields['recipes.quantity'].missing_policy=='block'


def test_retained_provenance_does_not_relabel_old_explicit_zero():
    old=dict(source_value='0',origin='SOURCE_EXPLICIT',applied_rule_ids=[],value_source='SOURCE_COLUMN',
        source_column_index=3,declaration_id=None)
    read=ProvenanceValue.model_validate(old)
    assert not read.source_missing and read.origin=='SOURCE_EXPLICIT' and read.source_value=='0'


@pytest.mark.parametrize('include_version',[False,True])
def test_retained_preview_keeps_original_policy_version(include_version):
    old=dict(preview_id=uuid4(),digest='retained',created_at='2026-07-08T00:00:00Z',source_set_version='old',
        mapping_bindings=[],validation_status='ready',required_actions=[],groups=[],counts={},blockers=[],warnings=[])
    if include_version:old['policy_version']='import_mapping_policy/1'
    assert PreviewSummary.model_validate(old).policy_version=='import_mapping_policy/1'
