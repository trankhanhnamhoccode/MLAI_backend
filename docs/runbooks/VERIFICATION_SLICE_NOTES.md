# Local verification tooling slice

Classification: HISTORICAL INFORMATION. These notes describe the earlier local
verification tooling slice under the then-accepted persistence decision; S0.2
supersedes its persistence assumptions. See S02_TASK_NOTES for active scope.

- Authorized scope: repository test/reset/seed/status commands and reproducible S0
  verification documentation. No S1 business implementation is authorized.
- Frozen contract: `/health` and OpenAPI remain unchanged; SQLite synchronous
  persistence and empty `0001_scaffold` remain unchanged (ADRs 001, 002, 003).
  PostgreSQL examples in the verification request are adapted to accepted SQLite.
- Observed WIP: the entire initial scaffold appears as pending additions. Preserve these
  files and their content except scoped test organization/documentation updates;
  do not commit, unstage, or reset unrelated work.
- Acceptance: stable unit/integration/api/e2e/all test selectors; nonzero errors;
  reset only in development and only the canonical runtime database, with optional
  seed; inspect persisted revision/integrity through a fresh read-only connection;
  test rejected reset targets without losing data; repeat reset/seed deterministically.
- BE impact: developer commands only. FE and ML/Data: none. Demo: repeatable empty
  baseline, explicitly no business seed/scenarios. No provider/notebook dependency.
- Rollback scope: added scripts/docs/tests and moved existing test files only.
  Reset is destructive to the development database; stop the backend and preserve
  a backup if needed before running it. Uploads/model artifacts are never reset.
- Verification: targeted tooling tests, all existing regressions, commands exercised
  against the canonical local database, and a live health/OpenAPI check. No API or
  business schema change; accepted ADRs remain unchanged.
