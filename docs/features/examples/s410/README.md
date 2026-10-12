# CURRENT FACT — S4.10 synthetic HTTP examples

These JSON responses were produced by real guarded PostgreSQL/HTTP tests and
validated against their actual Pydantic boundary DTOs by
`runtime/s410/check_openapi.py`. UUIDs/names belong to synthetic local fixtures.
Examples do not include private sessions/credentials or fabricate canonical data.

C04/C05/C08 share one actual completed Run/result. N9 and H01/H02 demonstrate
their own real history fixtures. N10/J01 use the final Vietnamese PDF sample.
`c04_null_digest_response.json` and `c05_null_digest_response.json` show the
accepted terminal-after-capture/no-result case: required result_digest is null,
captured stock remains, and engine-dependent values stay null/unavailable.

All N10 request keys are required; this selects the retained winner:

```json
{"format":"pdf","option_id":null,"locale":"vi"}
```

The binary example and visual evidence remain private runtime artifacts, linked
from the [runbook](../../../runbooks/FULL_TEST_FLOW.md). No handoff or
ZIP has been created; final FE synchronization remains a later roadmap task.
