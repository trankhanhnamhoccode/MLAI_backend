# Current clarification11/10 — CA-002/016/020

CURRENT FACT A2: four typed recorded domains use append-only
import_history_records revisions. Preview/commit/fresh read, explicit correction
confirmation, current domain grants and price-read denial preserve the existing
atomic boundary. I06 retains history_record + canonical_version; H01/H02 expose
category calendar/usage/purchase (promotion=sales) with current scoped read rights.
These are history consumers only; no stock/receipt/inbound/term/forecast mutation.
Calendar declaration and promotion observation are separate schemas. Unsupported
MIN_SAFETY_STOCK now blocks R01 in computed scope as well as execution.
The [Import contract](../IMPORT_MAPPING_API_CONTRACT_VI.md) owns A2 semantics and
the [field inventory](IMPORT_SCHEMA_INVENTORY.md) owns dictionaries/consumer limits.

CURRENT FACT A1 (targeted persistence acceptance on owned Import test DB): frozen sales plans retain
typed contributions and aggregate one effect per Product/day. Commit replaces each
previous contribution and retains stockout update/provenance revisions. Correction/
merge rights, read-set fence, transaction and retry receipts remain in force.
Changed contribution facts require correction rights/resolution even when the
canonical aggregate is unchanged. Fresh-session stockout/quantity rollback and
two-worker competing corrections are verified; the losing preview fails stale.
[Import contract](../IMPORT_MAPPING_API_CONTRACT_VI.md) owns identity/declarations;
no new endpoint. Historical slice boundaries below remain historical evidence.

I05 commit reason conditional theo effective actions, không bắt cho pure insert/NO_OP.
Correction/merge/count/amend cần nonblank, thiếu422 COMMIT_REASON_REQUIRED. Confirmation
reason/source/action evidence vẫn riêng. Money input18/18/keys1000 đã đồng bộ;
legacy output/evidence và re-review errors xem [compatibility](../CONTRACT_COMPATIBILITY_CHANGELOG_VI.md).
Staff IGNORE own uncommitted sheet không N5 riêng, không sửa profile/quota, invalidate
preview/confirmation. Supplier nine-schema consumers hiện hành xem S4.6 feature.

# S4.5 — Commit Import canonical, atomic

CURRENT FACT — consumer update S4.6: all nine existing schemas have atomic writers; N6/N8 stock workflows are separate. See [S4.6 feature](IMPORT_INVENTORY_SUPPLIER.md) and [evidence](../runbooks/FULL_TEST_FLOW.md). Four-schema/unsupported statements below describe the S4.5/S4.4 historical slice boundary.

HISTORICAL INFORMATION — original S4.5 scope10/10/2026. Authority: [Import contract](../IMPORT_MAPPING_API_CONTRACT_VI.md),
[authorization](../AUTHORIZATION_CONTRACT_VI.md), [roadmap](../ROADMAP.md).
[Task notes/evidence](../runbooks/FULL_TEST_FLOW.md) ghi commands thực chạy, fail→fix
và giới hạn; feature này không chứng nhận full regression hoặc production acceptance.

## Capability thực sự đã triển khai

| Schema | Retained preview S4.4 | Canonical commit S4.5 | Giới hạn |
| --- | --- | --- | --- |
| products | Có | Có | Tạo reserved ID đã Owner duyệt; existing exact metadata là NO_OP, conflict không overwrite. |
| ingredients | Có | Có | Tạo reserved ID, explicit metadata/unit; không tạo lô/tồn kho. |
| sales | Có | Có | Daily total hoặc declared disjoint contribution; explicit correction/merge, versioned source provenance. |
| recipes | Có | Có | Tạo phiên bản không overlap; exact units/yield/loss; không đóng/mở timeline của S4.7. |
| inventory_count | Có | Chưa — S4.6 | Không cập nhật on_hand/movement. |
| suppliers, supplier_terms, payable_fees, scope_declarations | Có | Chưa — S4.6 | Không ghi điều kiện/phí/declarations. |

