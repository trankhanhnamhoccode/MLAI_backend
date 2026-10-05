# Fixtures

CURRENT FACT: no canonical demo seed exists. Tests use fixed health
values and the separate local PostgreSQL `shelfcash_test` database with revision
`0003_catalog_recipe`. Destructive fixtures own only its `public` schema. S1.1
schema tests create isolated User/Store/Membership records with fixed fields;
explicit IDs are deterministic where needed, generated UUID identity is otherwise
asserted by type/default. No production password/credential fixture is supplied.

S1.2 tests create fixed COFFEE/MILK records, two stores, 2026-01-01 through
2026-03-31 recipe dates and adjacent 2026-04-01 version, exact Decimal price/yield/
quantity/loss values. Generated UUIDs represent relationships rather than expected
business facts. Each test resets its isolated schema; no canonical demo seed or
BOM/golden computation scenario is supplied.

PROPOSAL: add versioned deterministic fixture inputs and independently specified
expected business facts with the relevant feature slice. NORMAL_WEEK,
PROMOTION_SPIKE, LOW_BUDGET, SUPPLIER_DELAY and EXPIRY_RISK are future scenarios;
they are not currently executable.
