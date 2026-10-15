# Data readiness — facts, eligibility, fallback và cảnh báo

## Authority, phạm vi và trạng thái

ACCEPTED DECISION — yêu cầu D1 ngày 15/10/2026: ShelfCash hoạt động theo facts và
semantics cần cho từng action/scope, không yêu cầu đủ bộ sáu files. Một file có thể
chứa nhiều domains; nhiều files có thể bổ sung cùng domain. Thiếu dữ liệu không liên
quan consumer hiện tại không chặn và không phát warning. Thiếu làm giảm chất lượng
cho phép phương pháp eligible với warning; thiếu làm phép tính/ràng buộc không xác
định phải block đúng action/scope hoặc yêu cầu xác nhận có provenance.

HISTORICAL INFORMATION — D1 là audit source/design tại checkpoint local
`c930dfe66cfda5de5896164e16fcf8f4c7acaefe`, không đổi runtime/API. D2/D3 đã
checkpoint trong nhánh D, D4 COMPLETE checkpoint local. CURRENT FACT — D1–D5
đã tích hợp main local giữ ancestry; chưa push/deploy, runtime8103 không nâng cấp.
Main được audit tại
`052cddee075e165af2c0cea42ebc2e616c396760`. Worktree D1 `backend-data-readiness`,
branch `feat/data-readiness`, xuất phát đúng main này. D2 checkpoint local
`9f720caf01fdf0a8f586c049660a2fcc9447ade3`; D3 checkpoint local
`d0f3716c261f6634d5fcd5ae886c00cf3014276c`; D4 checkpoint local
`72415332e2a5224ab9909d54606d7e7e374bdd18`; D5 backend acceptance VERIFIED, committed
`11ef320a5873fc4dc314fdad63878db5f8a8b38c`, đã tích hợp main local.
Không nhập E1–E4.
Đối chiếu read-only challenger tại `c2544c1025815bd0ccef9acb524f6f265dd03c45`
cộng E4/dataset-admission WIP; các findings này không phải khả năng của main.
Ma trận/source trace D1 dưới đây là kiểm tra tĩnh; kết quả implementation/verification
D2 được phân biệt ở mục D2 và conversation. Không phần nào chứng minh process
HTTPS8103 đang chạy source nhánh D.

Tài liệu này sở hữu policy liên consumer và backlog D1–D5. Workflow/permissions vẫn
thuộc [Import](../IMPORT_MAPPING_API_CONTRACT_VI.md),
[Planning](../PROCUREMENT_API_CONTRACT_VI.md),
[Authorization](../AUTHORIZATION_CONTRACT_VI.md) và
[API conventions](../API_CONTRACT.md). Request/response structure thuộc source DTO
và OpenAPI. Các extension ghi PROPOSAL chưa thay thế contract hiện hành.

ACCEPTED DECISION — áp dụng ADR-010/012/014/015/A1, ADR-019/020/021/022 và tính
immutable của ADR-011; xem [index](../DECISIONS.md). Không sửa ADR đã accepted.
P25/P50/P75 là demand quantiles; LOW/BASE/HIGH là design paths;
LEAN/BALANCED/PROTECTED là strategies. Readiness không chứng minh accuracy,
calibration, confidence percentage, winner, savings hoặc infeasibility.

## CURRENT FACT — bản đồ source/consumer và coverage hiện có

Các đường dẫn trong bảng là main trừ nhãn **challenger-only**. Test được đọc để
xác định acceptance hiện có; D1 không chạy business tests.

| Ref | Source và consumer | Acceptance source hiện có |
| --- | --- | --- |
| F1 | [forecast_preparation](../../app/application/forecast_preparation.py), [validation](../../app/domain/forecasting/validation.py), [baseline](../../app/domain/forecasting/baseline.py), [baseline boundary](../../app/application/use_cases/forecast_baseline.py) | [baseline cases](../../tests/unit/test_forecast_baseline.py), [execution](../../tests/unit/test_forecast_execution.py) |
| F2 | [stockout](../../app/domain/forecasting/stockout.py), [demand projection/warnings](../../app/application/forecast_demand.py), [trained choice/replay](../../app/application/use_cases/forecast_trained_execution.py), [model boundary](../../app/infrastructure/forecast_model.py) | [stockout readiness](../../tests/unit/test_stockout_readiness.py), [trained execution](../../tests/integration/test_forecast_trained_execution.py), [A1 persistence](../../tests/integration/test_forecast_stockout_a1.py) |
| F3 | [serving choice/identity/reuse](../../app/application/use_cases/forecast_serving.py), [artifact verification](../../app/infrastructure/storage/forecast_artifacts.py), [operator config](../../app/application/use_cases/model_serving.py) | [serving/reuse/fallback](../../tests/integration/test_forecast_serving.py), [artifact corruption](../../tests/unit/test_forecast_artifacts.py) |
| R1 | [R01 evaluation](../../app/application/readiness_evaluation.py), [read orchestration](../../app/application/use_cases/readiness.py), [C01 projection](../../app/application/planning_context_projection.py), [typed issues](../../app/application/contracts/readiness.py) | [R01/C01](../../tests/integration/test_readiness_context.py), [Import snapshot](../../tests/integration/test_import_readiness_snapshot.py) |
| P1 | [operational/2 projection](../../app/application/decision_capture_v2_validation.py), [Planning capture/declarations/bounds](../../app/infrastructure/database/planning_capture.py), [BOM boundary](../../app/application/use_cases/bom.py), [dated BOM](../../app/domain/demand/bom.py) | [BOM cases](../../tests/unit/test_bom.py), [operational/2](../../tests/integration/test_decision_operational_v2.py), [public sources](../../tests/integration/test_planning_public_sources.py) |
| P2 | [setup resolution](../../app/application/use_cases/planning_setup.py), [C02 acceptance](../../app/application/use_cases/planning_public.py), [retained projection](../../app/application/planning_public_projection.py), [procurement/2 input](../../app/application/contracts/procurement_v2.py), [exact result validation](../../app/application/procurement_v2_validation.py) | [config resolution](../../tests/integration/test_planning_configuration_resolution.py), [procurement/2](../../tests/unit/test_procurement_v2.py) |
| I1 | [preview](../../app/application/import_preview.py), [configuration preview](../../app/application/import_configuration_preview.py), [commit/completion](../../app/application/use_cases/import_staging.py), [Notice/completion DTOs](../../app/application/contracts/import_mapping.py), [declaration dependencies](../../app/application/operational_import_facts.py) | [preview](../../tests/unit/test_import_preview.py), [completeness](../../tests/unit/test_import_inventory_completeness.py) |

CURRENT FACT — main có sparse-history baseline, trained eligibility/fallback,
tri-state stockout, dated Product exclusions, explicit inventory/fee/procurement
declarations và retained warnings. Không tìm thấy global guard yêu cầu đủ sáu
files trong các entrypoints đã trace. Đây không phải kết luận mọi data path đã
được kiểm chứng runtime hoặc mọi fallback đã public/configurable.

## Ma trận canonical — minimum facts theo action và scope

Mọi code không có nhãn PROPOSED là code đang có tại consumer được chỉ ra; tên code
có thể khác qua adapter. `B` = blocker, `W` = warning, `I` = irrelevant/no issue.
Ma trận này ghi baseline main/D1; implementation D2/D3 và proposals còn lại được
phân biệt trong các mục cùng tên bên dưới.
Invalid/conflicting không được xem như merely missing để fallback bỏ qua.

