# Fixtures

CURRENT FACT: no canonical demo seed exists. Tests use fixed health
values and the separate local PostgreSQL `shelfcash_test` database with revision
`0002_identity_store`. Destructive fixtures own only its `public` schema. S1.1
schema tests create isolated User/Store/Membership records with fixed fields;
explicit IDs are deterministic where needed, generated UUID identity is otherwise
asserted by type/default. No production password/credential fixture is supplied.

PROPOSAL: add versioned deterministic fixture inputs and independently specified
expected business facts with the relevant feature slice. NORMAL_WEEK,
PROMOTION_SPIKE, LOW_BUDGET, SUPPLIER_DELAY and EXPIRY_RISK are future scenarios;
they are not currently executable.
