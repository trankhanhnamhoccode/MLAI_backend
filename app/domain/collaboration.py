"""Pure permission request transitions and additive grant decisions."""
from dataclasses import dataclass


def permission_request_state(state: str, requested: tuple[str, ...], current: tuple[str, ...], *, eligible: bool) -> str:
    if state != 'pending':
        return state
    if not eligible:
        return 'invalidated'
    return 'satisfied' if set(requested) <= set(current) else 'pending'


@dataclass(frozen=True)
class GrantUnion:
    grants: tuple[str, ...]
    added: tuple[str, ...]


def grant_union(requested: tuple[str, ...], approved: tuple[str, ...], current: tuple[str, ...]) -> GrantUnion:
    selected = set(approved)
    if not selected or not selected <= set(requested):
        raise ValueError('INVALID_APPROVED_SUBSET')
    return GrantUnion(tuple(sorted(set(current) | selected)), tuple(sorted(selected - set(current))))
