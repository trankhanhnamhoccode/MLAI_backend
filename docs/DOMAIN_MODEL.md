# Domain model and business meaning

CURRENT FACT assistant L2: summary is retained presentation of PlanningRun evidence,
not a new Decision, purchase order or inventory fact. Six material claim families
are server-rendered with exact retained values/provenance; optional model chooses
bounded presentation only. Failed/unknown/no-winner/partial and proof scope remain
distinct. Generation state is separate from PlanningRun status; provider failure
can yield a deterministic completed summary without changing Run outcome. Workflow:
[Planning §18](PROCUREMENT_API_CONTRACT_VI.md#decision-assistant).

CURRENT FACT L3: a chat message is a scoped explanation of the same retained Run,
not a new decision or conversation authority. History can identify an Ingredient
from a prior user message for an explicit follow-up, never supply stock/cost/winner
facts. Ambiguous/conflicting entities clarify; unsupported operations do not run.
Message receipts preserve request/context/version and final answer. Optional chat
model writes prose from backend-selected sealed facts; complete clauses, roles,
values/units/entity/path, polarity and main-answer coverage validate before final
publication. L3.1 structured context is only an identity hint. Independent optional
assertions may be trimmed; one exact uniquely bound numeric slot may be repaired
and fully rechecked. Material/missing-main failures regenerate once or fall back.
No nearest-number repair, scope/unit conversion or new business calculation. Model prose is presentation, not domain truth.
Summary provider enablement does not enable conversational generation. What-if
questions disclose that no new simulation exists and direct creation of a new Run;
chat never creates that Run or mutates inputs implicitly.

CURRENT FACT self-service Store: authenticated active verified credential-ready
holder tự tạo Store với name/timezone/currency explicit và trở thành Owner đúng
Store mới. Signup/verify không tự tạo Store; Store không đồng nghĩa business READY.
Không menu/stock/completeness/budget/requirements default. Account có nhiều Stores;
membership/current grants vẫn authorization boundary, biết UUID không cấp quyền.
Workflow/accepted rules ở [Authorization](AUTHORIZATION_CONTRACT_VI.md#self-service-stores).

## CURRENT FACT — C3 actual receipts

Actual receipt là hàng thật đã nhận: một nguồn/record ổn định tạo một lot và
RECEIPT dương. Excel và N6 dùng cùng canonical receipt identity/normalized digest
và InventoryReceipts application writer. Cùng payload replay; khác payload conflict,
không upsert/delete theo file mới. Opening stock là balance đầu kỳ; count là target
observation của lot existing; purchase history chỉ lịch sử; Planning purchases là
đề xuất hypothetical. Receipt không tự chứng minh completeness và không sửa Run cũ.
Facts/date/supplier/cost unknown giữ null; zero cost là known value. Workflow do
[Import §16](IMPORT_MAPPING_API_CONTRACT_VI.md#excel-actual-receipt) sở hữu.

## CURRENT FACT — notification event foundation C1

`NotificationEvent` là immutable plain Python v1, event/decision/object/recipient
references và occurred_at; fixed server templates không nhận business facts từ
client/LLM. Inbox là projection lịch sử và read state riêng, không task/decision
authority. N13 PermissionEvent, PR submission/outcomes và MQ submission/N5 outcomes
là producers thật. PermissionRequest giữ requested facts, approval additions và
decision; current grants luôn live, approve union không replace quyền khác.
MappingSubmission là retained full-spec task, có own revision riêng batch/profile;
content/source/lifecycle drift làm review stale, không tự resubmit hay commit.
Recipient/object visibility luôn theo current authorization, không theo event
snapshot. [Notification contract](NOTIFICATION_API_CONTRACT_VI.md) sở hữu vocabulary,
DTO/visibility/retention; [database schema](DATABASE_SCHEMA.md) sở hữu persistence.

## ACCEPTED DECISION / CURRENT FACT — A2 recorded support history

CalendarEvent is a Store-scoped declared inclusive event, distinct from observed
Product/day promotion. UsageHistory records actual Ingredient consumption; it is
not theoretical BOM, waste/loss or a stock transaction. PurchaseHistory records
historical quantity/price basis with separate order, receipt and report dates; it
is not received stock, committed inbound or current supplier terms. Exact reviewed
physical conversion applies to quantity and price denominator without rounding.
Stable source/report/record identity has immutable domain grain and append-only
confirmed correction revisions; absent records remain. History-only readers are
retained Import preview/completion and H01/H02 discovery, not forecast features.
See [Import](IMPORT_MAPPING_API_CONTRACT_VI.md) and
[Authorization](AUTHORIZATION_CONTRACT_VI.md) for accepted workflow/current rights.

## ACCEPTED DECISION ? identity, units and time

A User may belong to several Stores; Owner/Staff authority is scoped to current
active membership and granular grants. Operator support is an audited identity,
not another Store role. Stored membership alone never authorizes data exposure.
[Authorization](AUTHORIZATION_CONTRACT_VI.md) owns permissions/consent/approval.
CURRENT FACT B1: signup creates an unverified credential-unset account, without
Store/membership/grants. Mailbox proof and holder password become usable atomically
at verification; a verified email does not constitute invitation acceptance.
CURRENT FACT B2: active verified holders can request account-scoped RESET without
changing password or sessions. N7 consumes it, advances credential revision and
revokes every account session atomically; Store membership/grants stay unchanged.
CURRENT FACT B3: a verified active invitation holder may decline a valid pending
offer without membership. Declined is terminal for that identity, consumes mutation
capability and retains an atomic event/receipt; it gives no Store access or grants.
A new invitation identity can subsequently be created and accepted independently.

Products/Ingredients/Suppliers belong to a Store. Names are not unique; nullable
SKUs are case-sensitive Store-scoped keys. Product.selling_unit is the sales/
forecast/recipe output unit; Ingredient.base_unit must match RecipeLine,
InventoryLot and SupplierTerm units exactly. There is no canonical unit conversion
engine. Import can apply explicitly declared Owner-reviewed conversion rules with
provenance; it cannot reinterpret existing canonical facts.

Business DATEs use Store timezone; event instants are aware UTC. Unknown received
or observed dates stay unknown, not upload date. Money inherits Store.currency;
no currency conversion or implicit rounding. Unknown, zero, empty and forbidden
are different states (ADR-010). Exact public decimal/rational types are defined
by [API](API_CONTRACT.md) and source DTOs.

## CURRENT FACT ? operational truth

Recipes have whole-yield quantities, process loss, dated lines and inclusive
nonoverlapping assigned applicability. BOM uses theoretical ingredient demand /
(1-loss); missing/empty recipes block or exclude according to captured scope.
Future-only recipe calendar changes have explicit preview/CAS/commit/audit, never
implicit period closure/reopening or historical content editing.

SalesDaily stores canonical Store/Product/day totals. Import source-contribution
revisions distinguish duplicate, replacement and confirmed independent-source
merge; changing file hash is not permission to add quantities. Approved mapping
is distinct from preview/commit confirmation. Canonical commit is atomic for all
requested groups; missing rights/blockers never silently drop rows.

CURRENT FACT A1 adds nullable observed product stockout, separately from inventory or
projected shortage. Contribution revisions retain observation evidence; quantity-only
preserves the contribution observation. Captured derived demand never overwrites
SalesDaily.quantity. [ADR-A1](adr/ADR-A1-observed-stockout-demand-policy.md) owns
schema-2 mechanics and legacy replay. Migration and targeted persistence/consumer
acceptance are verified on the owned Import test DB; real-data quality is not evaluated.

InventoryLot holds current physical balance; InventoryMovement holds justified
history. Receipt/count correction update movement+balance atomically under locks;
negative balance rejects. OPENING_STOCK observation is not an incoming purchase.
Count affects identified lots, not unexplained absolute overwrites or invented
receipts. Expired/unknown-date lots remain physical facts; eligibility is separate.
Inventory completeness requires explicit coverage/dependency evidence, not one receipt.

Supplier terms retain dated versions, exact pack size/unit/cost, whole-pack MOQ,
lead/shelf-life and scoped identity. Payable fees/capacity/supplier limits and
budget need explicit captured evidence; unknown is not zero/unlimited/unconfigured.

## CURRENT FACT / ACCEPTED DECISION ? forecast and decisions

Forecast captures explicit Products and sparse observed sales using Store-local D
and D+1..D+7 (ADR-012/014/015). Missing observations are not zero. P25/P50/P75 are
finite ordered nonnegative demand quantiles in each Product selling unit. Baseline
and trained LightGBM mechanics/evaluation/artifact replay exist; real-data quality
is NOT EVALUATED. Actual selected model and fallback reason remain retained.

LEAN/BALANCED/PROTECTED construct LOW/BASE/HIGH demand paths, not quantile aliases
or stochastic scenarios. Plain exact progressive serving/FEFO respects recipe/
expiry/arrival dates and shared physical stock. Native MILP generates candidate
pack baskets; exact domain simulation/validation owns hard validity.

Procurement/2 constructs100% per Product and applies explicit effective customer
requirements. Within customer-valid domain, construction pass minimizes purchase
plus declared fees; fallback uses minimum then mean Product service, outlay and
canonical ties. Mixed selling units are never summed as a service objective.
Winner requires exact validity, no related blocker and customer pass; no eligible
candidate gives null. Search incomplete/unproven, technical failure and exact
infeasibility proof are distinct (ADR-019/020). No universal BASE95 engine default.

Planning configuration/default/saved/budget/serving versions are frozen at acceptance;
operational values are captured before compute. PlanningRun is separate from the
original S1 DecisionRun schema. Retained result uses captured context, not current
stock/recipe/prices. Reads/export of an option do not persist customer selection.
Required nullable result_digest applies only to terminal captured scope without a
retained result; engine fields remain unavailable/null, not zero.

## ACCEPTED DECISION ? retention and limits

Completed Runs/snapshots/packages retain actual values and versions; rerun creates
new identity. Fingerprints are nonunique diagnostics, not deduplication/security.
Package version starts1. Model binaries/text are immutable local artifacts; metadata
is in PostgreSQL. Operational audit, source provenance, Runs/PDF and models are not
disposable development evidence (ADR-005/008/009/011/015/022).

What-if remains hypothetical/nonpersistent by default. No automatic purchasing,
customer selected-option write, one-time approval or AI business decision is enabled.
DB local constraints and application invariants have different coverage; privileged
SQL and tracked ORM can bypass some guards. Historical /1 remains readable and is
not reinterpreted as procurement/2. See [schema](DATABASE_SCHEMA.md),
[Planning](PROCUREMENT_API_CONTRACT_VI.md), [Import](IMPORT_MAPPING_API_CONTRACT_VI.md)
and [accepted ADR index](DECISIONS.md).