Opening stock/actual goods receipts thuộc S4.6, purchase-history OPEN. Một preview
chứa schema chưa hỗ trợ khiến **toàn commit** bị chặn SCHEMA_BLOCKED, kể cả nhóm
đó NO_OP; không bỏ dòng/nhóm để báo thành công. Explicit IGNORE đã review vẫn
là việc chọn scope ở mapping, không tự bỏ nhóm tại commit. Không gọi engine,
forecast/planning hoặc thay Run đã lưu. Không thay limits/quota/sealing S4.4.

## FE walkthrough và surface

1. I01 draft → nhiều I02 uploads; render per-file receipts rồi refresh I04/quota.
2. I03 analyze202 seal source set ngay acceptance; J01 đọc job, M01–M04 mapping.
   Unique approved Store profile reuse không gọi provider; ngoại lệ được resolve
   rõ ràng và N5 Owner duyệt immutable profile nếu cần.
3. I05 `phase=preview`202 tạo retained preview từ bindings/values hiện hành.
   J01 → I04 `include_preview=true`: kiểm toàn summary, blockers/warnings, before/
   after, provenance, required_actions. Rows có pagination nhưng commit toàn preview.
4. I05 `phase=confirm_review`200 với preview ID/digest, mapping_revision,
   confirm=true, reason, current If-Match và UUID Idempotency-Key. Đây chỉ staging
   confirmation riêng cho import, **chưa canonical writes**. Reuse profile không
   miễn confirmation import mới. Lưu revision/ETag mới từ response.
5. I05 `phase=commit`202, current If-Match + UUID Idempotency-Key + session/Origin/
   CSRF. Empty resolutions=[] rõ ràng nếu không có correction/merge. Nếu có,
   gửi đúng unresolved rows/actions/report key, evidence/reason; không gửi số lượng
   thay thế tùy ý. Supplier changes chưa được writer S4.5 hỗ trợ.
6. Poll J01/I04. Queued/running chưa thành công business. Job completed có result
   resource_type=import_completion, resource_id=import_id, commit_id. I06 GET
   `/api/v1/imports/{import_id}/completion` đọc retained outcome/impact/audit/provenance.
   I06 trước completion trả409 IMPORT_NOT_COMPLETED; GET không chạy việc còn thiếu.

I05 cùng route `/api/v1/imports/{import_id}/process`, không thêm route commit.
I06 là route đã có trong authoritative design. I04 `completion_available` true khi
completion đã durable. `allowed_actions` có commit chỉ khi đủ current rights,
supported preview, confirmation và dependencies usable; terminal/active job không
cho commit/preview thêm. `preview.summary.can_commit` là projection theo actor/
state, không approval hay guarantee facts không đổi; retained preview digest không
được viết lại khi projection đổi. Correction resolutions vẫn phải cung cấp khi commit.
ConfirmationResult.canonical_commit_supported phản ánh schema support của preview,
không bảo đảm request tiếp theo sẽ được accept.

## Transaction, dependencies và provenance

Acceptance khóa batch, recheck exact source/file-set versions, mapping revision,
approved pins/content, retained preview/read-set, per-import confirmation và mọi
required read/write action; không tự preview/confirm/approve để bypass. Worker
recheck dưới current user/session/membership/Store authorization fence trước ghi.
Permission thiếu kể cả NO_OP domain phải deny toàn batch.

Transaction worker ghi canonical + immutable IMPORT_CANONICAL_COMMITTED audit +
retained completion + terminal job/import cùng một commit. Writers catalog/sales/
recipe có transaction-owned seams tái sử dụng validation hiện hành, không commit
riêng mỗi row. Thứ tự ingredients → products → recipes → sales dựa dependencies,
không sheet upload order. Reservations phải Owner approved và đúng Store; không
fuzzy name identity. Unit conversion chỉ dùng explicit approved rule.

Read-set gồm dependency values/xmin và nguồn sales đã committed; recheck ở acceptance
và execution. Fixed canonical tables khóa `SHARE ROW EXCLUSIVE` theo thứ tự tên
để fence write/phantom với cả internal writers S1 chưa có Store lock. Đây là khóa
DB thật, bảo vệ correctness nhưng có thể serialize writes giữa nhiều Store; ngắn,
chỉ ở transaction commit. Không tuyên bố có fine-grained concurrency throughput.

