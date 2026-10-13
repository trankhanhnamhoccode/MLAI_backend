# Remaining work and acceptance gates

## CURRENT FACT

| Scope | State | Boundary |
| --- | --- | --- |
| S0/S1 | Implemented | PostgreSQL/local tooling, operational models/repositories and typed internal application paths |
| S2 | Implemented mechanics | Baseline/trained quantiles, retained inputs/evaluation/artifacts/replay; real-data quality NOT EVALUATED |
| S3.1-S3.6.4 | Implemented internal paths | Validated decision/BOM/serving/FEFO, procurement/1 and /2, comparison/selector, operational capture/setup and durable PlanningRun |
| S4.1-S4.10 | Implemented backend scope | Auth/Staff, public Menu/Inventory, Import/commit, calendar/config/readiness, public Planning, retained history/PDF |
| S4.11 | PARTIAL | Local integration/API coverage exists; whole mapping browser continuation NOT_RUN; PDF/planning-history UI incomplete |
| A1 Sales/reimport + stockout | COMPLETE | Migration0019 and targeted PostgreSQL acceptance on owned shelfcash_import_test; fresh-session sales/stockout, causal capture/trained/replay, retained Planning, rights/isolation/rollback/concurrency; real-data quality not evaluated |
| A2 support history + constraints | COMPLETE backend scope | Four history-only schemas, append revisions/current domain grants and retained reads; 24 targeted DB acceptance cases plus affected regressions; R01 scoped unsupported safety-stock blocker; no full-suite/whole-FE or forecast-feature claim |
| A3 Import → readiness → Planning | COMPLETE backend acceptance | Fresh provisioned Store/public imports and config/real workers/fresh reads; both upload orders and exact purchase/service/stock oracle; Staff invitation/source reuse/Owner spec change, conflict/ambiguity, scoped unsupported safety and lost ACK/retry; 11 unique targeted DB cases plus inherited A1/A2 evidence; no browser/full-suite/real-accuracy claim |

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
Reuse không học từ proposal chưa duyệt. Slice analyze → rules/LLM proposal → Owner
review → reuse đã có bounded candidates/reasons/diagnostics, late-result revision
fence và offline HTTP/DB acceptance. Numeric Excel dates hỗ trợ explicit
EXCEL_SERIAL + workbook epoch + Owner review; không tự chọn date semantics.
Live gateway probe POS demo đã nhận proposal hợp lệ cho SLX và giữ unsupported
columns null; không mở rộng workbook khác hay activate/commit. Whole browser flow
và broader model quality chưa kiểm chứng; live calls theo approved scope. Version
`v1.2` chưa release; Supplier source price/MOQ basis đã có explicit quantity/unit
declarations và exact normalization; recipe source basis đã có explicit
PER_SERVING/WHOLE_BATCH và Owner-reviewed scalar resolution → exact normalization
→ preview/atomic commit → fresh recipe/BOM/recipe readiness. Không defaults/loss kép,
old profiles thiếu basis cần review; output conversion chưa hỗ trợ. FE chưa có
acceptance cho selector/provenance mới;
CURRENT FACT A2: usage/purchase history, declared calendar và observed promotion có
record-only import writer/readback. Calendar/weather forecast features, waste/BOM
reconciliation và arbitrary tabular rules chưa hỗ trợ, không suy từ history presence.

ACCEPTED DECISION: ưu tiên nghiệp vụ cốt lõi theo chuỗi schema → mapping/resolution
→ validation → persistence → consumer → readiness, không theo số cột của sáu workbook.
Giữ Owner approval/profile reuse/exact semantics; không port defaults, permissive
conversions hoặc constraints chỉ lưu nhưng chưa enforce. Chín writer schemas hiện có
được dùng làm nền; thiếu một alias không được xem là thiếu cả persistence/consumer.
CURRENT FACT: Recipe serving/batch và SupplierTerm price/MOQ units đã implement
trong các slices được người dùng duyệt. Supplier source/canonical contracts tách
riêng; whole-pack price/MOQ normalization, Owner/profile review, preview/atomic
commit và immutable evidence nối writer/capture/procurement/readiness hiện có.
Acceptance gồm fresh-session persistence, exact MOQ/budget oracle và retained Run;
không đồng nghĩa toàn browser flow hoặc full regression. Các nghiệp vụ ngoài phạm
vi vẫn cần authorization riêng. Xem
[field inventory/gaps](features/IMPORT_SCHEMA_INVENTORY.md).

