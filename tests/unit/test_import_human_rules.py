"""General lexical rules and negative sampled evidence, unrelated to cafe names/files."""
import pytest
from uuid import uuid4
from app.application.import_descriptors import sheet_rules
from app.application.import_analysis import discover
from app.infrastructure.import_parser import parse_source


@pytest.mark.parametrize('headers',[
    ('Ngày bán','Tên món','SL bán','ĐVT'),
    ('SL ban','DVT','Ten mon','Ngay GD'),
])
def test_sold_quantity_alias_works_reordered_and_without_accents(headers):
    result=sheet_rules(headers,'unrelated report',samples=tuple(('13',) for _ in headers))
    assert result.schema=='sales'
    column=next(c for c in result.columns if c.target=='sales.quantity')
    assert column.requires_review and 'CONTEXTUAL_SOLD_QUANTITY' in column.reason


@pytest.mark.parametrize('value',['not a count','NaN','Infinity','-1','1e9999x'])
def test_quantity_text_is_candidate_not_deterministic_proposal(value):
    result=sheet_rules(('Ngày bán','Tên món','SL bán'),'arbitrary',samples=((),(),(value,)))
    assert result.columns[2].target is None
    assert result.columns[2].candidates==('sales.quantity',)
    assert 'QUANTITY_SAMPLE_TYPE_REVIEW' in result.columns[2].reason


def test_generic_and_conflicting_workflow_do_not_force_sales():
    assert sheet_rules(('Tên món','SL bán','ĐVT'),'sales').schema is None
    hint=sheet_rules(('Ngày bán','Tên món','SL bán','Ngày kiểm kê'),'arbitrary').columns[2]
    assert hint.target is None and hint.candidates==('sales.quantity',)


@pytest.mark.parametrize('preamble',['','BÁO CÁO GIẢ\n','BÁO CÁO GIẢ\nNguồn do người dùng khai báo\n\n'])
def test_header_row_variants_retain_physical_evidence(preamble):
    sheets,issues,sources=discover(uuid4(),parse_source((preamble+'Ngày bán,Tên món,SL bán,ĐVT\n2026-01-01,Nước ép size XL,2,cup\n').encode(),'csv'))
    assert sheets[0].selected_type=='sales' and sheets[0].row_count==1
    assert sheets[0].header_row==preamble.count('\n')+1
    assert sources[0]['rows'][0]['row_number']==sheets[0].header_row+1