| Fact/field; source → consumer | Action / scope; khi thực sự bắt buộc | Classification khi thiếu; fallback/declaration hiện có | Code, hệ quả, bổ sung và delta |
| --- | --- | --- | --- |
| Store timezone; Product ID/selling_unit; sales date/quantity/unit → F1 | Import/forecast; Store/Product/day, quantity hữu hạn không âm, date ≤ D, đúng identity/unit | B nếu không xác định; explicit quantity 0 hợp lệ; không đoán unit/date/ID | `INVALID_CANONICAL_CAPTURE` chỉ challenger; main semantic validation/Import field issues. Resolve source identity, reviewed conversion, timezone; không copy upload date. Main đã strict, giữ nguyên. |
| Observed history → F1/F2/R1 | Forecast, từng requested Product đến D | ≥1 usable sample baseline; no history B Product, không demand0; sparse day không zero-fill | `PRODUCT_HISTORY_MISSING`, `NO_COMPUTABLE_PRODUCTS`; internal `BASELINE_NOT_READY`. Bổ sung sales hoặc scope rõ; R01 có exclusion, internal explicit scope all-or-error. Không silently omit requested Product. |
| Coverage/completeness watermark → R1/I1 | Forecast quality; exact Product/date declaration, không phải file count | W nếu watermark không có/current proof stale; baseline vẫn có thể eligible | `HISTORY_NOT_AVAILABLE_THROUGH_CUTOFF`; declaration `SALES_COVERAGE` và dependency digest; latest sales date không chứng minh complete. Giữ absence, không zero-fill. |
| is_stockout true/false/null; earlier support → F2 | Forecast/BOM demand; Product/day | Unknown W dùng observed compatibility; true có đủ ≥3 strictly earlier known-false trong42 ngày thì reconstruct; thiếu support exclude censored sample; all unusable B | `STOCKOUT_UNKNOWN`, `DEMAND_RECONSTRUCTED`, `CENSORED_HISTORY_EXCLUDED`, `CENSORED_HISTORY_NOT_USABLE`. Giữ observed quantity/tri-state/method/support; không set unknown=false. |
| Trained usable observations/labels → F2/F3 | Main trained inference/training; exact requested model scope | ≥28 observations/Product, training ≥14 supervised rows/Product; baseline ≥1. Model ineligible có recognized whole-scope fallback | `BASELINE_FALLBACK`, selection reason `NOT_READY_HISTORY`; history không đủ model không tự block baseline. Actual model/candidate/reason được retain; không gọi main trained model là challenger C. |
| Candidate artifact/selection → F2/F3 | New trained execution; Store/Product/unit/policy/window/dependencies | No candidate/recognized missing artifact/baseline-selected evaluation có thể fallback nếu baseline ready | `BASELINE_FALLBACK`; reasons `NO_ARTIFACT`, `ARTIFACT_MISSING`, `BASELINE_SELECTED`. Supported operator hiện chỉ `BASELINE`/`DEFAULT_BASE95`; typed TRAINED không chứng minh có public activation. |
| Artifact bytes/hash/manifest/compatibility → F3 | Execution/replay; artifact/Run | B integrity nếu corrupt/incompatible; không fallback. Replay missing artifact cũng error | R01 `MODEL_ARTIFACT_INVALID`; retained loader có typed errors. Khôi phục đúng immutable bytes/dependency hoặc tạo new execution bằng explicit compatible policy; không latest/retrain đổi identity. |
| Serving configuration/composition → F3/R1 | Forecast/planning; Store/version/runtime | Unknown config không tự chọn model; unavailable runtime là execution issue riêng data | `MODEL_CONFIGURATION_UNKNOWN`, `EXECUTION_UNAVAILABLE`. Có operator CAS/version/evidence workflow; PROPOSAL D2/D4 làm eligibility rõ, không thêm implicit config. |
| Calendar/closures/weather/promotion/usage/purchase → F1/F2 | Main baseline/trained model chỉ bắt buộc features nó thực dùng | I cho absent support files: model main không consume chúng; A2 calendar/promotion/usage/purchase là history-only | Không thêm warning vì vắng file. Trained weekday/month tính từ date khác sourced opening calendar. History present không tự tăng forecast quality; A2 import riêng vẫn validate schema được chọn. |
| Sourced dense calendar + known-at; fit/point/CQR windows → challenger | **challenger-only** forecast/evaluation; Store/day/pinned arm | B của challenger/protocol, không B của baseline main. Weather disabled trong arm đang audit | `CALENDAR_COVERAGE`, `CALENDAR_NOT_AVAILABLE`, benchmark `SOURCED_CALENDAR_NOT_AVAILABLE`; bổ sung calendar/provenance hoặc chạy method khác ngoài protocol cũ theo protocol mới. Không default mọi ngày mở. |
| Recipe identity/effective dates/lines/units/yield/loss/source basis → I1/P1/R1 | Import/BOM/planning; Product × từng ngày D+1..D+7 | B hoặc known Product exclusion; forecast Product vẫn giữ. Unknown graph attribution B global. Standalone BOM giữ all-or-error | R01 `RECIPE_PERIOD_GAP`, `RECIPE_OVERLAP`, `RECIPE_EMPTY`, `UNIT_MISMATCH`; capture `MISSING_RECIPE` → public `RECIPE_MISSING`; `SOURCE_FAILURE_SCOPE_UNKNOWN`. Cung cấp recipe/source PER_SERVING/WHOLE_BATCH/positive yield và exact unit conversion; loss áp một lần. |
| Inventory quantity/unit/lot coverage/as-of → I1/P1/R1 | Planning; Ingredient và mọi dependent Product | Unknown stock khác confirmed empty; thiếu unique current dependency-bound declaration exclude dependent Products; warehouse vẫn đọc được | `INVENTORY_SCOPE_UNKNOWN` / capture `INVENTORY_BALANCE_MISSING` → public `INVENTORY_UNKNOWN`; inventory read W `STOCK_COMPLETENESS_UNKNOWN`. Dùng `COMPLETE_CURRENT_LOTS` hoặc `CONFIRMED_EMPTY`, không coi no rows là empty. |
| Expiry/received_date/unit_cost → P1 | FEFO positive expiry-tracked lot; inventory age/cost consumer riêng | Missing required expiry B dependent Product; receipt date/cost nullable W hiện hành; không invent expiry hoặc receipt date | `REQUIRED_EXPIRY_MISSING`; capture `MISSING_RECEIVED_DATE`/`MISSING_COST` → public `RECEIPT_DATE_UNKNOWN`/`INVENTORY_COST_UNKNOWN`. Bổ sung fact có proof. PROPOSAL lọc warning theo consumer khi không mất capability; D1 không đổi current warnings. |
| Supplier identity/term price/pack quantity/base unit/MOQ/lead/effective dates/shelf-life theo applicability → I1/P1 | Import term promotion và procurement; offer/Ingredient/order date/arrival | Canonical term strict; source unresolved không promote. Không term không đồng nghĩa proof không supplier; alternative offers chỉ khi eligible | R01 W `SUPPLIER_TERM_MISSING`; capture `SUPPLIER_TERM_FACT_UNAVAILABLE` B dependent Product. Resolve price denominator/basis, currency, pack, ceil physical MOQ, delivery/expiry facts. PROPOSAL D3 giữ omitted-offer evidence và xét alternatives sound. |
| Finite offer maximum; cost/budget/source maximum/supplier limit → P1 | Procurement finite search; offer/Run | Positive price derive floor(effective budget/cost), intersect known limits. Zero-cost không tự derive finite bound; hiện thiếu bound B Store/Run | `OFFER_BOUND_UNKNOWN`; `BoundEvidence` giữ derivation/proof scope. Bổ sung explicit finite limit; PROPOSAL D3 xét loại offer thiếu facts khi vẫn sound, không biến giới hạn kỹ thuật thành market infeasibility. |
| Payable fees/mode/currency/coverage/effectivity/bindings → I1/P1/R1 | Planning claim budget/min-outlay; scope toàn basket/horizon | Unknown fee B; explicit complete `NONE` known0; PER_OFFER/PER_SUPPLIER_ORDER cần đủ covered keys/components | `PAYABLE_FEE_COVERAGE_UNKNOWN`, `PAYABLE_FEE_DECLARATION_CONFLICT`, `UNSUPPORTED_FEE_RULE`; public `PAYABLE_FEE_UNKNOWN`. Dùng fee workflow hiện có, không fee=0 từ no file. Không đổi generic payable fees thành delivery phí. |
| Budget ceiling/effective limit/requirements → P2/R1 | Planning; Store + Run + Product/path | Known cap required, zero hợp lệ; null request budget inherit cap; default chỉ cần khi chọn/inherit default; saved/full custom resolve độc lập default | `BUDGET_CEILING_UNKNOWN`, `BUDGET_LIMIT_EXCEEDS_CEILING`; version/CAS checks. R01 hiện unknown default kể cả khi full custom/saved có thể resolve: delta D4 contextual readiness. Không đề xuất unlimited khi cap unknown. |
| Capacity/supplier limits/inbound/additional orders → P1/R1 | Planning applicable Ingredient/supplier/date/Run | `UNKNOWN` B; explicit not-configured khác unlimited ngầm; present unsupported inbound không được bỏ qua | `LIMIT_CONFIGURATION_UNKNOWN`, `COMMITTED_INBOUND_UNKNOWN`, `COMMITTED_INBOUND_UNSUPPORTED`; capture checks current declarations/effective horizon. Bổ sung typed scoped procurement declaration và provenance; không đổi history purchase thành inbound. |
| Configured mandatory MIN_SAFETY_STOCK → R1/procurement | Applicable computed Ingredient/horizon, kể cả numeric value0 | B unsupported semantics; không warning rồi claim passed; unrelated/future constraint không block forecast | `MIN_SAFETY_STOCK_UNSUPPORTED`; cần slice riêng chốt/enforce semantics hoặc authorized explicit configuration change. D1 không remove/soften guard. |
| Product retail price/profit → P2 | Không cần cho current min purchase+payable fee outlay | I cho objective này; không tự tạo profit/savings | Không blocker/warning chỉ vì missing retail price. Forecast reuse source digest không phụ thuộc retail/recipe/stock/budget. Không mở objective mới. |
| Source declaration/approved mapping/conversion/immutable version/current actor authority → I1 | Import theo selected schema/scope; approved interpretation khác batch facts | B khi ambiguous/conflict/unsupported/current authority thiếu; proof hợp lệ được reuse, không Owner reapprove mỗi file | `RECIPE_SOURCE_SCOPE_AMBIGUOUS`, `RECIPE_BASIS_REVIEW_REQUIRED`, schema-specific Notice. M04 source → compatible profile → row validation → preview/confirm → commit; không bypass atomic batch guards. |
| Historical actuals/known-at/holdout/use authority → evaluation | Benchmark metrics; Product/day/task/origin | Missing targets không zero; unsupported/censored/unknown masks tách primary known-false. Không labels/holdout thì quality not evaluated | Main evaluation đủ origins/paired validation mới chọn trained; challenger E3 `REAL_BENCHMARK_BLOCKED` là research status. Bổ sung authorized unseen dataset/vintages; không ép product intake theo research gate. |

