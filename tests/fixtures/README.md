# Fixtures

CURRENT FACT: S0 has no business input fixtures or seed rows. Tests use fixed health
values and isolated temporary SQLite databases with revision `0001_scaffold`.

PROPOSAL: add versioned deterministic fixture inputs and independently specified
expected business facts with the relevant feature slice. NORMAL_WEEK,
PROMOTION_SPIKE, LOW_BUDGET, SUPPLIER_DELAY and EXPIRY_RISK are future scenarios;
they are not currently executable.