Retained canonical references có canonical_domain/id, source_location(s), provenance
field→origin/value_source/column index/declaration ID/rule IDs. Recipe có
line_provenance theo từng Ingredient và dòng nguồn, không gán nguồn dòng đầu cho
mọi line. Shared PROFILE_CONSTANT/IMPORT_VALUE giữ declaration/rule identity;
Owner metadata của reservation dùng IDENTITY_BINDING + entity_proposal ID.
Sales normalized_source_quantity giữ lượng incoming; after.quantity là canonical
total dự kiến, phép cộng/delta được đánh dấu DETERMINISTIC_DERIVED. Các giá trị 0,
false, explicit null không bị coerce thành missing/default. Commit không parse,
normalize/remap hay gọi provider lại.

## Source sales và duplicate/correction

Identity là Store/source_system_key/business_report_key/Product/ngày; không filename,
blob checksum hoặc similarity. Nguồn provenance/version nằm trong immutable commit
audits của migration0013, không thêm migration/table hoặc overwrite audit cũ.

- Daily total100 →105: CHANGED/REPLACE_DAILY_TOTAL, sales.correct và explicit
  replace_daily_total resolution; không tự cộng205.
- Existing100 + nguồn độc lập105: MERGE_DISJOINT_SALES với sales.merge, người có
  quyền xác nhận disjoint_assertion=true và evidence/reason →205. Khi baseline
  chưa có source provenance, cảnh báo giữ nguyên; audit pin baseline canonical
  ID/xmin/quantity100 và assertion của người xác nhận. Đây là human declaration,
  không backend/LLM chứng minh hai tập sales độc lập.
- Reimport cùng source105 khi canonical205: NO_OP, không cộng thêm105.
- Correction source105→110: lượng aggregate205→210, sales.correct + explicit
  replacement, source_revision mới; baseline/contribution khác giữ nguyên.
- Mixed semantics, overlap chưa chứng minh, canonical total thay ngoài source ledger
  hoặc source identity mâu thuẫn: block SALES_OVERLAP_UNRESOLVED; không suy trừ/
  tự overwrite/cộng. Reimport changed daily total chỉ có thể thay theo source contract.

Arithmetic exact Fraction/Decimal text, không float hay rounding context28. Audit
read-set giới hạn10.000 canonical success audit records (mọi schema) và100.000 source revision entries:
RESOURCE_LIMIT_EXCEEDED khi quá bound, không truncate để classify sai. Đây là giới
hạn implementation read-set, không thay20 files/20 MiB/100 MiB upload policy.

## Counts, completion và readiness

CompletionSummary.files = accepted logical uploaded records; sheets = non-ignored
analysis sheets; rows = raw source rows của những sheet này, không bao gồm synthetic
catalog creation reservations và không gộp recipe lines. mapped_fields = non-ignored
column mapping issues có target_field, không cộng shared declarations; errors=0 chỉ successful
atomic completion; warnings = retained preview notices. Classification counts toàn
preview. inserted_record_count/changed_record_count/no_op_count là logical canonical
actions; một Recipe header+lines tính một record, không tổng raw SQL rows hoặc
Store totals. Sales counts là daily records; menu affected_product_count distinct
Products được tạo/có Recipe mới. Ingredient creation không inventory.updated.
All NO_OP: outcome=no_changes và updated=false, completion/audit vẫn durable.

data_date là metadata batch người dùng khai báo; readiness.as_of_date là ngày Store
tại completion, không lấy max sales date/data_date làm watermark. data_version pin
snapshot committed. Readiness hiện chỉ authorized intersection import/menu/inventory,
omitted_actions báo NOT_AUTHORIZED, không leak domain chưa được đọc. Evaluator R01/
Planning execution chưa có: mọi action trả unknown, can_execute=false,
result_assessment=NOT_ASSESSED và EXECUTION_UNAVAILABLE; không fabrication blocker
chi tiết/ready. Đây là retained point-in-time result, không evaluate lại khi GET.
H01/H02 và R01 chưa triển khai trong S4.5; không suy đã có từ I06.

