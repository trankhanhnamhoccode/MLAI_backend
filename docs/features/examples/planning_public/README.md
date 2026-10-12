# Public planning JSON examples

CURRENT FACT: request examples validate against PlanningRequest. Response examples
are actual guarded shelfcash_test HTTP responses validated against
PlanningEnvelope[Accepted] or PlanningEnvelope[RunView]. They use synthetic
observations and explicit BASELINE; no browser or forecast-accuracy claim.

The response files come from separate isolated test cases. UUIDs, opaque versions,
timestamps and default-1 are illustrative test identities. Use current Store,
saved requirement, default version and a fresh canonical UUID Idempotency-Key
for real requests. Never reuse these UUIDs as operator or authorization evidence.

`c02_default_request.json`, `c02_custom_request.json` and
`c02_saved_request.json` illustrate all three modes. The accepted, queued,
running, failed and completed response files show the same public DTO shapes.
The failed example uses a labeled deadline clock injection after actual engine
execution; it does not demonstrate hard cancellation. The completed example has
actual observed zero demand; positive-demand purchase/budget outcomes are covered
by the integration tests and documented in S49 task notes.

See [feature](../../PUBLIC_PLANNING.md) and
[local worker runbook](../../../runbooks/FULL_TEST_FLOW.md) for the supported
flow, headers, serving setup and interpretation of status/outcome/proof/winner.
