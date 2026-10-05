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
by inspection. Seed verifies the current S1.1/S1.2/S1.3 table set at head and writes
no data; demo seeding is not implemented. Normal workflows require no hosted notebook
or provider. After reset all sixteen business tables are empty.

See [FULL_TEST_FLOW](runbooks/FULL_TEST_FLOW.md) for fresh setup, live HTTP checks,
SQL inspection and exact expected state; [SCAFFOLD](features/SCAFFOLD.md) describes
implemented feature verification and limitations.

S1.3 targeted schema verification:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/integration/test_supplier_operational_constraints.py -q
```

POSIX: `.venv/bin/python -m pytest tests/integration/test_supplier_operational_constraints.py -q`.
Actual isolated PostgreSQL: six-model commit/close/fresh-session reads, many-to-many
terms/version/partial overlap, canonical sales key, lot/unit/Store integrity, movement
types/signs/lot consistency and controlled constraint scope/type/version/period.
Tests include NULL STORE uniqueness, inactive activation, exact Decimal/boundaries,
schema-only limitations and fresh/downgrade/re-upgrade. No ledger balance service,
import correction or FEFO coverage is claimed. See
[S13_VERIFICATION](runbooks/S13_VERIFICATION.md) and the four domain feature docs.
Current Windows verification: S1.3 80 targeted, S1.3.1 9 targeted, S1.4 58 targeted / 240 full tests pass; one existing upstream
warning. Full suite requires healthy local PostgreSQL, with no integration skips.

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

## S1.3.1 verification -- CURRENT FACT

```powershell
.\.venv\Scripts\python.exe -m pytest tests/integration/test_data_semantics_correction.py -q
.\scripts\test.ps1 all
```

POSIX equivalent: `.venv/bin/python -m pytest tests/integration/test_data_semantics_correction.py -q`.
Nine regressions cover ORM/raw SQL unknown receipt without defaults, strict supplier
inputs, exact per-pack price and clean/refused downgrade behavior. All use isolated
shelfcash_test, fresh sessions and actual PostgreSQL. No importer/readiness test oracle
is fabricated. See [S131_VERIFICATION](runbooks/S131_VERIFICATION.md). PowerShell
runtime verified; unchanged POSIX wrappers retain historical syntax-only status.

## S1.4 run persistence -- CURRENT FACT

```powershell
.\.venv\Scripts\python.exe -m pytest tests/integration/test_forecast_decision_persistence.py -q
.\scripts\test.ps1 all
```

POSIX: `.venv/bin/python -m pytest tests/integration/test_forecast_decision_persistence.py -q`.
58 tests verify actual isolated PostgreSQL run states/windows, model metadata, exact
ordered finite quantiles, same-store references, canonical keys, nested JSON independent
values, reruns, completed minimum fields, partial/failed outputs and fresh/down/up
migration. No engine or SQL immutability enforcement is claimed. Out-of-horizon
prediction test explicitly demonstrates the future application invariant. Full suite:
240 tests; see S14_VERIFICATION and FORECAST/DECISION_RUN docs. PowerShell runtime
verified; POSIX wrappers unchanged with historical syntax-only status, no runtime claim.

## S1.5 persistence access -- CURRENT FACT

```powershell
.\.venv\Scripts\python.exe -m pytest tests/integration/test_repositories.py tests/unit/test_repository_contract.py tests/unit/test_repository_guards.py -q
.\scripts\test.ps1 all
```

Real isolated PostgreSQL round trips for all sixteen tables through concrete
repositories; Store scope/identity-map isolation, exact Decimal/NULL/JSON, date
queries, duplicate/new-row guards, caller commit visibility/rollback and lot row
locks. Inventory fixture transactions are not an implemented mutation service.
See [PERSISTENCE_ACCESS](features/PERSISTENCE_ACCESS.md) and CURRENT_STATE for
acceptance evidence; unchanged schema/API and direct ORM/SQL limitations explicit.
RUNNING-only lifecycle guards, prediction append, terminal rejections before caller
flush, copied JSON inputs, Store boundaries, transaction rollback, row locks and
stale cached run refresh are exercised on real PostgreSQL. Full package/horizon/
authorization and operational inventory mutation remain future application checks.

S1.5 Windows acceptance: targeted command above **80 passed**; supported
`test.ps1 all` **320 passed** (29 unit, 289 integration, 2 API), one existing upstream warning, no skips. This includes
65 repository integration tests and 15 repository unit checks. Earlier 240-test totals
above describe HISTORICAL INFORMATION at the S1.4 baseline. Pre-S1.5 protected-file
hashes and exact generated/live OpenAPI comparison pass. Authorized development
reset/upgrade and Alembic check pass; final status is at unchanged 0006 head with
sixteen empty business tables. Tests only own shelfcash_test.

## S1.6 application contracts and persistence orchestration -- CURRENT FACT

```powershell
.\.venv\Scripts\python.exe -m pytest tests/unit/test_application_contracts.py tests/integration/test_application_paths.py -q
.\scripts\test.ps1 all
```

Contract/unit tests check Pydantic v2 fields, extra rejection, exact finite Decimal,
ordered windows/quantiles, aware time, minimal typed object JSON, positive version,
allowed recommendation and HTTP/query independence. Application integration tests
exercise Product/Sales/Forecast/Decision/dated Recipe paths on actual shelfcash_test,
two Stores, canonical conflicts, lifecycle/horizon/completed source, typed copied
outputs, stale cached status refresh, caller transaction preservation and read-only
no-commit/no-autoflush behavior. Forecast/Decision downstream failure after real flush
rolls back all output; close/fresh-session reads independently assert persisted state.
Existing repository tests continue to own S1.5 guards/locks/no-auto-commit behavior.
API tests remain health/OpenAPI only; there are no public business API tests.

Manual verification and expected rows: [S16_VERIFICATION](runbooks/S16_VERIFICATION.md).
Full contract/limitations: [APPLICATION_CONTRACTS](features/APPLICATION_CONTRACTS.md).
Fixtures are supplied persistence examples, not Forecast/Decision Engine output.
Latest execution totals are in CURRENT_STATE; older totals above are historical.

S1.6 Windows acceptance: **82 targeted passed** (38 unit, 44 application integration),
**402 full passed** (67 unit, 333 integration, 2 API), no skips; one existing upstream
Starlette/AnyIO warning. Alembic/pip checks, protected hashes, generated/live OpenAPI
and live health pass. No native POSIX execution claim.

## S1.7 operational application and inventory closure -- CURRENT FACT

```powershell
.\.venv\Scripts\python.exe -m pytest tests/unit/test_operational_contracts.py tests/integration/test_operational_paths.py tests/unit/test_application_contracts.py tests/integration/test_application_paths.py -q
# Only after targeted green, run full regression once at the final gate.
.\scripts\test.ps1 all
```

New tests cover Store/Ingredient/SupplierTerm/Recipe and inventory receipt/correction
contracts, exact Decimal arithmetic despite ambient precision, domain import
independence, required facts and distinct DATE/aware UTC instants. Real isolated
PostgreSQL tests assert close/fresh-session state, Store/unit integrity, active
overlap/canonical conflicts without overwrite, atomic header+lines/lot+movement,
negative-result protection and rollback after actual SQL flush. Every new writer
is tested for commit-failure rollback and preservation of caller transactions;
reads leave pending work unflushed. Stale cached balance refresh and real competing
lot locks prove no lost update. Full S1 chain uses application paths; only Supplier
identity is an explicit repository prerequisite. Existing S1.6 tests stay unchanged.

See [S17_VERIFICATION](runbooks/S17_VERIFICATION.md) for individual reviewable flows,
expected rows, reset/migration/status and health/OpenAPI checks. Final counts and
full regression run count are recorded in CURRENT_STATE. Prior totals/absence
claims in earlier slice sections are HISTORICAL INFORMATION where superseded.
No business API/e2e, FEFO, Forecast/Decision computation or auth evidence is claimed.

S1.7 Windows acceptance: **106 new targeted passed** (52 unit, 54 PostgreSQL
integration); final combined S1.6/S1.7 targeted **188 passed** (90 unit, 98 integration).
Supported full regression **508 passed** (119 unit, 387 integration, 2 API), no skips,
one existing upstream warning; **one full regression run**, after targeted green.
PostgreSQL, reset/upgrade/status, Alembic/pip checks, protected WIP hashes and exact
generated/live OpenAPI/health pass. No native POSIX runtime claim.
