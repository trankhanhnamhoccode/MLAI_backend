"""Concrete synchronous access contracts; callers own sessions and transactions.

Import repositories from their domain modules. Returned ORM rows are for
application orchestration; plain Python domain computation must not import them.
See docs/features/PERSISTENCE_ACCESS.md for the internal contract.
"""
