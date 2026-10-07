"""Internal validated persistence use cases. No HTTP contracts or engines.

Call domain-specific use cases with typed contracts and an explicit synchronous
Session. Write methods own a complete transaction; caller owns Session close.
See docs/features/APPLICATION_CONTRACTS.md.
"""
