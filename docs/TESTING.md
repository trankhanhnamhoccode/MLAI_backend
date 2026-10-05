# Testing

## CURRENT FACT — local verification

Supported full verification command from `backend/`: `./scripts/test.ps1 all` on
Windows PowerShell, or `sh scripts/test.sh all` on POSIX. Both use the repository
`.venv` and propagate pytest's exit status. Use `unit`, `integration`, `api`, `e2e`
or `all` (default) as the category. Tests live under those directories; reusable
fixed inputs belong under `tests/fixtures/`. CURRENT FACT: `e2e` reports no tests
implemented and exits zero; this is not evidence of business-flow coverage.

Developer commands:

| Workflow | PowerShell | POSIX |
| --- | --- | --- |
| All tests | `./scripts/test.ps1 all` | `sh scripts/test.sh all` |
| Integration tests | `./scripts/test.ps1 integration` | `sh scripts/test.sh integration` |
| Reset + migrations | `./scripts/reset_db.ps1` | `sh scripts/reset_db.sh` |
| Reset + migrations + seed | `./scripts/reset_db.ps1 -Seed` | `sh scripts/reset_db.sh --seed` |
| Seed/check baseline | `./scripts/seed_demo.ps1` | `sh scripts/seed_demo.sh` |
| Inspect persisted state | `./scripts/db_status.ps1` | `sh scripts/db_status.sh` |
| Reachability before migration | `./scripts/db_status.ps1 -AllowUnmigrated` | `sh scripts/db_status.sh --allow-unmigrated` |

Reset permits only local `shelfcash`/`shelfcash_test`, environment development/test;
test permits only the latter. Stop DB users beforehand. Reset transactionally
recreates `public`, then upgrades to Alembic head. Status opens a fresh read-only
PostgreSQL transaction, reports reachability, database/server version/revision,
migration head and table counts. Unreachable databases fail; unmigrated databases
fail unless reachability-only behavior is explicitly selected. No state is created
by inspection. Seed verifies the current identity/store and catalog/recipe table set at head and writes
no data; demo seeding is not implemented. Normal workflows require no hosted notebook
or provider. After reset all seven business tables are empty.

See [FULL_TEST_FLOW](runbooks/FULL_TEST_FLOW.md) for fresh setup, live HTTP checks,
SQL inspection and exact expected state; [SCAFFOLD](features/SCAFFOLD.md) describes
implemented feature verification and limitations.

S1.2 targeted schema verification:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/integration/test_catalog_recipe_schema.py -q
```

POSIX: `.venv/bin/python -m pytest tests/integration/test_catalog_recipe_schema.py -q`.
These isolated PostgreSQL tests verify all four fresh-session round trips, SKU/null
semantics, exact NUMERIC, version/period/overlap, yield/loss, line quantity/uniqueness,
unit and cross-store composite FKs, parent mutations and downgrade/re-upgrade.
See [CATALOG_RECIPE](features/CATALOG_RECIPE.md) for fixtures and SQL inspection.
Migration installs btree_gist via the local role; no host DB package is required.

S1.1 targeted schema verification:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/integration/test_identity_store_schema.py -q
```

POSIX equivalent: `.venv/bin/python -m pytest tests/integration/test_identity_store_schema.py -q`.
These tests exercise actual UUID PKs, email/pair uniqueness, role/FK/check constraints,
defaults, metadata/migration agreement and fresh-session User/Store/Membership reads.
UTC engine sessions and ORM updated_at semantics are tested; raw SQL timestamp
maintenance remains caller responsibility. See
[STORE_IDENTITY](features/STORE_IDENTITY.md) for exact manual inspection and limitations.

From `backend/`: `.\.venv\Scripts\python.exe -m pytest` on Windows, or
`.venv/bin/python -m pytest` on POSIX. Smoke tests verify import, health payload and
Pydantic/OpenAPI agreement, exact route inventory and domain import without transport,
ORM or infrastructure. Unit tests assert config/driver and forbid eager DB connection
on engine construction/import/startup/health. API tests require no database. Integration
tests execute actual PostgreSQL queries, migrate up/down, use synchronous Session,
assert durable state through fresh connections, and exercise reset/seed/status/error
behavior across processes. No external HTTP call or provider credential is needed.

## PostgreSQL dependency and isolation — CURRENT FACT

