"""Freeze one canonical sales effect per Product/day, retaining contribution lineage."""
from collections import defaultdict
from decimal import Decimal
from fractions import Fraction

from app.application.contracts import import_mapping as dto
from app.application.import_sales_sources import sources_for, latest_source, classify_sales
from app.domain.forecasting.stockout import aggregate_stockout


def finish_sales(rows, specs, snapshot):
    from app.application.import_preview import notice, exact_text
    groups = defaultdict(list)
    output = []
    for row in rows:
        if row.after is None or row.after.domain != 'sales':
            output.append(row)
        else:
            groups[row.after.product_id, row.after.sales_date].append(row)
    for (product, day), group in sorted(groups.items()):
        def identity(row):
            scope = specs[str(row.source_location.sheet_id)].scope
            return scope.source_system_key, scope.report_type, row.after.business_report_key
        group.sort(key=lambda r: (*identity(r), str(r.source_location.file_id), str(r.source_location.sheet_id), r.source_location.record_number or 0))
        first = group[0]
        blockers = [b for row in group for b in row.blockers if b.code != 'DUPLICATE_DAILY_OBSERVATION']
        by_identity = defaultdict(list)
        for row in group:
            by_identity[identity(row)].append(row)
        contributions = []
        for key, duplicates in sorted(by_identity.items()):
            sample = duplicates[0]
            values = {(Decimal(r.normalized_source_quantity), r.normalized_source_stockout,
                       r.stockout_update, r.after.unit,
                       specs[str(r.source_location.sheet_id)].sales_semantics) for r in duplicates}
            if len(values) != 1:
                blockers.append(notice('SALES_CONTRIBUTION_CONFLICT', sample.source_location))
            contributions.append(dto.SalesContribution(source_system_key=key[0], report_type=key[1],
                business_report_key=key[2], semantics=specs[str(sample.source_location.sheet_id)].sales_semantics,
                quantity=sample.normalized_source_quantity, is_stockout=sample.normalized_source_stockout,
                stockout_update=sample.stockout_update,
                source_locations=tuple(r.source_location for r in duplicates),
                provenance=tuple(p for r in duplicates for p in r.provenance)))
        current = next((r for r in snapshot['sales_daily'] if r['product_id'] == str(product) and r['sales_date'] == str(day)), None)
        after, action, classification = first.after, first.proposed_action, first.classification
        if len(contributions) == 1 and not blockers:
            candidate = first.after.model_copy(update={'quantity': contributions[0].quantity})
            target, action, classification, blocker = classify_sales(candidate, current,
                specs[str(first.source_location.sheet_id)], snapshot)
            if blocker:
                blockers.append(notice(blocker, first.source_location))
            contribution = contributions[0]
            prior = latest_source(sources_for(snapshot, product, day), contribution.source_system_key,
                contribution.business_report_key, contribution.report_type)
            revised = prior is not None and (Decimal(prior['source_quantity']) != Decimal(contribution.quantity)
                or prior.get('source_stockout') is not contribution.is_stockout)
            if current and action == 'NO_OP' and (after.is_stockout is not current.get('is_stockout') or revised):
                action, classification = 'REPLACE_DAILY_TOTAL', 'CHANGED'
        if len(contributions) > 1:
            if any(c.semantics != 'disjoint_contribution' for c in contributions):
                blockers.append(notice('SALES_OVERLAP_UNRESOLVED', first.source_location))
            else:
                history = sources_for(snapshot, product, day)
                total = Fraction(Decimal(current['quantity'])) if current else Fraction(0)
                new = False
                revised = False
                latest = {}
                for r in history:
                    key = r['source_system_key'], r.get('report_type', contributions[0].report_type), r['business_report_key']
                    if key not in latest or latest[key]['source_revision'] < r['source_revision']:
                        latest[key] = r
                for c in contributions:
                    old = latest_source(history, c.source_system_key, c.business_report_key, c.report_type)
                    total += Fraction(Decimal(c.quantity)) - (Fraction(Decimal(old['source_quantity'])) if old else 0)
                    new |= old is None
                    revised |= old is not None and (Decimal(old['source_quantity']) != Decimal(c.quantity)
                        or old.get('source_stockout') is not c.is_stockout)
                    latest[c.source_system_key, c.report_type, c.business_report_key] = {'source_stockout': c.is_stockout}
                flags = [r.get('source_stockout') for r in latest.values()]
                baseline = next((r['baseline'] for r in history if r.get('baseline')), None)
                if baseline:
                    flags.append(baseline.get('is_stockout'))
                elif current and not history:
                    flags.append(current.get('is_stockout'))
                if total < 0:
                    blockers.append(notice('SALES_OVERLAP_UNRESOLVED', first.source_location))
                elif len(exact_text(total)) > 200:
                    blockers.append(notice('NUMERIC_RESOURCE_LIMIT', first.source_location))
                else:
                    flag = aggregate_stockout(tuple(flags))
                    after = after.model_copy(update={'quantity': exact_text(total), 'is_stockout': flag})
                    unchanged = current and total == Fraction(Decimal(current['quantity'])) and flag is current.get('is_stockout') and not new and not revised
                    action = 'NO_OP' if unchanged else 'MERGE_DISJOINT_SALES' if new else 'REPLACE_DAILY_TOTAL'
                    classification = 'UNCHANGED' if unchanged else 'CHANGED' if current else 'NEW'
        changes = tuple(dto.Change(field=k, before=str(getattr(first.before, k)), after=str(getattr(after, k)))
                        for k in ('quantity', 'is_stockout') if first.before and getattr(first.before, k) != getattr(after, k))
        provenance = tuple(p.model_copy(update={'origin': 'DETERMINISTIC_DERIVED',
            'applied_rule_ids': p.applied_rule_ids + ('sales:planned_total_from_declared_contributions',)})
            if p.field == 'quantity' and Decimal(after.quantity) != Decimal(contributions[0].quantity)
            else p.model_copy(update={'origin': 'DETERMINISTIC_DERIVED',
                'applied_rule_ids': p.applied_rule_ids + ('stockout:contribution_aggregation',)})
            if p.field == 'is_stockout' and after.is_stockout is not contributions[0].is_stockout
            else p for p in first.provenance)
        output.append(first.model_copy(update=dict(after=after, changes=changes,
            provenance=provenance,
            proposed_action='BLOCKED' if blockers else action,
            classification='CONFLICT' if blockers else classification,
            blockers=tuple(blockers), sales_contributions=tuple(contributions),
            confirmation_required=not blockers and action in {'REPLACE_DAILY_TOTAL', 'MERGE_DISJOINT_SALES'},
            source_locations=tuple(r.source_location for r in group),
            dependencies=tuple(sorted({d for r in group for d in r.dependencies}, key=str)),
            warnings=tuple(w for r in group for w in r.warnings))))
    return tuple(output)
