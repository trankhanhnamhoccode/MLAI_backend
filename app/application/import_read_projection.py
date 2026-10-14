"""Projection of retained mapping/source/preview evidence, never canonicalization."""
from collections import Counter, defaultdict
from decimal import Decimal
from uuid import UUID
from app.application.contracts.auth import AuthError
from app.application.contracts import import_mapping as dto
from app.application.import_identity import content_digest
from app.domain.inventory.read_rules import decimal_text


def mapping_selection(issues, sheets, scope, *, file_ids=None):
    if scope.sheet_id and not any(s.sheet_id==scope.sheet_id for s in sheets):
        raise AuthError('RESOURCE_NOT_FOUND',404)
    known_files=set(file_ids) if file_ids is not None else {s.file_id for s in sheets}
    if scope.file_id and scope.file_id not in known_files:
        raise AuthError('RESOURCE_NOT_FOUND',404)
    def counts(rows):
        statuses=Counter(i.status for i in rows)
        origins=Counter(i.suggestion_origin or 'NONE' for i in rows)
        return dto.MappingIssueCounts(total=len(rows),by_status=dto.MappingStatusCounts(**statuses),
            by_origin=dto.MappingOriginCounts(**origins))
    file_sheets={s.sheet_id for s in sheets if not scope.file_id or s.file_id==scope.file_id}
    selected=[i for i in issues if i.sheet_id in file_sheets
        and (scope.sheet_id is None or i.sheet_id==scope.sheet_id)
        and (not scope.review_only or i.status!='auto_mapped')
        and (scope.status is None or i.status==scope.status)
        and (scope.origin is None or (i.suggestion_origin or 'NONE')==scope.origin)]
    return selected,dto.MappingCounters(batch=counts(issues),filtered=counts(selected))


def locations(row):
    return row.source_locations or (row.source_location,)


def in_scope(location, scope):
    return (scope.file_id is None or location.file_id==scope.file_id) and (scope.sheet_id is None or location.sheet_id==scope.sheet_id)


def scoped_rows(rows,scope):
    return [r for r in rows if (scope.classification is None or r.classification==scope.classification)
            and any(in_scope(loc,scope) for loc in locations(r))]


def pinned_sources(payload, analysis):
    sources=(analysis or {}).get('sources',())
    if payload.get('source_evidence_digest') is None or content_digest(sources)!=payload['source_evidence_digest']:
        return None
    return sources


def aggregate(rows,sources,scope):
    selected=scoped_rows(rows,scope)
    groups=defaultdict(list)
    for row in selected:groups[(row.canonical_domain or (row.after.domain if row.after else None),row.proposed_action)].append(row)
    raw=None
    if sources is not None:
        # Raw records are counted once, independently of synthetic/master actions.
        matched={(str(loc.sheet_id),loc.row_number) for row in selected for loc in locations(row) if in_scope(loc,scope)}
        raw=sum(1 for sheet in sources for row in sheet['rows']
            if (scope.sheet_id is None or sheet['sheet_id']==str(scope.sheet_id))
            and (scope.file_id is None or sheet['file_id']==str(scope.file_id))
            and (scope.classification is None or (sheet['sheet_id'],row['row_number']) in matched))
    def notices(field):
        codes=Counter(code for row in selected for code in {n.code for n in getattr(row,field)})
        return tuple(dto.NoticeActionCount(code=code,action_count=count) for code,count in sorted(codes.items()))
    return dto.ScopedPreviewAggregate(scope=scope,
        raw_source_rows=dto.RawSourceRowCount(availability='available' if raw is not None else 'unavailable',count=raw),
        logical_action_count=len({r.row_id for r in selected}),
        by_classification=dto.ClassificationCounts(**Counter(r.classification for r in selected)),
        groups=tuple(dto.PreviewActionGroupCount(canonical_domain=domain,proposed_action=action,action_count=len(values),
            blocked_action_count=sum(bool(r.blockers) for r in values),warning_action_count=sum(bool(r.warnings) for r in values))
            for (domain,action),values in sorted(groups.items(),key=lambda entry:str(entry[0]))),
        blockers=notices('blockers'),warnings=notices('warnings'))


def preview_aggregates(payload,rows,sources,scope):
    sheets=payload.get('reviewed_sheets',())
    return dto.PreviewAggregates(preview_id=payload['summary']['preview_id'],preview_digest=payload['summary']['digest'],
        batch=aggregate(rows,sources,dto.PreviewScope(classification=scope.classification)),
        selected=aggregate(rows,sources,scope),
        files=tuple(aggregate(rows,sources,dto.PreviewScope(file_id=UUID(fid),classification=scope.classification))
            for fid in sorted({s['file_id'] for s in payload.get('source_files',sheets)})),
        sheets=tuple(aggregate(rows,sources,dto.PreviewScope(file_id=UUID(sh['file_id']),sheet_id=UUID(sh['sheet_id']),classification=scope.classification))
            for sh in sheets))