Start Docker, then `docker compose up -d postgres` and
`docker compose up -d --wait --wait-timeout 90 postgres` from `backend/`.
`docker compose ps` must show healthy. The default native URL is
`postgresql+psycopg://shelfcash:shelfcash@127.0.0.1:5432/shelfcash`.
`TEST_DATABASE_URL` defaults to the same local role/server and database
`shelfcash_test`. Configure it in `.env` when port/credentials differ.

Integration fixtures create `shelfcash_test` if absent through the `postgres`
maintenance DB, then own/reset only its public schema before/after each test.
The official Compose role has the required local permissions. Unsafe test targets
are rejected before connection. Tests never destructively operate on `shelfcash`.
Run suites sequentially; concurrent test/reset clients against the same test DB
are unsupported. Missing PostgreSQL is an integration failure, not a skipped test.
`test unit`/`test api` work without a live DB; `test integration`/`test all` require it.

## Platform verification

Windows PowerShell commands are runtime-verified when recorded in CURRENT_STATE.
POSIX `.sh` scripts are provided with the same shared Python implementation.
In this Windows session they are shell-syntax checked with Git Bash `bash -n`
only; native POSIX runtime execution has not been verified. Syntax validation
must not be described as successful runtime verification.

## ACCEPTED DECISION — layers for future slices

1. Domain invariant unit tests: plain Python quantities/dates and rules, no DB/server/LLM.
2. Application/use-case tests: orchestration, permission boundaries, failure behavior,
   transaction scope and deterministic output with explicit dependencies.
3. Repository/infrastructure integration tests: isolated PostgreSQL, migrations, same-store
   relations, round trips, constraints and actual query behavior; isolate file artifacts.
4. API contract tests: Pydantic/OpenAPI request/response shape, status/errors, access checks;
   use in-process ASGI client, compare schema when public operations change.
5. Golden scenarios: fixed versioned inputs, deterministic expected metrics/recommendation
   and snapshot evidence. Define expected values before implementing the computation.

Tests must verify observable business behavior rather than mirror implementation.
Run targeted tests and relevant regressions per slice; full suite when warranted.
For public contract changes, inspect an OpenAPI diff/check. Preserve reproducible
inputs/model versions; external providers are replaced at the gateway boundary.

Major feature completion requires implementation, automated tests, relevant
integration/persistence coverage, reproducible manual steps, deterministic fixtures
where practical, fresh-connection DB assertions where persistence is involved,
and canonical feature documentation. Verify both API/application results and
committed database state; never use HTTP 2xx or the writer's ORM identity alone.
Update CURRENT_STATE and the relevant `docs/features/` document after each major
slice; update testing/runbook/schema/API documents when their scope changes.
Record only implemented feature contracts; do not create speculative feature docs.

## Future golden scenarios — PROPOSAL, not existing tests

| Scenario | Input condition | Acceptance evidence to freeze in S3 |
| --- | --- | --- |
| NORMAL_WEEK | Stable demand, usable stock, normal supplier terms | Demand reconciliation, three candidate simulations and deterministic comparison |
| PROMOTION_SPIKE | Explicit promotion/demand increase | Increased demand, measured shortage/service/capital tradeoffs without LLM selection |
| LOW_BUDGET | Binding purchase budget | Feasibility and warnings; no concealed overspend or fabricated feasible candidate |
| SUPPLIER_DELAY | Delayed arrival relative to demand dates | Stock unavailable before arrival; deterministic shortage/service consequences |
| EXPIRY_RISK | Lots expiring within planning horizon | FEFO allocation, excluded expired stock and exact waste evidence |

## Mandatory future invariants — ACCEPTED DECISION

- Demand = 100, usable inventory = 20 → raw procurement need = 80 (before pack/MOQ rules).
- Requirement = 83, pack size = 10 → rounded purchase quantity = 90.
- Expired inventory lot → zero usable quantity for future demand.
- Supplier lead time = 3 days → incoming inventory unavailable before arrival.
- Order placed → MOQ respected; purchase quantity obeys pack size.
- FEFO → earliest usable expiry chosen, never expired/not-yet-arrived lots.
- Future demand dates → strictly after frozen cutoff boundary.
- Unauthorized user → state-changing action rejected by backend.
- What-if budget permission → does not imply real-budget mutation permission.
- No provider available → deterministic decision flow still functions.
- Historical DecisionRun → unchanged meaning after current inventory/terms/constraints change.

These scenarios/invariants are specifications for future implementation, not claims
that forecast, FEFO, procurement, simulation or authorization works in this scaffold.
