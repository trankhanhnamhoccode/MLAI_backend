# Remaining work and acceptance gates

## CURRENT FACT

| Scope | State | Boundary |
| --- | --- | --- |
| S0/S1 | Implemented | PostgreSQL/local tooling, operational models/repositories and typed internal application paths |
| S2 | Implemented mechanics | Baseline/trained quantiles, retained inputs/evaluation/artifacts/replay; real-data quality NOT EVALUATED |
| S3.1-S3.6.4 | Implemented internal paths | Validated decision/BOM/serving/FEFO, procurement/1 and /2, comparison/selector, operational capture/setup and durable PlanningRun |
| S4.1-S4.10 | Implemented backend scope | Auth/Staff, public Menu/Inventory, Import/commit, calendar/config/readiness, public Planning, retained history/PDF |
| S4.11 | PARTIAL | Local integration/API coverage exists; whole mapping browser continuation NOT_RUN; PDF/planning-history UI incomplete |

These are functional checkpoints, not a claim each is a Git commit or every route
passed a fresh full suite. Current runtime/debt is in [CURRENT_STATE](CURRENT_STATE.md).
Acceptance uses [FULL_TEST_FLOW](runbooks/FULL_TEST_FLOW.md) and relevant tests.

## CURRENT FACT - authorized repair scope

The ADR-013 authority clarification, recipe adapter test doubles, Money boundary
expectations, current API inventories and four application query boundaries have
been repaired without changing product/API behavior. Related tests remain active,
including both capture versions. Verification results are reported in the
conversation; S4.11 UI acceptance and remaining product proposals are unchanged.

## ACCEPTED DECISION — phạm vi tiếp theo được người dùng duyệt

Chốt/push v1.0 trước rồi tách nhánh import: audit sáu workbook chỉ đọc, cải tiến
deterministic mapping proposals và approved Store/source/report/version profile
reuse, phát hiện drift, giữ Owner approval và atomic commit. Provider thật cần
duyệt model/dữ liệu/giới hạn calls/chi phí riêng trước khi gửi dữ liệu. Không sửa
FE, triển khai ngoài import hoặc deploy trong phạm vi này.

CURRENT FACT: v1.0 đã push; nhánh import riêng đã có header/preamble discovery,
controlled aliases/candidates/reasons, full-spec Owner review và scoped drift notice.
Reuse không học từ proposal chưa duyệt. Numeric Excel dates, version `v1.2`, MOQ/
pricing basis và per-serving recipe semantics vẫn cần dữ liệu/quyết định rõ ràng;
consumption, purchase history, calendar/weather và tabular business rules chưa có
writer import. Đưa các workflow này vào import là slice riêng, chưa được thực hiện.

## PROPOSAL / ngoài phạm vi đã duyệt

- Dashboard D01/prototype screens and draft PO remain proposals unless separately
  approved; the retired v0 prototype contract is not implementation authority.

- Finish whole-chain browser acceptance against real BE: mapping/Owner approval,
  preview/confirm/commit, readiness, Planning and retained/history/PDF UI; distinguish
  unsupported UI from API defects and assert fresh-session persistence.
- Assess forecast quality using suitable observed sales/correction provenance;
  do not activate trained artifacts merely because training code exists.
- Owner lifecycle/reactivation, one-time approval allowlist/TTL and sensitive audit
  retention need separate reviewed scope. Stored membership alone is not authority.
- AI wording/copilot, deterministic hypothetical what-if, customer selection and
  draft/actual purchase orders are not silently enabled by current Planning/PDF.
- Stock/correction/purchase history extensions, unsupported supplier conditions,
  safety-stock semantics and latency improvements require explicit slices.

## Acceptance policy ? ACCEPTED DECISION

Select tests for changed behavior and affected callers. Full pytest is for important
integration milestones or broad shared-contract/schema/transaction/infrastructure
changes when targeted coverage is insufficient; state why it is needed. Pure doc
changes use link/content checks, not full pytest. Never treat historical PASS logs
or HTTP2xx as fresh regression/persistence proof. A fresh Session must verify commits.
Public API changes require explicit contract approval and OpenAPI diff.

Update this document when scope/status changes; keep execution logs in the
conversation. No automatic next product slice follows cleanup.
