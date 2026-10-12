# Verification policy and coverage

ACCEPTED DECISION: choose tests for changed behavior and affected callers. After
small fixes rerun affected/failed tests, not full pytest without new evidence.
Full suite is for integration milestones or broad shared-contract/schema/
transaction/infrastructure changes when targeted coverage is insufficient.
Document-only changes need link/consistency checks. State commands/results/limits
and the reason for broadening; historical PASS is not a fresh result.

[FULL_TEST_FLOW](runbooks/FULL_TEST_FLOW.md) owns runnable setup/DB guards/API/
manual/browser/restart commands. Integration fixtures run sequentially and own
only local shelfcash_test, never development/S4.11 demo data. Assert committed
state through a new Session; HTTP2xx is insufficient. API changes require explicit
approval, source DTO/OpenAPI tests and before/after diff.

| Boundary | Relevant coverage |
| --- | --- |
| Layer/import safety | Architecture assertions in unit tests |
| Identity/catalog/schema/migrations | test_identity_store_schema.py, test_catalog_recipe_schema.py, test_database_bootstrap.py |
| Repositories/application | test_repositories.py, test_application_paths.py, test_operational_paths.py; atomicity/scoped fresh reads |
| Forecast | Unit contracts/baseline/features/metrics; integration execution/trained/serving/artifact replay |
| BOM/serving/procurement | test_bom.py, test_serving.py, test_serving_output_validation.py, test_procurement*.py |
| Capture/setup/selector | test_decision_operational_v2.py, test_planning_setup.py, test_planning_small_domain.py; independent stock/purchase/infeasible oracle |
| Auth/Staff | test_auth_public.py, test_staff_public.py, OpenAPI/security tests and test_integration_tooling.py guards |
| Import | Parser/descriptors/preview/classification/value unit tests; staging/batch/commit/inventory/supplier/readiness integration tests |
| Public/retained Planning | test_planning_public*.py, test_planning_inspection.py, retained-history/current-rights tests |
| PDF | test_planning_exports.py, test_planning_export_durability.py, test_planning_export_schema.py; bytes/fonts/current rights/fresh state |
| Tooling/baseline | test_integration_contract_snapshot.py, test_integration_tooling.py; original hash and real deltas |

ACCEPTED DECISION: exhaustive route inventories retain independent expected
paths/methods and security assertions; never derive expected paths from the app
under test. Correct stale expectations without dropping business assertions.
Paid provider/real-data forecast quality remain outside this repair.
S4.11 API/native and browser acceptance are distinct; whole mapping and incomplete
PDF/history UI prevent whole-UI PASS.

CURRENT FACT: pytest uses importlib collection so unit and integration modules
with the same basename (including test_planning_run.py) keep separate identities.
Both suites remain collected; no tests are excluded to avoid naming collisions.

CURRENT FACT: the authorized repair's local full-regression run bounds native
math threads with `OMP_NUM_THREADS=1`, `OPENBLAS_NUM_THREADS=1`,
`MKL_NUM_THREADS=1` and `NUMEXPR_NUM_THREADS=1` in the verification process
environment. Earlier full runs exposed child-process queue timeouts on a
memory-constrained Windows host; thread limits alone did not resolve them.
These verification settings do not alter app/demo
configuration, test assertions, process timeouts or business recovery rules.
Results and the limit of this environment diagnosis are reported in the conversation.

CURRENT FACT: real Planning/PDF spawn targets live in `tests/planning_process_cases.py`.
Windows child bootstrap imports that fixture-free module instead of importing
the test modules and their app-composition/fixture dependencies. Child service
calls, local test DB guards, cleanup and the original 20-second waits remain.

Routine output goes to ignored runtime/verification or private integration runtime.
Tests/fixtures/independent oracle specifications remain; old logs/PASS reports and
packaging-only tests are not required verification assets.

HISTORICAL INFORMATION, cleanup checkpoint 2026-10-12: the expanded unit/API plus public-planning/export selection
returned 1039 passed / 15 failed / 2 skipped. Observed failures included the
application query guard, obsolete repository mock signatures, fee precision
expectation and two exhaustive route inventories. See CURRENT_STATE; cleanup
did not edit these business tests or establish pre-cleanup reproduction. The
authorized repair updates affected tests while preserving their invariants;
current verification results are reported in the conversation.