## HISTORICAL INFORMATION — D1 findings và technical debt tại baseline

1. **Đã có fallback**: `_choose` kiểm baseline readiness, chỉ catch
   `ArtifactMissingError`, verify compatibility trước history/selection fallback;
   metadata lưu actual model/candidate/selection/warnings. `ForecastServing.choice`
   còn kiểm training rows. Replay chọn đúng retained artifact/input, không chọn lại.
   Test serving/trained/artifact ở F2/F3 xác định các cases này.
2. **Đã có partial scope**: R01 tách base forecast scope khỏi recipe/inventory;
   operational/2 giữ active menu, exclusions, dates, raw source, overrides
   `NOT_EVALUATED`. Unknown attribution block global. BOM thuần không partial success.
   Không đổi missing recipe thành mất forecast hoặc denominator toàn menu thành
   computed scope mà không nêu coverage.
3. **Block quá rộng theo action/mode**: `evaluate` luôn thêm
   `DEFAULT_CONFIGURATION_UNAVAILABLE` cho planning nếu không default, trong khi
   `resolve_planning_setup` cho full custom/saved không kế thừa default. C01 có
   `custom.available` đồng thời `can_generate=false` do default unknown. Đây là
   scope limitation của readiness, không chứng minh C02 bị chặn bởi cùng guard.
   R01 chưa nhận selected custom/saved intent nên không thể chứng nhận request đó.
4. **Offer thiếu fact kéo scope lớn hơn offer tại main/D1–D2**: `declarations_for` cũ thêm
   `OFFER_BOUND_UNKNOWN` dạng Store blocker và bỏ offer; `project_capture_v2` biến
   `SUPPLIER_TERM_FACT_UNAVAILABLE` thành dependent Product exclusion. Do đó một
   alternative đủ facts không tự giải được blocker này. D3 thêm admission versioned
   cho new Runs như mục dưới, giữ old-policy Runs và nguyên tắc missing offer không
   phải no-supplier proof. Contextual R01/C01 refinement vẫn thuộc D4.
5. **Thông tin fallback chưa đi hết public R01/C01**: tại main/D1, `assess` trả
   `None` khi choice fallback hợp lệ. D2 internal assessment đã có method/reason/
   warnings, nhưng public projection giữ nguyên; C01 chỉ
   project blocker reason codes và không project action warnings. Execution/retained
   forecast và Planning forecast view đã có warnings. D4 cần additive projection,
   không kết luận warnings chỉ tồn tại trong logging.
6. **Error distinction tại main/D1, đã sửa trong D2**: `assess` cũ gộp `ArtifactError`/`ModelBoundaryError`
   thành `MODEL_ARTIFACT_INVALID`, có thể gồm dependency incompatibility. Với
   schema-2 all-censored Product và serving mode TRAINED, `_choose` có thể raise
   `BaselineNotReadyError` trước `evaluate`; caller cũ không chuyển readiness exception
   thành assessment. Linked regression D2 xác nhận handler chung trả503
   SERVICE_UNAVAILABLE ở cả R01/C01. D2 trả scoped blockers, không che programming
   errors; unit evaluator trước đây không bao phủ integration path này.
