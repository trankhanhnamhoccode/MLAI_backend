"""Canonical fee bindings shared by readiness and coherent planning capture."""
from dataclasses import dataclass
from collections.abc import Mapping,Sequence
from app.application.contracts.import_domains import FeeSource


@dataclass(frozen=True)
class FeeBindings:
    term_keys: Mapping[str,str]
    supplier_keys: Mapping[str,frozenset[str]]

    def covers(self,fee: FeeSource,terms: Sequence[Mapping[str,object]]) -> bool:
        if fee.mode=='NONE':return True
        if fee.mode=='PER_OFFER':
            known=set(self.term_keys.values())
            return (all(c.source_term_key in known for c in fee.components)
                and all(self.term_keys.get(str(t['id'])) in fee.covered_source_term_keys for t in terms))
        known={key for keys in self.supplier_keys.values() for key in keys}
        covered=set(fee.covered_source_supplier_keys)
        return (all(c.source_supplier_key in known for c in fee.components)
            and all(self.supplier_keys.get(str(t['supplier_id']),frozenset()) & covered for t in terms))


def fee_bindings(term_sources: Sequence[Mapping[str,object]],supplier_sources: Sequence[Mapping[str,object]],
                 source_system: str | None) -> FeeBindings:
    suppliers: dict[str,set[str]]={}
    for row in supplier_sources:
        if row['source_system_key']==source_system:
            suppliers.setdefault(str(row['supplier_id']),set()).add(str(row['source_record_key']))
    return FeeBindings(term_keys={str(row['id']):str(row['source_record_key']) for row in term_sources
        if row['source_system_key']==source_system},supplier_keys={ident:frozenset(keys) for ident,keys in suppliers.items()})