## Retry, failure và vận hành local

Same UUID key+same body replay retained202/job ID, vẫn auth hiện hành; không tạo job/
rows/audit thành công mới. Same key khác body409 IDEMPOTENCY_KEY_CONFLICT.
Concurrent commit same import chỉ một acceptance hợp lệ; other stale CAS412 hoặc
active-job409. Success retry không reinterpret retired mapping/current DB; I06 vẫn
current rights và full sensitive read scope. N5 reapproval profile cho future không
reset terminal import/rewrite completion; retired pin block commit chưa thành công.

Failure rollback toàn canonical set, giữ preview/confirmation/evidence và J01.error
actionable. Không tự retry writes trong GET. Worker process proof recovery chỉ
recover process đã chết, không steal live worker. Failed job retry explicit new key,
current If-Match, exact same usable preview/confirmation; same old key trả failed job
receipt lịch sử. Stale dependencies cần preview/review lại trước intent mới.
Uncertain DB acknowledgment được fresh-session reconcile durable job/completion
digest, không đánh dấu failed hoặc ghi lặp sau actual successful COMMIT.

IMPORT_WORKER_ENABLED vẫn mặc định false. Local deployment muốn HTTP lifespan worker
phải opt in IMPORT_WORKER_ENABLED=true trong cấu hình riêng và khởi động theo runbook
backend; bounded single-process worker/recovery hiện hành xử lý analyze/preview/commit.
Không tự start worker từ GET. `scripts/run_import_jobs.py` giữ test-only guard;
không dùng script này như production/development worker bypass. Live worker/provider/
production multi-process/load/backup chưa được chứng nhận bởi targeted tests.

## Errors/action cho FE

| Outcome | HTTP / code | FE action |
| --- | --- | --- |
| Commit accepted | 202 committing | Poll J01, refresh I04; không báo data đã ghi. |
| Missing confirmation/blockers | 409 PREVIEW_BLOCKED | Show retained evidence, resolve rồi preview/review. |
| Read-set/shared/mapping changed | 409 PREVIEW_STALE | Refresh, tạo preview mới và confirm riêng. |
| Retired pin | 409 MAPPING_VERSION_RETIRED | Owner review valid profile rồi preview/confirm. |
| Unsupported canonical schema | 409 SCHEMA_BLOCKED | Báo capability chưa có; không silently drop. |
| Resolution shape/scope invalid | 422 INVALID_IMPORT_CONFIGURATION | Gửi đúng rows và actions đã preview. |
| Source semantics/overlap invalid | 409 SALES_OVERLAP_UNRESOLVED | Show reason/evidence, không tự merge. |
| Stale ETag | 412 | Refresh current revision trước explicit intent mới. |
| Revoked/foreign Store | 403 PERMISSION_DENIED / 404 | Không render sensitive retained result. |
| Job execution failed | GET J01 200, status=failed | Render error.code/details, không coi200 là business success. |

JSON examples đúng current DTO ở cuối tài liệu; các UUID/digests/revisions chỉ minh
họa syntax, không real token hoặc evidence integrity. Feature+OpenAPI+task notes là
runtime evidence; policy người dùng nằm trong authoritative Import/Auth contracts.

## Examples kiểm bằng current DTO (minh họa, không dữ liệu thật)

### I05 request phase=commit

```json
{
  "phase": "commit",
  "preview_id": "00000000-0000-4000-8000-000000000040",
  "preview_digest": "sha256:0000000000000000000000000000000000000000000000000000000000000000",
  "confirm": true,
  "reason": "Đã đối chiếu báo cáo sales hôm qua.",
  "resolutions": [],
  "supplier_changes": []
}
```

### I05 HTTP202 data

```json
{
  "import_id": "00000000-0000-4000-8000-000000000001",
  "status": "committing",
  "phase": "commit",
  "job_id": "00000000-0000-4000-8000-000000000060",
  "job_status": "queued",
  "commit_id": "00000000-0000-4000-8000-000000000070",
  "preview_id": "00000000-0000-4000-8000-000000000040",
  "effective_plan_digest": "sha256:0000000000000000000000000000000000000000000000000000000000000000",
  "import_revision": "import-example-after-acceptance"
}
```