7. **Drift được báo, không sửa approved intent**: Planning prose §4 nhắc sales
   availability đến D được xác nhận; source R01 dùng thiếu watermark làm warning,
   baseline vẫn eligible. Các ADR có đoạn implementation boundary lịch sử nói
   chưa có HTTP/config/capture trong khi main đã wired. D1 không dùng các đoạn đó
   thay source, không đổi prose/ADR để che drift. D4 phải reconcile rõ scope public.

## CURRENT FACT — D2 forecast eligibility và linked readiness

D2 bổ sung [ForecastEligibility](../../app/application/contracts/forecast_eligibility.py),
internal frozen dataclass cho requested mode/candidate, actual eligible method/version/
artifact, ExecutionDetails selection reason, existing ForecastWarning và scoped
Readiness Issue blockers. `failure_kind` phân biệt HISTORY_UNUSABLE, ARTIFACT_INVALID,
DEPENDENCY_UNAVAILABLE và RUNTIME_UNAVAILABLE. Đây không phải retained/public schema;
không đổi hash/serialization/identity schema1/schema2 hoặc DTO R01/C01.

`ForecastServing.assess` gọi chính `choice` của execution, không selector mới. Shared
baseline guard yêu cầu ≥1 usable observation cho mỗi requested Product; BASELINE
mode cũng preflight guard này trước start. `_choose` sở hữu trained thresholds duy
nhất, gồm ≥28 usable observations và ≥14 supervised rows cho trained được chọn;
trước D2 check training rows nằm thêm ở serving wrapper. Consolidation áp dụng new
selection; replay dùng `_replay_choice` cũ với đúng retained artifact/input/policy,
không áp lại selection gate để đổi model. Thứ tự recognized absence, compatibility,
observation minimum, baseline-selected evaluation và trained-row gate giữ truthful
reasons/whole-scope fallback. Invalid capture vẫn raise validation error.

No candidate/recognized missing artifact/history-ineligible/baseline-selected là
recognized fallback, baseline phải ready; actual baseline/candidate/reason/warnings
vẫn được retain bởi execution hiện có. Sparse days không zero-fill, observed0 giữ0,
unknown stockout giữ null/observed compatibility. Projection luôn từ raw captured
observations, không feed reconstructed estimates thành observed support. Không dùng
recipe/stock/supplier/calendar/usage/purchase để gate model main hiện tại; explicit
serving config vẫn required. Không thay main model thành challenger C.

R01/C01 và Today caller dùng typed assessment, trả Product-scoped
CENSORED_HISTORY_NOT_USABLE/PRODUCT_HISTORY_MISSING khi baseline không eligible.
Dedup blockers giữ cả entity/date/source, không làm mất Product cùng code. Artifact
corruption/policy incompatibility giữ MODEL_ARTIFACT_INVALID/data invalid; recognized
ModelDependencyError (kể cả cause được artifact loader wrap) và wrapped storage
OSError dùng existing EXECUTION_UNAVAILABLE/execution unavailable, không gán history
missing/data invalid. Unexpected programming/raw technical errors vẫn propagate,
không thành baseline success hoặc missing-data blocker. Unmet baseline prerequisite
short-circuit downstream artifact checks; không claim artifact đã verified khi chưa
đến bước load. Không artifact failure nào được success-fallback.