CURRENT FACT: lát setup identity/opening/count/completeness đã nối public intake
đến custom Planning trên Store mới không seed business facts. Source opening_stock
dùng writer/receipt identity N6, whole-batch dependencies và typed declaration
bindings; count/stock CAS, quyền và atomic rollback giữ nguyên. R01/capture operational/2
cùng kiểm một current completeness scope, nhận explicit zero trên retained lots.
Source declaration M04 đi trước compatible reuse; signature không chứng minh nguồn.
Recipe cross-sheet cùng version bị RECIPE_SOURCE_SCOPE_AMBIGUOUS; split-part grain
chưa supported. Retirement giữ chặn cả fresh reuse và pending commit.
Default configuration absence vẫn UNKNOWN; whole browser acceptance chưa chạy.
Excel actual receipts vẫn ngoài phạm vi lát setup identity.

ACCEPTED DECISION: người dùng đã mở A1 sales/reimport và stockout riêng;
[ADR-A1](adr/ADR-A1-observed-stockout-demand-policy.md) sở hữu capture/consumer policy.
A2 được duyệt riêng: recorded calendar/promotion/usage/purchase và constraints đã
contract/enforce; không Excel actual receipts, Auth workflow hoặc queue/notification.

CURRENT FACT A3: backend acceptance of the implemented chain is complete on the owned
Import DB, provider OFF. Coverage extends existing tests only at the missing oracle,
retained correction/count/config, Staff public-grants/reuse and scope/retry boundaries.
No runtime/schema/API/permission change or migration was needed. A1/A2 targeted
evidence is reused explicitly rather than repeating broad groups. See current
[workflow/expected outcomes/recovery](runbooks/FULL_TEST_FLOW.md). No next feature
slice, FE work, commit/push/merge/deploy or ZIP is authorized by this milestone.

## PROPOSAL / ngoài phạm vi đã duyệt

- [TD-BE review](../008_TechDebt.md) là review/acceptance dependency, không ủy quyền
  implement/deploy endpoint PROPOSED. Ưu tiên Product freeze queue semantics TD004
  trước Staff→Owner→Staff; kế tiếp supplier/location TD007 và settings TD010,
  preview/PDF discovery/Today TD006/008/009. Budget absence/create hiện có C01/N4,
  Ingredient discovery có V01; FE cần current environment/rights/persistence evidence.
  Product chốt assisted/public provisioning và decline TD001/002; AI/What-if/PO
  TD011–013 phải chốt scope/design trước API. Owner cá nhân và ngày môi trường mới
  chưa được xác nhận; không mục nào đủ điều kiện đề nghị đóng từ review tài liệu.

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

CURRENT FACT: isolated worktree test DB setup is supported; effective target, dedicated
roles and reset commands are documented in [FULL_TEST_FLOW](runbooks/FULL_TEST_FLOW.md).
Parallel tests require different owned DBs; each DB remains sequential.

## Acceptance policy ? ACCEPTED DECISION

Select tests for changed behavior and affected callers. Full pytest is for important
integration milestones or broad shared-contract/schema/transaction/infrastructure
changes when targeted coverage is insufficient; state why it is needed. Pure doc
changes use link/content checks, not full pytest. Never treat historical PASS logs
or HTTP2xx as fresh regression/persistence proof. A fresh Session must verify commits.
Public API changes require explicit contract approval and OpenAPI diff.

Update this document when scope/status changes; keep execution logs in the
conversation. No automatic next product slice follows cleanup.