### I06 HTTP200 data

```json
{
  "import_id": "00000000-0000-4000-8000-000000000001",
  "status": "completed",
  "data_date": "2026-10-09",
  "outcome": "committed",
  "mode": "atomic",
  "completed_at": "2026-10-10T02:00:00Z",
  "commit_id": "00000000-0000-4000-8000-000000000070",
  "preview_id": "00000000-0000-4000-8000-000000000040",
  "effective_plan_digest": "sha256:0000000000000000000000000000000000000000000000000000000000000000",
  "mapping_bindings": [
    {
      "sheet_id": "00000000-0000-4000-8000-000000000020",
      "profile_id": "00000000-0000-4000-8000-000000000030",
      "version": "example-profile-version",
      "content_digest": "sha256:0000000000000000000000000000000000000000000000000000000000000000"
    }
  ],
  "summary": {
    "files": 1,
    "sheets": 1,
    "rows": 1,
    "mapped_fields": 3,
    "errors": 0,
    "warnings": 0,
    "counts": {
      "NEW": 1,
      "UNCHANGED": 0,
      "CHANGED": 0,
      "INVALID": 0,
      "CONFLICT": 0
    },
    "inserted_record_count": 1,
    "changed_record_count": 0,
    "no_op_count": 0
  },
  "updated_resources": {
    "inventory": {
      "updated": false,
      "affected_ingredient_count": null,
      "changed_record_count": null
    },
    "menu": {
      "updated": false,
      "affected_product_count": null,
      "changed_record_count": null
    },
    "sales": {
      "updated": true,
      "added_record_count": 1,
      "changed_record_count": 0
    },
    "catalog": {
      "created_product_count": 0,
      "created_ingredient_count": 0
    }
  },
  "readiness": {
    "evaluated_at": "2026-10-10T02:00:00Z",
    "as_of_date": "2026-10-10",
    "data_version": "sha256:0000000000000000000000000000000000000000000000000000000000000000",
    "actions": [
      {
        "action": "import",
        "availability": "unknown",
        "can_execute": false,
        "data_status": "unknown",
        "execution_status": "unknown",
        "blockers": [],
        "warnings": [
          {
            "code": "EXECUTION_UNAVAILABLE",
            "source": "runtime",
            "scope": "STORE",
            "entity_id": null,
            "affected_dates": [],
            "details": {}
          }
        ],
        "result_assessment": "NOT_ASSESSED"
      }
    ],
    "evaluated_actions": [
      "import"
    ],
    "omitted_actions": [
      {
        "action": "menu",
        "reason": "NOT_AUTHORIZED"
      },
      {
        "action": "inventory",
        "reason": "NOT_AUTHORIZED"
      }
    ]
  },
  "audit_reference": "00000000-0000-4000-8000-000000000080",
  "canonical_references": [
    {
      "row_id": "00000000-0000-4000-8000-000000000050",
      "canonical_domain": "sales",
      "canonical_id": "00000000-0000-4000-8000-000000000090",
      "source_location": {
        "file_id": "00000000-0000-4000-8000-000000000010",
        "sheet_id": "00000000-0000-4000-8000-000000000020",
        "row_number": 2,
        "source_column_index": null,
        "record_number": null,
        "line_start": null,
        "line_end": null
      },
      "source_locations": [],
      "line_provenance": [],
      "provenance": {
        "quantity": {
          "origin": "SOURCE_EXPLICIT",
          "applied_rule_ids": [],
          "value_source": "SOURCE_COLUMN",
          "source_column_index": 2,
          "declaration_id": null
        }
      }
    }
  ]
}
```

Các object response trên là `data`; envelope hiện hành `{data,meta,error:null}`, J01 GET status completed có result `{resource_type:"import_completion",resource_id:import_id,commit_id}`. Không copy revision/digest mẫu để gọi API thật.