GET không train/infer/solve hoặc ghi business state. Sales-only linked case kiểm
fresh-session sparse observations, absent operational domains, no ForecastRun/
PlanningRun sau GET; execution sau đó giữ metadata/warnings và replay sau live sales
correction. Linked cases bao gồm all-censored R01/C01/Today, dependency-vs-integrity,
explicit no-history scope và foreign Store denial. Synthetic tests không chứng minh
real accuracy. Commands/owned DB/manual flow tại
[runbook D2](../runbooks/FULL_TEST_FLOW.md#data-readiness-d2).

D2 giữ các vấn đề default/custom/saved contextual readiness và public warning/method
fields ở D4; offer omission được triển khai D3 riêng. Current public action warnings không tự thêm
BASELINE_FALLBACK từ internal assessment trong slice này. Không sửa FE/permissions,
accepted ADR, E1–E4, runtime người dùng hoặc workbook gốc. Sáu workbook mới trong
ignored runtime/uploads là optional acceptance inputs theo consumer, chưa dùng/train
trong D2; không kế thừa findings calendar của demo cũ.

## CURRENT FACT — D3 confirmed source facts và offer admission

New C02 acceptance pin `offer_eligibility/1` trong private PublicPlanningAcceptance.
PlanningPipelineDeclarations/operational request giữ typed
[OfferAdmission/OfferOmission](../../app/application/contracts/offer_admission.py):
Store/term/supplier/Ingredient IDs, canonical term version/effective dates, reason,
missing fields và canonical source reference. Proof scope là
CAPTURED_ELIGIBLE_OFFERS_ONLY. Capture/result digests bao gồm policy/omissions;
không thay objective, requirements, native resource/deadline/certification policy,
serving fairness, loss hoặc winner rules.

| Classification | Admission D3 |
| --- | --- |
| A — thiếu fact local, identity/version/effectivity/dependencies xác định | Omit offer, giữ OFFER_OMITTED warning/evidence. Không loại Product nếu alternatives hoặc existing stock vẫn cho bài toán xác định. |
| B — invalid/conflicting, corrupt, cross-Store, không xác định scope | Giữ blocker/execution failure đúng source boundary; không dùng omission để che. Unit/date/identity conflicts và negative values không coi như absent. Unknown recipe graph vẫn global blocker. |
| C — shared budget/fee/context/capacity/supplier-limit/inbound unknown | Giữ blocker ngay cả khi omit hết offers; không đặt fees0, unlimited hay CONFIRMED_NONE ngầm. |

A được nhận trong các trường hợp cụ thể: zero-cost term không có finite source/
declared bound; absent/null required scalar pack price/size/MOQ/lead/unit nếu các
facts còn lại validate và identity/date scope đủ; shelf_life_days unknown khi
Ingredient có expiry_tracking. Shelf life không cần cho untracked Ingredient không
phát issue. Canonical term promotion vẫn strict; omission không cho phép import
record thiếu required facts vào DB. Missing scalar path chủ yếu là detached/source
admission boundary; shelf-life nullable và zero-cost bound là cases canonical thật.
Không sửa price basis/MOQ/positive-price value để làm offer eligible.

Bound và quantities/costs chỉ tính từ offers còn eligible. Original source facts,
term identities và raw menu vẫn retained trong capture; omitted terms không vào
PreparedDecisionInput/procurement input. Fee coverage được kiểm lại trên remaining
offers và known component bindings, nhưng vẫn cần unique COMPLETE declaration,
đúng currency/horizon/mode. Coverage UNKNOWN, unresolved component identity,
multiple current fee rows, conflicting currency/effectivity không được omission
giải quyết. Supplier constraints/capacity được validate trên original declarations
trước projection; chỉ bỏ scoped purchase limit của omitted-only pair khỏi computed
envelope, giữ original proof. Applicable safety-stock kể cả0 vẫn block như trước.

Không eligible offer vẫn xét zero-purchase trong engine hiện có. Stock đủ có thể có
winner/outlay0; stock không đủ có thể no eligible candidate. Engine proof vẫn
CAPTURED_FINITE_DOMAIN_ONLY, liên kết admission marker để chỉ rõ domain đã hạn chế;
không có market-infeasibility hoặc no-supplier claim. Existing technical bounds
không thành physical supplier capacity. Không mở search universe.

Confirmed inventory vẫn dùng current dependency-bound COMPLETE_CURRENT_LOTS hoặc
CONFIRMED_EMPTY; mutation hoặc multiple-current proofs không được chọn thuận lợi.
Explicit fee NONE khác unknown; effective procurement declarations/approved unit
conversions vẫn cùng workflows. Không thêm assumptions service/declaration/default,
không sửa canonical stock/terms/fees khi Planning. Missing recipe/stock dependencies
giữ Product/date exclusions, raw menu và override NOT_EVALUATED; standalone BOM
all-or-error giữ nguyên. Forecast serving không nhận thêm Planning prerequisites.

Private PlanningSourceEvidence bổ sung optional typed confirmations: exact source
keys/entity IDs, provenance digest, unique matching immutable Import audit ID/actor/
canonical commit time khi có proof. Đây là actor/time của source writer audit,
không tự nhận là Owner profile approver hoặc thời điểm người dùng review trước đó.
Thiếu hoặc ambiguous audit giữ actor/time/audit=null;
không dùng Run actor giả làm source confirmer. Existing term/fee/declaration payloads
giữ values, versions và effectivity; no live rebuild khi read. Existing immutable
mapping approval/reuse và IMPORT_VALUE/batch-facts rules không đổi, không review lại
mỗi upload nếu proof còn hợp lệ. Internal/manual source không có Import audit thì
actor proof vẫn unknown rõ ràng; D3 không tạo approval fact để lấp gap này.

Legacy fields mặc định null và được serializer elide khi absent; /1 và old /2 request/
source/capture bytes/digests giữ nguyên. Old queued public acceptance không có marker
tiếp tục old admission khi worker chạy; completed Runs không reclassify từ live facts.
Retained validator đối chiếu accepted policy, omission identity/version/source bound
và source-proof coverage. Không migration hoặc đổi planning_storage/1/package1.

Public C03/result, Ingredient inspection và explanation reuse PlanningNotification
OFFER_OMITTED với existing details.entity_id/ingredient_ids/classification/proof_scope/
suggested_action; không endpoint/DTO field mới. FE generic warning renderer có thể
đọc existing fields, không có FE source change. Tổng thể readiness/warning UX thuộc
D4. Tại checkpoint D3, R01/C01 còn conservative với old offer-bound checks và
default-mode estimate; D4 refinement được mô tả riêng bên dưới.

Coverage mới tại [unit admission](../../tests/unit/test_offer_admission.py) và
[HTTP/PG](../../tests/integration/test_planning_offer_admission.py); Import source
proof nối [supplier acceptance](../../tests/integration/test_import_supplier_basis.py).
Commands/expected cases ở [runbook D3](../runbooks/FULL_TEST_FLOW.md#data-readiness-d3).
Synthetic correctness không là forecast accuracy hay research benchmark evidence.

## CURRENT FACT — D4 contextual readiness và public warnings

D3 checkpoint local `d0f3716c261f6634d5fcd5ae886c00cf3014276c`; D4 COMPLETE checkpoint local
`72415332e2a5224ab9909d54606d7e7e374bdd18`; nay tích hợp main local, chưa push/deploy.
Existing R01/C01 routes thêm optional URL-encoded
`planning_request` (strict C02 PlanningRequest JSON). Không query đánh giá default
ngày Store hôm nay; có query đánh giá đúng request, không suy hypothetical custom.
R01 forecast_start_date nếu đồng thời có phải khớp ngày request. Malformed/null,
duplicate keys hoặc query ngoài planning action trả422; config rejection trả200
blocked assessment. Không endpoint, migration hoặc computation trong GET.

| Field | Scope/current behavior D4 |
| --- | --- |
| R01 planning.can_execute / availability | Action planning với default hoặc supplied request tại snapshot; true chỉ admission/preflight available, không chứng minh winner/requirements satisfied. Unknown prerequisites giữ unknown/false; known missing default trong default flow blocked/false. |
| C01 readiness.can_generate / status | Chính R01 planning assessment; assessment.input_scope xác định DEFAULT_CONFIGURATION/SUPPLIED_REQUEST, requirements_mode và configuration_status; có blockers/warnings typed, version planning_readiness/1. |
| C01 requirements_modes[].availability | Discovery của setup/resolver/saved reader hiện có, không khả năng execution của mọi request thuộc mode; không dùng thay contextual assessment. |
| C01 capabilities | Public flow wired flags, không data readiness hoặc quyền được cấp; acceptance vẫn current-authorized. |
| Today readiness sections | Cùng shared evaluation, default scope tại ngày Store; không hypothetical request. Source/counter masking và section authorization giữ nguyên. |
| R01 forecast_assessment / C01 readiness.forecast | D2 requested/actual method/version/selection reason, null khi chưa xác định; quality_status=not_evaluated, không claim accuracy hoặc probability. |

Configuration preflight gọi đúng C02 resolve_planning_setup; full custom explicit
thresholds/overrides và stored saved không cần default. Custom inheritance vẫn cần
same-path default/version, null scalar invalid, [] explicit thay list. Budget0 giữ0;
omitted/null late-bind current cap, unknown ceiling không bypass. Saved active dùng
current stored version, missing/archived/cross-Store và inactive overrides giữ resolver
guards. GET không pin version cho Run; C02/execution revalidate và retain riêng.

Detached planning_admission.planning_declarations chứa chính computation D3 được
chuyển khỏi DB adapter, wrapper execution giữ legacy policy marker behavior. Contextual
bounds dùng effective resolved budget; remaining fee binding/shared unknown giữ như
execution. Corrupt/conflict/unknown graph và safety0 vẫn blockers; no eligible offers
không tự block Product, winner chỉ được engine xác định sau đó.

Current R01 issues có optional typed details field/impact/entity_id/reference/version/
classification/proof_scope/suggested_action. D2 forecast warnings enrich existing
same-code/Product issues thay vì thêm duplicate; dates/scope giữ nguyên và ordering
deterministic. Exclusions/history watermark/current-date assumptions tiếp tục công khai.
C03/C08 OFFER_OMITTED thêm optional source_reference/source_version từ retained
D3 evidence; không actor/time giả hoặc live reclassification. Legacy optional fields
elide khi absent; old storage/digests/queued policy không rewrite. I06 retained
Issue/details schema giữ riêng, không tự thêm Planning assessment vào completion.

Documented drift ở D1 về sales watermark được reconcile với CURRENT FACT của
baseline/C02: missing watermark là HISTORY_NOT_AVAILABLE_THROUGH_CUTOFF warning,
không missing-day0 hoặc completeness gate mới. Model eligibility/serving không đổi.
GET vẫn estimate, chưa chạy forecast/solver/numeric validation toàn engine, không SLA
hoặc browser/full-suite claim. D3 overall deadline failure chưa có root cause; D4 giữ
deadline180s/proof/search policy và targeted regression, timing instability còn mở.

Canonical [R01](../IMPORT_MAPPING_API_CONTRACT_VI.md#readiness-v1) và
[C01](../PROCUREMENT_API_CONTRACT_VI.md#planning-context) sở hữu API/FE delta;
[runbook D4](../runbooks/FULL_TEST_FLOW.md#data-readiness-d4) có commands/expected cases.

## D5 — backend linked acceptance và integration boundary

CURRENT FACT: user authorized backend-only HTTP/application workers/PostgreSQL,
không yêu cầu FE. [Matrix/runbook](../runbooks/FULL_TEST_FLOW.md#data-readiness-d5)
reuse D2–D4 và chỉ thêm liên kết/invariants thiếu. Tests trong
[public linked acceptance](../../tests/integration/test_data_readiness_acceptance.py)
reuse public setup của Import, không framework/production test route/permission mới.
Synthetic fixtures explicit: received date unknown, known stock/completeness, no fees,
one bounded price offer và one unbounded zero-price omission. Bounded independent
oracle kiểm14 demand/stock12/pack4/cost10 →1 pack/outlay10; stock20 →zero purchase.
Oracle không nâng production proof hoặc claim market impossibility.

Future-only reviewed fee amendment giữ historical fee guard; UNKNOWN coverage cho
request mới vẫn block. Same-key terminal replay là current terminal200/poll0 của
cùng Run, không receipt queued cũ; request/resolved budget/capture không resolve lại.
Ceiling đổi sau GET phải revalidate khi C02 mới. C03/C08/fresh Session kiểm retained
facts/warnings/digests sau stock, budget và future fee mutation. Mixed scope giữ
excluded Product/override NOT_EVALUATED, recognized NO_ARTIFACT fallback giữ actual
method/reason. Mandatory safety0 chỉ applicable computed dependencies mới block.

Backend acceptance VERIFIED bằng final focused unit/API/PostgreSQL invocation;
source integration có final focused gate riêng trên PostgreSQL5437/limited role,
head0027. OpenAPI source73/66 và handoff cập nhật; runtime8103 giữ source manifest
052cddee, không restart/migrate. Không conflict merge hoặc kiến trúc mới;
không full-suite claim. Không sửa production source trong D5; OpenAPI JSON-equal
so với D4. Workbook smoke/browser E2E chưa chạy; accuracy/real impact
chưa đánh giá. Không tự suy business declarations từ uploads. D3 timing overrun
vẫn known limitation nếu không có telemetry chứng minh root cause.

Integration chú ý shared D4 files: app/api/readiness.py và application/contracts/
readiness.py/planning_context.py sở hữu query+assessment; readiness_evaluation.py,
contextual_planning.py và planning_admission.py dùng canonical resolver/admission.
DB planning_capture wrapper tiếp tục giữ legacy acceptance marker. Import
contracts/import_mapping.py giữ CompletionReadinessIssue/details riêng; public
PlanningNotificationDetails optional source reference/version elide khi absent.
LLM/challenger integration phải giữ các boundaries này, current sensitive-read
guards và retained semantics; không đưa research eligibility/LLM vào business truth.
D5 không thêm contract delta ngoài D4 cần FE đồng bộ sau này.

## Existing warning contracts và remaining proposals

ACCEPTED DECISION — warning vẫn cho chạy; blocker chặn đúng action/scope; irrelevant
missing không có issue. Existing retained Runs không bị update/reclassify theo policy
mới. GET/readiness không solve/train/infer hoặc mutate business data. Current GET
có auth/session bookkeeping và read-only business snapshot, có thể đọc/verify artifact;
không diễn giải yêu cầu này thành thay đổi auth lifecycle.

CURRENT FACT — tái sử dụng các contracts hiện có:

| Boundary | Shape hiện có | Giới hạn / extension PROPOSAL |
| --- | --- | --- |
| R01 current / Import retained completion | Issue `{code,source,scope,entity_id,affected_dates,details}`; severity theo vị trí blockers/warnings; R01 details typed D4, retained completion vẫn empty strict DTO | Generic assumption references/actor lifecycle còn PROPOSAL; không generic dictionary/default service. |
| Import preview/completion/meta | Notice `{code,severity:WARNING\|ERROR,message,field?,entity?,impact?,source_location?}` | Dùng Notice, chỉ thêm optional remediation/reference nếu cần; missing/conflict ERROR không downgrade. |
| Forecast execution | ForecastWarning `{code,severity,field,entity,impact,product_id?}` và ExecutionDetails selection/candidate | Không tạo taxonomy song song; optional typed remediation/assumption refs, giữ identity/serialization cũ. |
| Decision/BOM | `DecisionIssue.kind=INFO\|WARNING\|DATA_BLOCKER\|HARD_VIOLATION`, affected refs, impact, suggested_action | Giữ kind và mapping public hiện có; không đổi HARD_VIOLATION thành warning. |
| Public Planning | PlanningNotification `{code,message,details}`; warnings/errors/exclusions và forecast.warnings riêng | Reuse adapters, mapping code công khai; additive impact/remediation/assumption refs, FE không đoán severity chỉ từ code/message. |

PROPOSAL — cùng code chỉ reuse khi cùng meaning. Map existing consumer codes rõ,
ví dụ R01 `PAYABLE_FEE_COVERAGE_UNKNOWN` → Planning `PAYABLE_FEE_UNKNOWN`;
không silently rename contract. Nếu extension cần severity thì thêm optional explicit
field theo shape từng boundary; không ép Import severity enum vào mọi contracts.
Deduplicate theo code + action + scope/ref + affected dates + assumption refs,
không deduplicate bằng code mà làm mất entity. Messages nêu capability bị mất và
thao tác khắc phục, không hứa chất lượng bằng phần trăm tự tạo.

CURRENT FACT — Import preview giữ Notice/provenance trên rows/groups; commit xây
completion cùng transaction, `completed_with_warnings` theo retained preview summary
warnings và giữ completion/audit với preview reference/digest và warning count.
Không coi count là full warning messages được copy vào completion; consumer cần
retained preview/detail để đọc nguyên issues. I06 `completion_in_transaction` chỉ evaluate các action
đủ quyền trong import/menu/inventory; không đánh giá forecast/planning và không
chứng nhận Store-wide READY. R01 có action warnings, C01 D4 giữ chúng trong
readiness.assessment. Forecast metadata giữ warnings, Planning capture giữ forecast
view/identity/source versions/operational source evidence và result giữ warnings.

PROPOSAL — retain đúng warnings áp dụng ở acceptance/capture/result của Run mới,
cùng policy version, chosen method và source/declaration references. Dynamic R01
là assessment snapshot có data_version/evaluated_at, không phải audit writer mới.
Không append mọi GET vào Run hoặc thay historical issues. Với I06 giữ snapshot lúc
commit; muốn biết hiện tại gọi R01 theo quyền và action được yêu cầu, không thêm
endpoint chỉ để lấy warnings.

PROPOSAL — assumption reference trỏ fact/declaration/config sẵn có khi đủ:
`reference_id`, immutable `version`/digest, kind, source/evidence reference, Store,
typed scoped IDs/date range, actor hoặc operator identity, confirmed_at và effectivity,
policy version, trạng thái current/stale/conflicting. Các trường là logical requirements,
chưa phải schema/migration đã implement. Hiện source/profile/version/actor/provenance,
dependency digest, observed_at/effective dates và captured config/source evidence
đã có ở các workflows; cần map từng loại, không tạo generic assumption service.

ACCEPTED DECISION — batch `IMPORT_VALUE`, sales report identity/date/quantity và
stockout update declarations không thành reusable default. Approved interpretation/
immutable alias/conversion proof còn hợp lệ không cần Owner xác nhận lại mỗi upload;
rows mới, drift, dependencies và current rights vẫn kiểm lại. Unknown assumption
không thành canonical fact. Hypothetical facts chỉ thuộc Run/simulation; không ghi
stock/terms giả. Existing NONCURRENT_PLANNING_CURRENT_FACTS giữ temporal meaning.

### Ví dụ response fragments/messages

Các JSON dưới đây là **PROPOSAL fragments**, không full current HTTP response;
`message/impact/remediation` ở R01 là additive proposal. Không gửi chúng như current
DTO trước D4. UUID là synthetic; conditions ngoài ví dụ được giả định đã eligible.

Sales-only, baseline đã explicit configured; recipe/stock/usage/purchase/calendar
không cần cho forecast. Nếu stockout không known thì thêm warning riêng dưới đây.

```json
{"action":"forecast","availability":"ready","can_execute":true,"blockers":[],"warnings":[],"result_assessment":"NOT_ASSESSED"}
```

Short history của main trained path: baseline eligible; không gọi trained thành công.

```json
{"actual_model_type":"historical_quantile_baseline","selection_reason":"NOT_READY_HISTORY","warnings":[{"code":"BASELINE_FALLBACK","severity":"WARNING","message":"Lịch sử chưa đủ cho model đã chọn; dùng baseline trên scope yêu cầu.","impact":"Chưa xác lập chất lượng dự báo.","remediation":"Bổ sung lịch sử usable rồi đánh giá lại model."}]}
```

Unknown stockout giữ null và observed compatibility theo ADR-A1.

```json
{"code":"STOCKOUT_UNKNOWN","source":"sales","scope":"PRODUCT","entity_id":"00000000-0000-0000-0000-000000000001","affected_dates":["2026-10-14"],"details":{},"message":"Chưa biết ngày này có hết hàng; dùng lượng bán quan sát.","impact":"Có thể thấp hơn nhu cầu thực.","remediation":"Bổ sung quan sát stockout có nguồn nếu có."}
```

Missing recipe Product: forecast vẫn hợp lệ; Planning exclusion phải hiện rõ scope.

```json
{"forecast_available":true,"excluded_products":[{"product_id":"00000000-0000-0000-0000-000000000001","reason_codes":["RECIPE_PERIOD_GAP"],"affected_dates":["2026-10-16"]}],"message":"Product này chưa được tính trong Planning ngày 16/10; bổ sung recipe hiệu lực. Forecast được giữ."}
```

Unknown fee: blocker Planning, không blocker forecast; explicit NONE khác missing.

```json
{"action":"planning","availability":"blocked","can_execute":false,"blockers":[{"code":"PAYABLE_FEE_COVERAGE_UNKNOWN","source":"fees","scope":"STORE","entity_id":null,"affected_dates":[],"details":{},"message":"Chưa đủ coverage phí phải trả; chưa thể kiểm ngân sách basket.","remediation":"Xác nhận phí/coverage hoặc khai rõ không có phí trong workflow phí."}]}
```

Confirmed empty stock: đây là declaration fragment đã đủ proof hiện hành, không cần
warning “thiếu stock”. Nó không tự làm toàn Planning ready.

```json
{"kind":"INVENTORY","state":"CONFIRMED_EMPTY","ingredient_id":"00000000-0000-0000-0000-000000000002","covered_lot_ids":[],"message":"Đã xác nhận tồn bằng 0 cho Ingredient này; phép tính dùng 0 trong scope đã xác nhận."}
```

Model C thiếu calendar nhưng baseline main eligible: cross-method assessment đề xuất,
không sửa output identity hoặc eligibility của E1–E4.

```json
{"action":"forecast","eligible_methods":["historical_quantile_baseline"],"ineligible_methods":[{"method":"challenger_C","code":"CALENDAR_COVERAGE"}],"message":"Model C chưa đủ calendar có nguồn; baseline đủ dữ liệu. Chạy baseline là kết quả baseline, không phải C hoặc benchmark C pass."}
```

Mandatory unsupported safety constraint: block applicable computed scope, không claim passed.

```json
{"action":"planning","availability":"blocked","can_execute":false,"blockers":[{"code":"MIN_SAFETY_STOCK_UNSUPPORTED","source":"constraints","scope":"INGREDIENT","entity_id":"00000000-0000-0000-0000-000000000002","affected_dates":["2026-10-16"],"details":{},"message":"Ràng buộc safety stock đang áp dụng chưa được engine hỗ trợ.","remediation":"Giữ chặn tới khi semantics được hỗ trợ hoặc cấu hình được thay đổi có thẩm quyền."}]}
```

## Challenger/protocol — CURRENT FACT riêng, không nhập vào main

Read-only source trong sibling `backend-forecast-engine-challenger`:
`app/application/forecast_challenger_validation.py:admit_input/admit_artifact`,
`app/application/forecast_benchmark_admission.py:admit_plan/calendar_at_origin`,
`app/application/use_cases/forecast_challenger.py`,
`app/application/demo_workbook_admission.py:assess/forecast_projection` (untracked WIP),
`docs/features/FORECAST_ENGINE_INTEGRATION.md` (modified WIP).
Không dùng link sibling tương đối như một dependency của D1/main checkout.

CURRENT FACT — challenger admission đòi exact sourced calendar từ first observation
đến D+7, aware availability, exact scope/unit/window/point/CQR/artifact identity;
production gate vẫn khóa. Benchmark frozen A/B/C có paired tasks, holdout quarantine,
partition/masks và source/config digests. Một shared A/B/C protocol gate đòi calendar
không chứng minh main baseline cần calendar. Demo admission WIP đọc các workbook
roles cố định để đánh giá dataset/protocol cụ thể; các E4 operational-date findings
không là general import requirement. Nó giữ C calendar/vintage blocked, retrospective
demo assumptions tách evidence; không là public Store readiness.

HISTORICAL INFORMATION / CURRENT FACT theo source checkpoint — E1/E2/E3 commits
ở challenger; E3 real accuracy vẫn `REAL_BENCHMARK_BLOCKED` /
`INSUFFICIENT_EVIDENCE`; E4 uncommitted `COUNTERFACTUAL_SYNTHETIC`, manifest incomplete,
real impact blocked, E5 chưa làm. D1 không chạy/re-score/training, không sửa protocol,
checkpoint, dataset hoặc promotion status; không claim đã độc lập verify private
runtime evidence.

PROPOSAL D5 — nếu đo fallback/confirmed assumptions, tạo protocol version mới với
method eligibility từng action/scope, actual selected arm và assumption IDs trong
identity; freeze trước execution. Báo model-C eligibility, selected product method và
research benchmark admissibility riêng. Giữ old protocol/digests/results để so sánh;
không đổi C thành baseline trong old paired cohort hoặc nới gate để pass.

## Dependency/API impact và thứ tự triển khai — CURRENT FACT / PROPOSAL D5

| Slice | Phạm vi, phụ thuộc và boundary thay đổi | Gate trước khi kết thúc |
| --- | --- | --- |
| D1 | Audit/policy này, CURRENT_STATE/ROADMAP; không runtime/API/schema delta | Source/test trace, JSON examples, local links, UTF-8/whitespace; dừng chưa commit/push/merge |
| D2 | CURRENT FACT COMPLETE, checkpoint9f720caf: shared choice + typed internal assessment, scoped history blockers và dependency/runtime classification; public shapes/replay giữ nguyên | Focused forecast/HTTP/PostgreSQL regressions, linked all-censored fail→fix, fresh-session retained evidence; không challenger activation |
| D3 | CURRENT FACT COMPLETE, local checkpoint d0f3716c261f6634d5fcd5ae886c00cf3014276c: versioned offer admission/source proof; /1/legacy giữ nguyên | Focused alternatives/fee/capacity/safety/unknown graph/stock/stale/permissions/Import/replay và OpenAPI equality |
| D4 | CURRENT FACT COMPLETE checkpoint72415332: contextual request/resolver/admission và shared warnings; I06 retained schema giữ nguyên | Focused modes/budgets/scope/retained/security/OpenAPI delta; không FE/browser hoặc full-suite claim |
| D5 | CURRENT FACT backend acceptance VERIFIED, local tests/docs WIP: public setup/actual workers/PG, independent oracle, retained/security/concurrency | Final focused invocation và OpenAPI equality D4 PASS; timing instability còn mở; không full-suite/FE/workbook/accuracy claim |

BE phụ thuộc eligibility/classification/capture/projection hiện có; domain vẫn plain
Python, không service registry/agent framework/new infrastructure. FE cần render
warning vs blocker vs excluded/not-evaluated, mode-specific eligibility, actual method,
impact/remediation và assumption references theo quyền; không ép upload đủ files.
ML/Data cần giữ policy/schema/artifact/fit/availability identity, không nâng quality
từ history-only inputs. Demo/manual flow cần sales-only và complementary uploads,
không bắt buộc training/provider. D1 không sửa FE hoặc main runtime.

CURRENT FACT D4 — additive versioned assessment/input_scope phân biệt default-mode
estimate với supplied request. Planning/Import canonical contracts và compatibility
changelog sở hữu semantic delta/FE behavior. Không endpoint song song, không thay
`/1`, schema1 replay hoặc retained old Run policy. OpenAPI diff D3→D4 đã đối chiếu;
original baseline provenance giữ nguyên. FE/browser integration còn chưa thực hiện.

Phân loại sản phẩm đã chốt, không còn câu hỏi “có cần đủ files?”. Các quyết định
nghiệp vụ thật sự cần trước capability mới là semantics/enforcement của mandatory
safety stock nếu muốn hỗ trợ, và nguồn/phạm vi/effectivity của một reusable operational
declaration mới nếu existing workflows chưa biểu diễn được. Không cần hỏi lại Owner
cho immutable proof hợp lệ. CQR/calendar changes hoặc research promotion có review
riêng, không là điều kiện để dùng baseline hiện có. D2 được authorized riêng;
D3/D4/D5 được authorized riêng; D5 là backend-only acceptance, không mở lát tiếp theo.

## Acceptance cases — D2–D4 coverage và PROPOSAL D5

CURRENT FACT D2: forecast/stockout/eligibility/GET/replay cases được cover bởi
[unit eligibility](../../tests/unit/test_forecast_eligibility.py),
[linked HTTP/PG](../../tests/integration/test_forecast_readiness.py) và regressions
F1–F3/R1. D3 facts/offer và D4 public context/warnings có focused coverage riêng tại
runbook. D5 FE/browser/consumer-specific acceptance còn PROPOSAL, không suy từ
passing backend cases rằng đã browser verified.

| Case | Outcome cần giữ/chứng minh | Coverage / slice |
| --- | --- | --- |
| Sales-only, explicit baseline, known quantity/unit/date, ≥1 usable sample | Forecast đủ Product×7; không đòi recipe/stock/supplier/calendar/usage/purchase; no invented confidence | F1/F3 regressions, D2/D5 |
| Một missing day, explicit observed0 và Product hoàn toàn no history | Missing không zero; observed0 giữ; no-history Product được chỉ rõ, không fabricate demand0 hoặc silently omit explicit scope | F1/R1, D2 |
| Short history vs main trained; C blocked vì calendar | Baseline eligible nếu có usable samples; actual baseline/reason retained; C/protocol vẫn blocked | F2/F3 + separate protocol, D2/D5 |
| Unknown/true unsupported/known-false stockout, all-censored GET | Compatibility warning/null giữ; unsupported samples exclude; all unusable trả scoped readiness blocker qua API, không crash hoặc demand0 | Stockout unit + mới linked GET, D2 |
| Corrupt/incompatible artifact; replay missing pinned artifact | Error riêng integrity/dependency; không success fallback/latest/retrain; old Run immutable | F3, D2/D5 |
| Một Product missing recipe, Product khác computable; unknown Ingredient attribution | Forecast hợp lệ giữ; known exclusions/override NOT_EVALUATED; unknown graph global blocker, không nâng fill rate bằng biến mất scope | P1/R1, D3 |
| Unknown stock vs confirmed empty, cả retained zero lots; stale proof sau stock mutation | Unknown không0; current confirmed empty dùng0; stale dependency quay unknown; không write stock khi Planning | I1/P1, D3 |
| Unknown fee vs complete NONE, fee keys/currency/horizon conflict | Planning block hoặc known0 theo proof; forecast unaffected; no min-outlay/budget pass khi coverage unknown | P1/R1, D3/D5 |
| Một offer thiếu numeric/bound và alternative đủ facts | Omission evidence/ref rõ; chỉ eligible captured-domain proof; không market no-supplier/infeasible claim; invalid scope không skip | Mới D3, không thay current guard ở D1 |
| Budget0 vs absent; full custom/saved khi không default; inherited path missing default | Zero known; absent cap B; full config eligible theo mode; inherited default vẫn cần exact version; không implicit unlimited | P2 + contextual D4 |
| Mandatory safety constraint0 trên computed Ingredient, unrelated/future constraint | Applicable constraint block; unrelated không spam forecast warning; không nói constraint passed | R1/procurement, D3/D5 |
| Complementary files/one mixed-domain file; import completed_with_warnings | Chỉ schema/action đang dùng cần facts; retained warnings/provenance/current rights, I06 không Store-wide READY | I1, D4/D5 |
| Approved immutable mapping proof reuse vs batch IMPORT_VALUE | Không reapprove không cần thiết; source/rows/current rights vẫn validate; batch facts không reusable defaults | Import existing workflow, D3 |
| Readiness/read/replay sau policy/config thay đổi | GET không solve/infer/train/business mutate; no sensitive-data leak; old Run không rewrite/reclassify; new Run new identity | R1/P2, D4/D5 |

Rollback scope D1: ba tài liệu tại checkpoint c930dfe. D2 checkpoint9f720caf;
D3 scope chỉ admission/capture/source proof/projections/contracts/tests/docs.
Giữ retained data/artifacts/private test config. Khi đã có D3 Runs, rollback new
acceptance cần giữ reader hiểu D3 optional fields; binary D2 không tự hiểu payload
D3 extra fields. Không xóa evidence hoặc đổi digest để ép đọc bằng binary cũ.
Không downgrade DB, sửa main/challenger WIP hoặc xóa workbook/runtime để rollback.
Verification commands/results thuộc conversation; đây không phải PASS report.