def planned_effect(row,read_set_digest):
    value=row.after
    if row.receipt_effect:return dto.ReceiptPlannedEffect(**row.receipt_effect.model_dump())
    if value is None or row.blockers:return None
    domain=value.domain;identity=row.target_reserved_or_existing_id
    if domain=='opening_stock':
        return dto.OpeningEffect(lot_id=value.lot_id,action='reuse' if row.proposed_action=='NO_OP' else 'create',
            quantity_delta=row.inventory_effect.quantity_delta if row.inventory_effect else value.quantity,
            unit=value.unit,observed_at=value.observed_at)
    if domain=='inventory_count' and row.before is not None:
        return dto.CountEffect(lot_id=value.lot_id,before_quantity=row.before.on_hand,after_quantity=value.on_hand,
            delta=decimal_text(Decimal(value.on_hand)-Decimal(row.before.on_hand)),unit=value.unit,expected_version=read_set_digest)
    if domain=='sales':
        action={'NO_OP':'reuse','REPLACE_DAILY_TOTAL':'replace','MERGE_DISJOINT_SALES':'merge'}.get(row.proposed_action,'record')
        return dto.SalesEffect(product_id=value.product_id,date=value.sales_date,action=action,
            before_quantity=row.before.quantity if row.before else None,after_quantity=value.quantity,unit=value.unit,expected_version=row.expected_version)
    if domain in ('products','ingredients','suppliers'):
        kind={'products':'product','ingredients':'ingredient','suppliers':'supplier'}[domain]
        identity=identity or next((ref.canonical_id for ref in row.entity_refs if ref.entity==kind),None)
        if identity is None:return None
        return dto.CatalogEffect(entity=kind,
            id=identity,action='reuse' if row.proposed_action=='NO_OP' else 'create',expected_version=row.expected_version)
    if domain=='recipes':
        return dto.RecipeEffect(product_id=value.product_id,recipe_id=identity,
            action='reuse' if row.proposed_action=='NO_OP' else 'create_version',
            identity_availability='available' if identity else 'not_reserved',recipe_version=value.version,effective_from=value.effective_from,
            effective_to=value.effective_to,dependency_ids=row.dependencies)
    if identity is None:return None
    if domain in ('supplier_terms','payable_fees'):
        return dto.SupplierEffect(entity='supplier_term' if domain=='supplier_terms' else 'payable_fee',id=identity,
            action='reuse' if row.proposed_action=='NO_OP' else 'close_period' if 'AMEND' in row.proposed_action else 'create_version',expected_version=row.expected_version)
    if domain=='scope_declarations':
        return dto.DeclarationEffect(id=identity,action='reuse' if row.proposed_action=='NO_OP' else 'declare',
            dependency_ids=row.dependencies,expected_version=row.expected_version)
    if domain in ('calendar_events','promotion_observations','usage_history','purchase_history'):
        return dto.HistoryEffect(domain=domain,id=identity,action='reuse' if row.proposed_action=='NO_OP' else 'record',expected_version=row.expected_version)
    return None


def source_effect_row(row,payload,sources,*,max_cells=200,source_index=None):
    cells=[];unavailable=False;truncated=False
    headers={sh['sheet_id']:sh['headers'] for sh in payload.get('reviewed_sheets',())}
    source_rows=source_index if source_index is not None else {(sh['sheet_id'],r['row_number']):r for sh in (sources or ()) for r in sh['rows']}
    seen=set()
    for loc in locations(row):
        key=str(loc.sheet_id),loc.row_number
        if key in seen:continue
        seen.add(key);raw=source_rows.get(key)
        if raw is None:unavailable=True;continue
        for cell in raw['cells']:
            if len(cells)>=max_cells:truncated=True;break
            label=headers.get(str(loc.sheet_id),())
            label=label[cell['column_index']] if cell['column_index']<len(label) else None
            projected,partial=source_evidence_cell(cell,label,loc.model_copy(update={'source_column_index':cell['column_index']}))
            unavailable=unavailable or partial
            cells.append(projected)
    notices=row.warnings
    if unavailable or truncated:
        notices+= (dto.Notice(code='SOURCE_CELL_DISPLAY_UNAVAILABLE',severity='WARNING',message='Source evidence display is incomplete.',source_location=row.source_location),)
    return dto.SourceEffectRow(**row.model_dump(exclude={'warnings'}),warnings=notices,source_cells=tuple(cells),
        planned_effect=planned_effect(row,payload['read_set_digest']),
        source_evidence_availability='unavailable' if not cells else 'partial' if unavailable or truncated else 'available',
        source_cells_truncated=truncated)


def source_effect_rows(rows,payload,sources):
    index={(sh['sheet_id'],r['row_number']):r for sh in (sources or ()) for r in sh['rows']}
    remaining=2000;result=[]
    for row in rows:
        expanded=source_effect_row(row,payload,sources,max_cells=min(200,remaining),source_index=index)
        remaining-=len(expanded.source_cells);result.append(expanded)
    return tuple(result)


def source_evidence_cell(cell,label,location):
    """Shared C2 MQ03/C4 display rule: never pass truncated facts as evidence."""
    raw=cell.get('raw');partial=False
    if raw is not None and len(raw)>200:raw=None;partial=True
    if label is not None and len(label)>200:label=None;partial=True
    return dto.SourceEvidenceCell(location=location,column_label=label,raw_value=raw,
        cell_kind=cell['kind'],formula_present=cell.get('formula',False)),partial
