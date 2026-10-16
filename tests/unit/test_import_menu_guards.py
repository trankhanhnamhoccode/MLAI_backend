"""Catalog source validation distinguishes paused, missing and unreviewed labels."""
from uuid import uuid4
import pytest
from app.application.contracts import import_mapping as dto
from tests.unit.test_import_preview import case


@pytest.mark.parametrize('active', [None, 'Đang bán', 'Tạm dừng', 'unknown'])
def test_catalog_missing_or_unreviewed_status_never_becomes_true_or_false(active):
    source = dict(source_business_key='INDEPENDENT', name='Independent item',
                  selling_unit='cup', sku=None, price='19000', active=active)
    row, = case('products', [source])
    assert row.classification == 'INVALID' and row.blockers and row.after is None


def test_paused_catalog_metadata_conflict_cannot_overwrite_existing_product():
    ident=uuid4()
    metadata=dict(name='Independent paused item',selling_unit='cup',sku=None,price='19000',active=False)
    reservation=dto.EntityReservation(proposal_id=uuid4(),entity='product',source_business_key='INDEPENDENT',
        reserved_canonical_id=ident,metadata=dto.ProductMetadata(**metadata),
        evidence_reference='Synthetic explicit paused status',approval_revision='rev-1')
    row,=case('products',[dict(source_business_key='INDEPENDENT',**metadata)],
        dict(products=[dict(id=str(ident),**{**metadata,'active':True})]),entities=(reservation,))
    assert any(b.code == 'ENTITY_METADATA_CONFLICT' for b in row.blockers)
    assert row.after.active is False


@pytest.mark.parametrize('token', [
    'Sinh tố dâu size L lạnh', 'Sinh tố dâu size S lạnh',
    'Sinh tố dâu', 'Sinh tố dâu size L', 'Sinh tố dâu size XL lạnh', 'Trà đào',
])
def test_product_names_preserved_without_automatic_binding_or_sku_inference(token):
    from app.application.import_analysis import discover, identity_issues
    from app.infrastructure.import_parser import parse_source
    from tests.unit.test_import_field_values import spec
    sheets,issues,sources=discover(uuid4(),parse_source(('sales.product_id\n'+token+'\n').encode(),'csv'))
    names=('Sinh tố dâu size L lạnh','Sinh tố dâu size S lạnh','Trà đào','Trà đào')
    snapshot=dict(products=[dict(id=str(uuid4()),name=name,sku='UNRELATED-'+str(n),selling_unit='cup')
        for n,name in enumerate(names)],ingredients=[],suppliers=[],inventory_lots=[])
    profile=spec('sales',('product_id',))
    found=identity_issues(sheets,issues,sources,snapshot,{str(sheets[0].sheet_id):profile})
    identity,=[i for i in found if i.issue_type=='identity']
    assert identity.source_header==token and identity.resolution is None and identity.status=='unmatched'
    # Current guard: even a unique exact name is still a candidate/choice, not
    # authority to bind. Duplicate/partial/near names cannot auto-merge either.


def test_reviewed_full_name_binding_does_not_cover_other_size_or_temperature():
    from app.application.import_analysis import discover, identity_issues
    from app.infrastructure.import_parser import parse_source
    from tests.unit.test_import_field_values import spec
    names=('Sinh tố dâu size L lạnh','Sinh tố dâu size S lạnh','Sinh tố dâu size L nóng')
    ids=[uuid4() for _ in names]
    sheets,issues,sources=discover(uuid4(),parse_source(('sales.product_id\n'+'\n'.join(names)+'\n').encode(),'csv'))
    profile=spec('sales',('product_id',)).model_copy(update={'identity_rules':(
        dto.IdentityRule(entity='product',source_token=names[0],canonical_id=ids[0]),)})
    snapshot=dict(products=[dict(id=str(ident),name=name,sku=None,selling_unit='cup')
        for ident,name in zip(ids,names)],ingredients=[],suppliers=[],inventory_lots=[])
    found=identity_issues(sheets,issues,sources,snapshot,{str(sheets[0].sheet_id):profile})
    assert {i.source_header for i in found if i.issue_type=='identity'}==set(names[1:])
