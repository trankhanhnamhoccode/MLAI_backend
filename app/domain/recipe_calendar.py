"""Inclusive date-only calendar validation; no HTTP, persistence or Pydantic."""
from dataclasses import dataclass
from datetime import date, timedelta
from uuid import UUID


@dataclass(frozen=True)
class Period:
    recipe_id: UUID
    start: date
    end: date | None


def history_unchanged(before: tuple[Period, ...], after: tuple[Period, ...], today: date) -> bool:
    def past(periods):
        return sorted((str(p.recipe_id), p.start, min(p.end or date.max, today))
                      for p in periods if p.start <= today)
    return past(before) == past(after)


def overlaps(periods: tuple[Period, ...]) -> bool:
    ordered = sorted(periods, key=lambda p: (p.start, str(p.recipe_id)))
    return any((a.end or date.max) >= b.start for a, b in zip(ordered, ordered[1:]))


def gaps(periods: tuple[Period, ...], minimum: date) -> tuple[tuple[date, date | None], ...]:
    """Future availability, including leading/trailing uncovered ranges. No fill."""
    cursor = minimum
    result = []
    for p in sorted(periods, key=lambda p: (p.start, str(p.recipe_id))):
        if p.end is not None and p.end < cursor:
            continue
        if p.start > cursor:
            result.append((cursor, p.start - timedelta(days=1)))
        if p.end is None or p.end == date.max:
            return tuple(result)
        cursor = max(cursor, p.end + timedelta(days=1))
    result.append((cursor, None))
    return tuple(result)


def changed_ranges(before: tuple[Period, ...], after: tuple[Period, ...], minimum: date):
    boundaries = {minimum}
    for p in before + after:
        if p.start >= minimum:
            boundaries.add(p.start)
        if p.end is not None and minimum <= p.end < date.max:
            boundaries.add(p.end + timedelta(days=1))
    ordered = sorted(boundaries)
    result = []
    def identities(periods, day):
        return {p.recipe_id for p in periods if p.start <= day <= (p.end or date.max)}
    for index, start in enumerate(ordered):
        end = ordered[index+1] - timedelta(days=1) if index+1 < len(ordered) else None
        if identities(before,start) == identities(after,start):
            continue
        if result and result[-1][1] is not None and result[-1][1] + timedelta(days=1) == start:
            result[-1] = result[-1][0], end
        else:
            result.append((start,end))
    return tuple(result)
