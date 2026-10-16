"""Durable Import staging plus S4.5 atomic catalog/sales/recipe canonical commit."""

import base64
import hashlib
import hmac
import json
import threading
import logging
import io
import zipfile
from datetime import datetime
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo
from sqlalchemy import select
from app.application.contracts.auth import AuthError, Pagination
from app.application.use_cases.auth import Actor
from app.application.use_cases.forecast_execution import _is_uncertain_commit
from app.application.contracts import import_mapping as dto
from app.application.import_analysis import (
    discover,
    build_spec,
    options,
    identity_issues,
    source_context_conflicts,
    captured_domains,
)
from app.application.import_preview import make_preview, notice
from app.application.import_descriptors import descriptors
from app.infrastructure.auth_crypto import digest
from app.infrastructure.database.auth_session import auth_session
from app.infrastructure.import_parser import parse_source
from app.models.import_staging import (
    ImportBatch,
    ImportFile,
    ImportBlob,
    ImportJob,
    ImportProfile,
    ImportProfileVersion,
    ImportSourceContext,
    ImportPreview,
    ImportReceipt,
    ImportAudit,
)
from app.models.auth import AuthSession, AuthAccount
from app.repositories.auth import AuthRepository
from app.repositories.import_staging import capture_read_set, content_digest, read_set_in_session
from app.application.import_commit import commit_rows, effective_digest, write_rows, SUPPORTED
from app.infrastructure.planning_process import current_process, liveness
from app.application.contracts.planning_run import ProcessIdentity

ALL_READS = (
    "menu.read",
    "ingredient.read",
    "recipe.read",
    "sales.read",
    "inventory.read",
    "supplier.read",
    "procurement.cost.read",
    "budget.read",
)
READS = {
    "calendar_events": ("calendar.read",),
    "promotion_observations": ("menu.read", "sales.read"),
    "usage_history": ("ingredient.read", "usage.history.read"),
    "purchase_history": ("ingredient.read", "supplier.read", "purchase.history.read", "procurement.cost.read"),
    "sales": ("menu.read", "sales.read"),
    "recipes": ("menu.read", "ingredient.read", "recipe.read"),
    "inventory_count": ("ingredient.read", "inventory.read"),
    "opening_stock": ("ingredient.read", "inventory.read", "supplier.read", "procurement.cost.read"),
    "inventory_receipts": ("ingredient.read", "inventory.read"),
    "products": ("menu.read",),
    "ingredients": ("ingredient.read",),
    "suppliers": ("supplier.read",),
    "supplier_terms": ("supplier.read", "ingredient.read", "procurement.cost.read"),
    "payable_fees": ("supplier.read", "procurement.cost.read"),
    "scope_declarations": ALL_READS,
}
READS.update(
    {
        "scope_declarations.INVENTORY": ("ingredient.read", "inventory.read"),
        "scope_declarations.SALES_COVERAGE": ("menu.read", "sales.read"),
        "scope_declarations.PROCUREMENT_CONTEXT": (
            "ingredient.read",
            "supplier.read",
            "procurement.cost.read",
            "budget.read",
        ),
    }
)
WRITES = {
    "calendar_events": "calendar.write",
    "promotion_observations": "sales.record",
    "usage_history": "usage.history.write",
    "purchase_history": "purchase.history.write",
    "sales": "sales.record",
    "recipes": "recipe.create_version",
    "inventory_count": "inventory.count.correct",
    "opening_stock": "inventory.receive",
    "inventory_receipts": "inventory.receive",
    "products": "product.create",
    "ingredients": "ingredient.create",
    "suppliers": "supplier.create",
    "supplier_terms": "supplier.terms.create",
    "payable_fees": "supplier.fees.manage",
    "scope_declarations": "supplier.fees.manage",
}


def rev():
    return str(uuid4())


class _ImportCommitUncertain(Exception):
    """Recognized DB transport failure during canonical commit only."""


class ImportStaging:
    def __init__(self, auth, settings):
        self.auth, self.engine, self.settings, self.clock = (
            auth,
            auth.engine,
            settings,
            auth.clock,
        )
        self._execution = threading.Lock()
        self._current = None

    def _batch(self, s, ident, lock=True):
        query = select(ImportBatch).where(ImportBatch.id == ident)
        if lock:
            query = query.with_for_update().execution_options(populate_existing=True)
        row = s.scalar(query)
        if row is None:
            raise AuthError("RESOURCE_NOT_FOUND", 404)
        return row

    def _authority(self, s, token, batch, action, csrf=None, sensitive=False):
        required = (action,) + (self._sensitive_reads(batch) if sensitive else ())
        return self.auth.authorize_in_session(
            s, token, batch.store_id, required, csrf=csrf
        )

    @staticmethod
    def _sensitive_reads(batch):
        issues = [dto.MappingIssue.model_validate(i) for i in batch.analysis_json['issues']] if batch.analysis_json else []
        schemas = (
            captured_domains(
                batch.analysis_json['sources'],
                {str(sh.sheet_id): [i for i in issues if i.sheet_id == sh.sheet_id and i.issue_type == 'column']
                 for sh in (dto.SheetInfo.model_validate(i) for i in batch.analysis_json['sheets'])},
            ) if batch.analysis_json else set()
        )
        unknown = not batch.analysis_json or any(
            i['issue_type'] == 'schema_blocker' or i['issue_type'] == 'column' and i.get('target_field') is None
            for i in batch.analysis_json['issues']
        )
        if not schemas or unknown: return ALL_READS
        from app.application.import_analysis import receipt_sensitive_reads
        required={p for schema in schemas for p in READS[schema]}
        required.update(receipt_sensitive_reads(batch.analysis_json['sources'],
            {str(sh['sheet_id']):[i for i in issues if str(i.sheet_id)==str(sh['sheet_id']) and i.issue_type=='column']
                for sh in batch.analysis_json['sheets']},
            {str(sh['sheet_id']):tuple(dto.ImportValue.model_validate(v) for v in sh.get('import_values',()))
                for sh in batch.analysis_json['sheets']}))
        return tuple(sorted(required))

    def _request(self, key, body, match=None, cas=False):
        try:
            if str(UUID(key)) != key:
                raise ValueError()
        except (ValueError, TypeError, AttributeError):
            raise AuthError("VALIDATION_ERROR", 422) from None
        if cas and match is None:
            raise AuthError("PRECONDITION_REQUIRED", 428)
        if match is not None:
            if not (match.startswith('"') and match.endswith('"')):
                raise AuthError("VALIDATION_ERROR", 422)
            match = match[1:-1]
            if not match or any(c in match for c in ('"', ",", "*")):
                raise AuthError("VALIDATION_ERROR", 422)
        return (
            digest(key),
            digest(json.dumps([body, match], sort_keys=True, separators=(",", ":"))),
            match,
        )

    def _old(self, s, actor, store, op, kd, fp):
        r = s.get(ImportReceipt, (actor.user_id, store, op, kd))
        if r and r.request_digest != fp:
            raise AuthError("IDEMPOTENCY_KEY_REUSED", 409)
        return r.record_json if r else None

    def _save(self, s, actor, store, op, kd, fp, result):
        from app.application.use_cases.mapping_submissions import invalidate_submissions
        invalidate_submissions(self, s, actor, store)
        s.add(
            ImportReceipt(
                actor_id=actor.user_id,
                store_id=store,
                operation=op,
                key_digest=kd,
                request_digest=fp,
                record_json=result.model_dump(mode="json"),
            )
        )

    def _audit(self, s, actor, store, kind, record):
        ident = uuid4()
        s.add(
            ImportAudit(
                id=ident,
                actor_id=actor.user_id,
                store_id=store,
                occurred_at=self.clock(),
                kind=kind,
                record_json=record,
            )
        )
        return ident

    def _draft(self, b, files):
        return dto.Draft(
            import_id=b.id,
            display_number="IMP-" + str(b.id),
            store_id=b.store_id,
            data_date=b.data_date,
            status=b.status,
            import_revision=b.revision,
            created_at=b.created_at,
            imported_at=b.imported_at,
            file_count=sum(f.upload_status == "uploaded" for f in files),
            file_set_version=b.file_set_version,
        )

    def _files(self, s, b):
        return s.scalars(
            select(ImportFile)
            .where(ImportFile.import_id == b.id)
            .order_by(ImportFile.id)
        ).all()

    def _quota(self, files):
        accepted = [f for f in files if f.upload_status == "uploaded"]
        count = len(accepted)
        size = sum(f.size for f in accepted)
        return dto.ImportQuota(
            accepted_file_count=count,
            accepted_total_bytes=size,
            remaining_file_slots=20 - count,
            remaining_bytes=100 * 1024 * 1024 - size,
        )

    def _file(self, r, view=True):
        cls = dto.FileView if view else dto.FileReceipt
        return cls(
            client_file_id=r.client_file_id,
            file_id=r.id if r.upload_status == "uploaded" else None,
            filename=r.filename,
            type=r.format,
            size_bytes=r.size,
            content_digest=r.digest,
            upload_status=r.upload_status,
            error=dto.FileError(code=r.error, message=r.error) if r.error else None,
            **({"parse_status": r.parse_status} if view else {}),
        )

    def create(self, token, store, body, key, csrf):
        body = dto.DraftRequest.model_validate(body.model_dump())
        kd, fp, _ = self._request(key, body.model_dump(mode="json"))
        with auth_session(self.engine) as s:
            actor, _, _ = self.auth.authorize_in_session(
                s, token, store, ("import.create",), csrf=csrf or ""
            )
            op = "POST:stores/imports"
            old = self._old(s, actor, store, op, kd, fp)
            if old:
                return dto.Draft.model_validate(old)
            b = ImportBatch(
                id=uuid4(),
                store_id=store,
                actor_id=actor.user_id,
                data_date=body.data_date,
                status="draft",
                revision=rev(),
                file_set_version=rev(),
                sealed=False,
                created_at=self.clock(),
                mapping_revision=rev(),
            )
            s.add(b)
            s.flush()
            result = self._draft(b, [])
            self._save(s, actor, store, op, kd, fp, result)
            self._audit(
                s, actor, store, "IMPORT_DRAFT_CREATED", result.model_dump(mode="json")
            )
            s.commit()
        return result

    def upload(self, token, ident, entries, key, csrf):
        if (
            not entries
            or len(entries) > 20
            or len({e[0] for e in entries}) != len(entries)
        ):
            raise AuthError("RESOURCE_LIMIT_EXCEEDED", 413)
        kd, fp, _ = self._request(
            key,
            [(str(i), n, len(v), hashlib.sha256(v).hexdigest()) for i, n, v in entries],
        )
        with auth_session(self.engine) as s:
            b = self._batch(s, ident, False)
            actor, _, _ = self._authority(s, token, b, "import.upload", csrf or "")
            b = self._batch(s, ident)
            op = "POST:imports/" + str(ident) + "/files"
            old = self._old(s, actor, b.store_id, op, kd, fp)
            if old:
                return dto.UploadResult.model_validate(old)
            if b.sealed:
                raise AuthError("IMPORT_STATE_CONFLICT", 409)
            existing = self._files(s, b)
            items = []
            warnings = []
            count = sum(f.upload_status == "uploaded" for f in existing)
            size = sum(f.size for f in existing if f.upload_status == "uploaded")
            for client_id, name, content in entries:
                oldfile = next(
                    (f for f in existing if f.client_file_id == client_id), None
                )
                filename = name.rsplit("/", 1)[-1].rsplit("\\", 1)[-1][:255]
                raw_hash = "sha256:" + hashlib.sha256(content).hexdigest()
                if oldfile:
                    if oldfile.raw_digest != raw_hash or oldfile.filename != filename:
                        raise AuthError("IDEMPOTENCY_KEY_REUSED", 409)
                    items.append(self._file(oldfile, False))
                    continue
                fmt = (
                    "xlsx"
                    if filename.lower().endswith(".xlsx") and content.startswith(b"PK")
                    else (
                        "csv"
                        if filename.lower().endswith(".csv")
                        and not content.startswith(b"PK")
                        and b"\0" not in content[:8192]
                        else "unknown"
                    )
                )
                error = None
                if (
                    len(content) > 20 * 1024 * 1024
                    or count >= 20
                    or size + len(content) > 100 * 1024 * 1024
                ):
                    error = "RESOURCE_LIMIT_EXCEEDED"
                elif fmt == "unknown":
                    error = "INVALID_FILE_TYPE"
                elif not content:
                    error = "EMPTY_FILE"
                status = "rejected" if error else "uploaded"
                if not error:
                    blob = s.get(ImportBlob, (b.store_id, raw_hash))
                    if blob is None:
                        s.add(
                            ImportBlob(
                                store_id=b.store_id, digest=raw_hash, content=content
                            )
                        )
                        s.flush()
                    else:
                        if blob.content != content:
                            raise AuthError("SOURCE_INTEGRITY_ERROR", 409)
                        warnings.append(notice("DUPLICATE_CONTENT", None, True))
                r = ImportFile(
                    id=uuid4(),
                    import_id=b.id,
                    store_id=b.store_id,
                    client_file_id=client_id,
                    filename=filename,
                    format=fmt,
                    digest=None if error else raw_hash,
                    raw_digest=raw_hash,
                    size=len(content),
                    upload_status=status,
                    error=error,
                    parse_status="not_started",
                )
                s.add(r)
                existing.append(r)
                items.append(self._file(r, False))
                if not error:
                    count += 1
                    size += len(content)
                    b.imported_at = b.imported_at or self.clock()
            b.revision = rev()
            b.file_set_version = rev()
            b.status = "uploaded" if count else "draft"
            result = dto.UploadResult(
                import_id=b.id,
                import_revision=b.revision,
                file_set_version=b.file_set_version,
                items=tuple(items),
                warnings=tuple(warnings),
            )
            self._save(s, actor, b.store_id, op, kd, fp, result)
            self._audit(
                s,
                actor,
                b.store_id,
                "IMPORT_FILES_RECEIVED",
                result.model_dump(mode="json"),
            )
            s.commit()
        return result

    def _accept(self, s, b, actor, operation, input_json):
        if b.active_job_id:
            raise AuthError("IMPORT_STATE_CONFLICT", 409)
        job = ImportJob(
            id=uuid4(),
            import_id=b.id,
            store_id=b.store_id,
            actor_id=actor.user_id,
            session_digest=actor.session_digest,
            operation=operation,
            status="queued",
            stage="queued",
            created_at=self.clock(),
            input_json=input_json,
        )
        s.add(job)
        b.active_job_id = job.id
        b.revision = rev()
        return job

    def analyze(self, token, ident, body, key, match, csrf):
        body = dto.AnalyzeRequest.model_validate(body.model_dump())
        kd, fp, m = self._request(key, body.model_dump(mode="json"), match, True)
        with auth_session(self.engine) as s:
            b = self._batch(s, ident, False)
            actor, _, _ = self._authority(s, token, b, "import.analyze", csrf or "")
            b = self._batch(s, ident)
            op = "POST:imports/" + str(ident) + "/analyze"
            old = self._old(s, actor, b.store_id, op, kd, fp)
            if old:
                return dto.AnalysisAccepted.model_validate(old)
            if b.revision != m:
                raise AuthError("IMPORT_REVISION_CONFLICT", 412)
            files = self._files(s, b)
            if not any(f.upload_status == "uploaded" for f in files):
                raise AuthError("NO_UPLOADED_FILES", 409)
            if (
                b.status not in {"uploaded", "failed"}
                or b.sealed
                and b.analysis_json is not None
            ):
                raise AuthError("IMPORT_STATE_CONFLICT", 409)
            if (
                body.file_set_version != b.file_set_version
                or set(body.accepted_file_ids)
                != {f.id for f in files if f.upload_status == "uploaded"}
                or set(body.acknowledged_rejected_client_file_ids)
                != {f.client_file_id for f in files if f.upload_status == "rejected"}
            ):
                raise AuthError("INVALID_IMPORT_CONFIGURATION", 422)
            b.sealed = True
            b.analysis_id = uuid4()
            b.status = "analyzing"
            job = self._accept(
                s,
                b,
                actor,
                "import_analyze",
                dict(
                    analysis_id=str(b.analysis_id),
                    file_set_version=b.file_set_version,
                    file_ids=[str(x) for x in body.accepted_file_ids],
                ),
            )
            result = dto.AnalysisAccepted(
                import_id=b.id,
                analysis_id=b.analysis_id,
                job_id=job.id,
                status="analyzing",
                import_revision=b.revision,
            )
            self._save(s, actor, b.store_id, op, kd, fp, result)
            s.commit()
        return result

    def _issues(self, b):
        return [dto.MappingIssue.model_validate(i) for i in b.analysis_json["issues"]]

    def _sheets(self, b):
        return [dto.SheetInfo.model_validate(i) for i in b.analysis_json["sheets"]]

    def _progress(self, issues):
        n = sum(i.status in {"auto_mapped", "resolved"} for i in issues)
        return dto.Progress(
            total_fields=len(issues), completed_fields=n, unresolved=len(issues) - n
        )

    def _bindings(self, s, b):
        result = []
        contexts = {i.sheet_id: i for i in self._issues(b) if i.issue_type == "source_context"}
        for item in b.analysis_json["bindings"]:
            ref = dto.BindingRef.model_validate(item)
            v = s.get(ImportProfileVersion, (ref.profile_id, ref.version))
            if v is None or v.retired:
                raise AuthError("MAPPING_VERSION_RETIRED", 409)
            if v.store_id != b.store_id:
                raise AuthError("RESOURCE_NOT_FOUND", 404)
            if content_digest(v.spec_json) != ref.content_digest:
                raise AuthError("SOURCE_IDENTITY_CONFLICT", 409)
            declared = contexts.get(ref.sheet_id)
            if (declared is None or declared.resolved_by is None or declared.resolution is None
                    or not isinstance(declared.resolution.resolution, dto.SourceContext)):
                raise AuthError("SOURCE_CONTEXT_REQUIRED", 409)
            context = declared.resolution.resolution
            if context.source_system_key != v.source_system_key or context.report_type != v.report_type:
                raise AuthError("SOURCE_CONTEXT_CONFLICT", 409)
            result.append((ref, dto.ProfileSpec.model_validate(v.spec_json, context={"retained_evidence": True})))
        return result

    def _summary(self, s, b, details=True):
        if b.analysis_json is None:
            raise AuthError("ANALYSIS_NOT_READY", 409)
        issues = self._issues(b)
        sheets = self._sheets(b)
        props = []
        blockers = []
        for sheet in sheets:
            p = s.get(ImportProfile, sheet.profile_id) if sheet.profile_id else None
            if p and p.import_id == b.id:
                spec = p.proposal_json.get("spec")
                missing = p.proposal_json.get("missing_fields", [])
                props.append(
                    dto.ProfileProposal(
                        profile_id=p.id,
                        proposal_revision=p.proposal_revision,
                        lifecycle_revision=p.lifecycle_revision,
                        active_version=p.active_version,
                        spec=(
                            dto.ProfileSpec.model_validate(spec)
                            if spec and details
                            else None
                        ),
                        missing_fields=tuple(missing),
                    )
                )
        if self._progress(issues).unresolved:
            blockers.append(notice("UNRESOLVED_REQUIRED_FIELDS", None))
        bindings = []
        inspected = []
        try:
            pairs = self._bindings(s, b)
            bindings = [ref for ref, _ in pairs]
            for ref, spec in pairs:
                sheet = next(sh for sh in sheets if sh.sheet_id == ref.sheet_id)
                supplied = {v.target_field for v in sheet.import_values}
                if any(
                    r.scope == "IMPORT_VALUE" and r.target_field not in supplied
                    for r in spec.shared_field_bindings
                ):
                    blockers.append(
                        notice(
                            "MISSING_IMPORT_VALUE",
                            dto.SourceLocation(
                                file_id=sheet.file_id, sheet_id=sheet.sheet_id
                            ),
                        )
                    )
            if details:
                inspected = [
                    dto.InspectedProfile(binding=ref, spec=spec) for ref, spec in pairs
                ]
        except AuthError as error:
            blockers.append(notice(error.code, None))
        active_sheets = [sh for sh in sheets if not sh.ignored]
        if len(bindings) != len(active_sheets):
            blockers.append(notice("OWNER_MAPPING_APPROVAL_REQUIRED", None))
        if not active_sheets or not any(sh.row_count for sh in active_sheets):
            blockers.append(notice("NO_DATA_ROWS", None))
        contexts = s.scalars(
            select(ImportSourceContext)
            .where(ImportSourceContext.store_id == b.store_id)
            .order_by(
                ImportSourceContext.source_system_key, ImportSourceContext.report_type
            )
        ).all()
        choices = tuple(
            dto.ApprovedContext(
                source_system_key=c.source_system_key,
                report_type=c.report_type,
                evidence_reference=c.evidence_reference,
                approved_by=c.approved_by,
                approved_at=c.approved_at,
            )
            for c in contexts
        )
        return dto.MappingSummary(
            import_id=b.id,
            analysis_id=b.analysis_id,
            mapping_revision=b.mapping_revision,
            progress=self._progress(issues),
            files=tuple(self._file(f) for f in self._files(s, b)),
            sheets=tuple(sheets),
            binding_refs=tuple(bindings),
            profile_proposals=tuple(props),
            can_preview=not blockers and not b.analysis_json.get("completion"),
            blockers=tuple(blockers),
            allowed_actions=(() if b.analysis_json.get("completion") else
                             ("preview",) if not blockers else ("resolve_mapping",)),
            approved_contexts=choices,
            approved_profiles=tuple(inspected),
            warnings=tuple(
                dto.Notice.model_validate(n)
                for n in b.analysis_json.get("warnings", [])
            ),
        )

    def summary(self, token, ident, details=False, clean=False, file_id=None, sheet_id=None, review=True, status=None, origin=None):
        with auth_session(self.engine) as s:
            b = self._batch(s, ident, False)
            _, _, permissions = self._authority(
                s, token, b, "mapping.read", sensitive=True
            )
            result = self._summary(s, b, details)
            from app.application.import_read_projection import mapping_selection
            scope=dto.MappingCounterScope(file_id=file_id,sheet_id=sheet_id,review_only=review,status=status,origin=origin)
            _,counters=mapping_selection(self._issues(b),self._sheets(b),scope,file_ids=[f.file_id for f in result.files])
            result=result.model_copy(update={'counter_scope':scope,'counters':counters})
            result = result.model_copy(
                update={
                    "allowed_actions": self._allowed(
                        result.allowed_actions, permissions
                    ),
                    "can_preview": result.can_preview
                    and "import.preview" in permissions,
                }
            )
            if not clean:
                clean_ids = {
                    ref.sheet_id
                    for ref in result.binding_refs
                    if not any(
                        n.source_location and n.source_location.sheet_id == ref.sheet_id
                        for n in result.blockers
                    )
                    and all(
                        i.status == "auto_mapped"
                        for i in self._issues(b)
                        if i.sheet_id == ref.sheet_id
                    )
                }
                result = result.model_copy(
                    update={
                        "sheets": tuple(
                            sh for sh in result.sheets if sh.sheet_id not in clean_ids
                        )
                    }
                )
            s.commit()
            return result

    def _page(self, items, token, actor, summary, binding, limit, cursor, *, mapping_snapshot=False):
        if type(limit) is not int or not 1 <= limit <= 100:
            raise AuthError("INVALID_FILTER", 422)
        bound = [
            str(actor.user_id),
            str(summary.store_id),
            summary.authorization_version,
            binding,
            limit,
        ]
        fingerprint = content_digest([i.model_dump(mode="json") for i in items])
        offset = 0
        if cursor:
            try:
                payload, signature = cursor.split(".")
                if not hmac.compare_digest(
                    signature, self.auth.cursor_signer.sign(token, "imports", payload)
                ):
                    raise ValueError()
                value = json.loads(base64.urlsafe_b64decode(payload))
                if value["binding"] != bound:
                    if mapping_snapshot:
                        old=value['binding']
                        # Filters are syntax; revisions/current authority are snapshot identity.
                        if (old[:2]==bound[:2] and old[4:]==bound[4:]
                            and old[3][:1]+old[3][2:]==bound[3][:1]+bound[3][2:]):
                            raise AuthError('SNAPSHOT_NOT_AVAILABLE',409)
                    raise ValueError()
                if value["fingerprint"] != fingerprint:
                    raise AuthError("SNAPSHOT_NOT_AVAILABLE" if mapping_snapshot else "LIST_VERSION_CHANGED", 409)
                offset = value["offset"]
                if type(offset) is not int or not 0 < offset < len(items):
                    raise ValueError()
            except (ValueError, TypeError, KeyError, IndexError):
                raise AuthError("INVALID_CURSOR", 422) from None
        next_cursor = None
        if offset + limit < len(items):
            payload = base64.urlsafe_b64encode(
                json.dumps(
                    dict(binding=bound, fingerprint=fingerprint, offset=offset + limit),
                    separators=(",", ":"),
                ).encode()
            ).decode()
            next_cursor = (
                payload + "." + self.auth.cursor_signer.sign(token, "imports", payload)
            )
        return tuple(items[offset : offset + limit]), Pagination(
            limit=limit, next_cursor=next_cursor, total_count=len(items)
        )

    def mappings(
        self,
        token,
        ident,
        sheet_id=None,
        review=True,
        status=None,
        details=False,
        limit=50,
        cursor=None,
        file_id=None,
        origin=None,
        snapshot_id=None,
    ):
        with auth_session(self.engine) as s:
            b = self._batch(s, ident, False)
            actor, summary, _ = self._authority(
                s, token, b, "mapping.read", sensitive=True
            )
            if b.analysis_json is None:
                raise AuthError("ANALYSIS_NOT_READY", 409)
            issues = self._issues(b)
            from app.application.import_read_projection import mapping_selection
            if snapshot_id is not None and snapshot_id!=b.mapping_revision:raise AuthError('SNAPSHOT_NOT_AVAILABLE',409)
            scope=dto.MappingCounterScope(file_id=file_id,sheet_id=sheet_id,review_only=review,status=status,origin=origin)
            items,counters=mapping_selection(issues,self._sheets(b),scope,file_ids=[f.id for f in self._files(s,b)])
            page, pagination = self._page(
                items,
                token,
                actor,
                summary,
                [str(b.id), b.mapping_revision, str(sheet_id), review, status, details,str(file_id),origin],
                limit,
                cursor,
                mapping_snapshot=True,
            )
            s.commit()
            return (
                dto.MappingList(items=page, counts=self._progress(issues),mapping_revision=b.mapping_revision,counter_scope=scope,counters=counters),
                pagination,
            )

    def field_options(self, token, ident, sheet_id, mapping_id=None):
        with auth_session(self.engine) as s:
            b = self._batch(s, ident, False)
            self._authority(s, token, b, "mapping.read", sensitive=True)
            if b.analysis_json is None:
                raise AuthError("ANALYSIS_NOT_READY", 409)
            sheet = next(
                (sh for sh in self._sheets(b) if sh.sheet_id == sheet_id), None
            )
            if (
                not sheet
                or mapping_id
                and not any(
                    i.mapping_id == mapping_id and i.sheet_id == sheet_id
                    for i in self._issues(b)
                )
            ):
                raise AuthError("RESOURCE_NOT_FOUND", 404)
            own = [i for i in self._issues(b) if i.sheet_id == sheet_id]
            used = {
                i.target_field
                for i in own
                if i.mapping_id != mapping_id and i.target_field
            }
            schemas = {i.target_field.split(".")[0] for i in own if i.target_field}
            schema = sheet.selected_type or (
                next(iter(schemas)) if len(schemas) == 1 else None
            )
            choices = tuple(
                (
                    o.model_copy(
                        update={
                            "available": False,
                            "reason_code": "TARGET_ALREADY_BOUND",
                        }
                    )
                    if o.key in used
                    else o
                )
                for o in options(schema)
            )
            result = dto.FieldOptions(
                schema=schema,
                schema_version="import_schema/1",
                schema_context_id=sheet_id,
                mapping_revision=b.mapping_revision,
                options=choices,
                schemas=descriptors(),
            )
            s.commit()
            return result

    def _select_sheet(self, s, b, actor, issue, body, op, kd, fp):
        if issue.issue_type != "classification":
            raise AuthError("INVALID_MAPPING_TARGET", 422)
        choice = body.resolution
        sheets = self._sheets(b)
        oldsheet = next(sh for sh in sheets if sh.sheet_id == issue.sheet_id)
        oldspec = None
        oldpin = next(
            (
                ref
                for ref in b.analysis_json["bindings"]
                if ref["sheet_id"] == str(issue.sheet_id)
            ),
            None,
        )
        if oldpin:
            version = s.get(
                ImportProfileVersion, (UUID(oldpin["profile_id"]), oldpin["version"])
            )
            if (
                version is None
                or version.store_id != b.store_id
                or content_digest(version.spec_json) != oldpin["content_digest"]
            ):
                raise AuthError("SOURCE_INTEGRITY_ERROR", 409)
            oldspec = dto.ProfileSpec.model_validate(version.spec_json, context={"retained_evidence": True})
        previous = (
            s.get(ImportProfile, oldsheet.profile_id) if oldsheet.profile_id else None
        )
        pdata = (
            dict(previous.proposal_json)
            if previous
            and previous.import_id == b.id
            and oldsheet.selected_type == choice.sheet_type
            else {}
        )
        same_type = oldsheet.selected_type == choice.sheet_type and not oldsheet.ignored
        sheet = oldsheet.model_copy(
            update={
                "selected_type": choice.sheet_type,
                "ignored": choice.ignored,
                "ignore_reason": choice.reason if choice.ignored else None,
                "classification_origin": "MANUAL",
                "confidence": None,
                "profile_id": None,
                "shared_field_bindings": tuple(
                    r
                    for r in oldsheet.shared_field_bindings
                    if choice.sheet_type
                    and r.target_field.startswith(choice.sheet_type + ".")
                ),
                "import_values": tuple(
                    v
                    for v in oldsheet.import_values
                    if choice.sheet_type
                    and v.target_field.startswith(choice.sheet_type + ".")
                ),
            }
        )
        allowed = {o.key for o in options(choice.sheet_type) if o.available}
        issues = []
        for item in self._issues(b):
            if item.sheet_id != issue.sheet_id:
                issues.append(item)
                continue
            if item.issue_type in {"identity", "conversion"} and (
                not same_type or choice.ignored
            ):
                continue
            update = {"profile_ref": None, "resolution_origin": "USER_PROPOSAL"}
            if choice.ignored:
                update.update(
                    status="resolved",
                    target_field=None,
                    ignored=True,
                    suggestion_origin="MANUAL",
                    confidence=None,
                )
                if item.issue_type == "classification":
                    update["resolution"] = body
            elif item.issue_type == "classification":
                update.update(
                    status="resolved",
                    resolution=body,
                    ignored=False,
                    suggestion_origin="MANUAL",
                    confidence=None,
                )
            elif item.issue_type == "source_context" and oldspec is not None:
                update.update(
                    status="resolved",
                    resolution=dto.ResolveRequest(
                        resolution=dto.SourceContext(
                            kind="source_context",
                            source_system_key=oldspec.scope.source_system_key,
                            report_type=oldspec.scope.report_type,
                            evidence_reference=oldspec.source_provenance.evidence_references[
                                0
                            ],
                            sales_semantics=(
                                oldspec.sales_semantics
                                if choice.sheet_type == "sales"
                                else None
                            ),
                            inventory_semantics=(
                                oldspec.inventory_semantics
                                if choice.sheet_type == "inventory_count"
                                else None
                            ),
                        )
                    ),
                )
            elif item.issue_type == "column":
                if item.ignored and not oldsheet.ignored:
                    update.update(status="resolved", target_field=None, ignored=True)
                elif oldsheet.ignored or item.target_field not in allowed:
                    update.update(
                        target_field=None,
                        status="unmatched",
                        ignored=False,
                        resolution=None,
                        suggested_target_field=None,
                        suggestion_origin="NONE",
                        confidence=None,
                    )
                else:
                    update.update(
                        status=(
                            "resolved" if item.status == "auto_mapped" else item.status
                        )
                    )
            issues.append(item.model_copy(update=update))
        p = None
        if not choice.ignored:
            same = oldspec if oldspec and oldspec.schema == choice.sheet_type else None
            spec, missing = build_spec(
                sheet,
                issues,
                actor.user_id,
                identities=tuple(
                    dto.IdentityRule.model_validate(r)
                    for r in pdata.get("identities", ())
                )
                or (same.identity_rules if same else ()),
                entities=tuple(
                    dto.EntityReservation.model_validate(r)
                    for r in pdata.get("entities", ())
                )
                or (same.entity_proposals if same else ()),
                conversions=tuple(
                    dto.Conversion.model_validate(r)
                    for r in pdata.get("conversions", ())
                )
                or (same.conversions if same else ()),
                prior_normalizations=same.normalizations if same else (),
                prior_spec=same,
            )
            p = ImportProfile(
                id=uuid4(),
                store_id=b.store_id,
                import_id=b.id,
                sheet_id=sheet.sheet_id,
                lifecycle_revision=rev(),
                proposal_revision=rev(),
                proposal_json={
                    **pdata,
                    "spec": spec.model_dump(mode="json") if spec else None,
                    "missing_fields": missing,
                    "base_spec": same.model_dump(mode="json") if same else None,
                },
                rejected=False,
            )
            s.add(p)
            sheet = sheet.model_copy(update={"profile_id": p.id})
        sheets = [sheet if sh.sheet_id == sheet.sheet_id else sh for sh in sheets]
        analysis = dict(b.analysis_json)
        analysis.update(
            sheets=[sh.model_dump(mode="json") for sh in sheets],
            issues=[i.model_dump(mode="json") for i in issues],
            bindings=[
                r for r in analysis["bindings"] if r["sheet_id"] != str(sheet.sheet_id)
            ],
        )
        analysis.pop("confirmation", None)
        analysis["schemas"] = sorted(
            {i.target_field.split(".")[0] for i in issues if i.target_field}
        )
        b.analysis_json = analysis
        b.mapping_revision = rev()
        b.revision = rev()
        b.status = "review_required"
        result = dto.MappingUpdated(
            mapping_id=issue.mapping_id,
            status="resolved",
            mapping_revision=b.mapping_revision,
            progress=self._progress(issues),
            sheets=tuple(sheets),
            proposal_revision=p.proposal_revision if p else None,
            approval_required=not choice.ignored,
        )
        self._save(s, actor, b.store_id, op, kd, fp, result)
        self._audit(
            s,
            actor,
            b.store_id,
            "SHEET_TYPE_REVIEWED",
            dict(
                import_id=str(b.id),
                sheet_id=str(sheet.sheet_id),
                resolution=body.model_dump(mode="json"),
            ),
        )
        s.commit()
        return result

    def resolve(self, token, ident, mapping_id, body, key, match, csrf):
        body = type(body).model_validate(body.model_dump())
        kd, fp, m = self._request(key, body.model_dump(mode="json"), match, True)
        with auth_session(self.engine) as s:
            b = self._batch(s, ident, False)
            actor, authorization, _ = self._authority(
                s, token, b, "mapping.propose", csrf or "", True
            )
            b = self._batch(s, ident)
            if (isinstance(body, dto.ResolveRequest) and isinstance(body.resolution, dto.SheetTypeResolution)
                and body.resolution.ignored and authorization.role == "STAFF" and b.actor_id != actor.user_id):
                raise AuthError("PERMISSION_DENIED")
            op = "PATCH:imports/" + str(ident) + "/mappings/" + str(mapping_id)
            old = self._old(s, actor, b.store_id, op, kd, fp)
            if old:
                return dto.MappingUpdated.model_validate(old)
            if b.mapping_revision != m:
                raise AuthError("MAPPING_REVISION_CONFLICT", 412)
            if (b.analysis_json or {}).get("completion"):
                raise AuthError("IMPORT_STATE_CONFLICT", 409)
            if b.active_job_id:
                raise AuthError("IMPORT_STATE_CONFLICT", 409)
            issues = self._issues(b)
            sheets = self._sheets(b)
            issue = next((i for i in issues if i.mapping_id == mapping_id), None)
            if issue is None:
                raise AuthError("RESOURCE_NOT_FOUND", 404)
            if isinstance(body, dto.ResolveRequest) and isinstance(
                body.resolution, dto.SharedValueResolution
            ):
                return self._resolve_shared(s, b, actor, issue, body, op, kd, fp)
            if isinstance(body, dto.ResolveRequest) and isinstance(
                body.resolution, dto.SheetTypeResolution
            ):
                return self._select_sheet(s, b, actor, issue, body, op, kd, fp)
            if issue.status == "auto_mapped" and issue.issue_type not in {
                "source_context",
                "column",
            }:
                raise AuthError("IMPORT_STATE_CONFLICT", 409)
            sheet = next(sh for sh in sheets if sh.sheet_id == issue.sheet_id)
            p = s.get(ImportProfile, sheet.profile_id) if sheet.profile_id else None
            if isinstance(body, dto.ResolveRequest) and isinstance(
                body.resolution, dto.SourceContext
            ):
                if issue.issue_type != "source_context":
                    raise AuthError("INVALID_MAPPING_TARGET", 422)
                context = body.resolution
                rawsheet = next(
                    raw
                    for raw in b.analysis_json["sources"]
                    if raw["sheet_id"] == str(sheet.sheet_id)
                )
                if source_context_conflicts(sheet, rawsheet, context):
                    raise AuthError("SOURCE_CONTEXT_CONFLICT", 409)
                candidates = s.scalars(
                    select(ImportProfileVersion)
                    .join(
                        ImportProfile,
                        ImportProfile.id == ImportProfileVersion.profile_id,
                    )
                    .where(
                        ImportProfileVersion.store_id == b.store_id,
                        ImportProfileVersion.schema_signature == sheet.schema_signature,
                        ImportProfileVersion.source_system_key
                        == context.source_system_key,
                        ImportProfileVersion.report_type == context.report_type,
                        ImportProfileVersion.retired.is_(False),
                        ImportProfile.active_version == ImportProfileVersion.version,
                    )
                ).all()
                if sheet.classification_origin == "MANUAL":
                    candidates = [
                        v
                        for v in candidates
                        if v.spec_json["schema"] == sheet.selected_type
                    ]
                candidates = [v for v in candidates
                    if dto.ProfileSpec.model_validate(v.spec_json, context={"retained_evidence": True}).supports_recipe_basis()
                    and dto.ProfileSpec.model_validate(v.spec_json, context={"retained_evidence": True}).supports_supplier_basis()]
                if len(candidates) == 1:
                    existing_spec = dto.ProfileSpec.model_validate(
                        candidates[0].spec_json
                    )
                    declared = {
                        key: value
                        for key, value in context.model_dump(mode="json").items()
                        if key
                        not in {
                            "kind",
                            "source_system_key",
                            "report_type",
                            "evidence_reference",
                            "missing_stockout",
                        }
                        and value not in (None, (), [])
                    }
                    expected = existing_spec.model_dump(mode="json")
                    expected['stockout_aliases'] = next((json.loads(n.parameter)
                        for n in existing_spec.normalizations if n.kind == 'stockout_alias'), [])
                    expected.update(
                        decimal_locale=next(
                            (
                                r.parameter
                                for r in existing_spec.normalizations
                                if r.kind == "decimal_locale"
                            ),
                            None,
                        ),
                        date_format=next(
                            (
                                r.parameter
                                for r in existing_spec.normalizations
                                if r.kind == "date_format"
                            ),
                            None,
                        ),
                        pack_cost_basis=(
                            "PER_SOURCE_UNIT"
                            if any(
                                r.rule_id == "declared_pack_pricing_basis"
                                for r in existing_spec.normalizations
                            )
                            else "PER_PACK"
                        ),
                    )
                    if expected.get('date_format') in {'EXCEL_1900', 'EXCEL_1904'}:
                        expected['date_format'] = 'EXCEL_SERIAL'
                    if any(
                        value != expected.get(key) for key, value in declared.items()
                    ):
                        candidates = []
                if len(candidates) > 1:
                    raise AuthError("PROFILE_MATCH_AMBIGUOUS", 409)
                scoped_versions = s.scalars(
                    select(ImportProfileVersion).join(
                        ImportProfile, ImportProfile.id == ImportProfileVersion.profile_id
                    ).where(
                        ImportProfileVersion.store_id == b.store_id,
                        ImportProfileVersion.source_system_key == context.source_system_key,
                        ImportProfileVersion.report_type == context.report_type,
                        ImportProfileVersion.retired.is_(False),
                        ImportProfile.active_version == ImportProfileVersion.version,
                    )
                ).all()
                if scoped_versions and not candidates:
                    analysis = dict(b.analysis_json)
                    location = dto.SourceLocation(file_id=sheet.file_id, sheet_id=sheet.sheet_id)
                    warning = notice("PROFILE_STRUCTURE_OR_SEMANTICS_DRIFT", location, True)
                    retained = [n for n in analysis.get("warnings", [])
                                if not (n["code"] == warning.code and n.get("source_location") == location.model_dump(mode="json"))]
                    analysis["warnings"] = retained + [warning.model_dump(mode="json")]
                    b.analysis_json = analysis
                if (
                    len(candidates) == 1
                    and issue.issue_type == "source_context"
                    and (p is None or p.import_id != b.id or (
                        # A classification/column review before declaring source
                        # is not itself a reusable-spec change. Keep genuine
                        # draft edits on the approval path.
                        p.proposal_json.get("spec") is None
                        and p.proposal_json.get("base_spec") is None
                        and not any(p.proposal_json.get(key) for key in ("identities", "entities", "conversions"))
                        and (not sheet.shared_field_bindings or sheet.shared_field_bindings == existing_spec.shared_field_bindings)
                        and sheet.selected_type == existing_spec.schema
                        and all(any(f.source_column_index == i.source_location.source_column_index
                            and f.target_field == i.target_field and f.ignored == i.ignored
                            for f in existing_spec.field_bindings)
                            for i in issues if i.sheet_id == sheet.sheet_id and i.issue_type == "column"
                            and i.status == "resolved")
                    ))
                ):
                    v = candidates[0]
                    spec = dto.ProfileSpec.model_validate(v.spec_json, context={"retained_evidence": True})
                    if (
                        context.sales_semantics is not None
                        and context.sales_semantics != spec.sales_semantics
                        or context.inventory_semantics is not None
                        and context.inventory_semantics != spec.inventory_semantics
                    ):
                        raise AuthError("SOURCE_IDENTITY_CONFLICT", 409)
                    for kind, param in (
                        ("decimal_locale", context.decimal_locale),
                        ("date_format", context.date_format),
                    ):
                        if param is not None and not any(
                            n.kind == kind and (n.parameter == param or kind == 'date_format'
                                and param == 'EXCEL_SERIAL' and n.parameter == 'EXCEL_' + (sheet.excel_date_system or ''))
                            for n in spec.normalizations
                        ):
                            raise AuthError("SOURCE_IDENTITY_CONFLICT", 409)
                    from app.models import Product, Ingredient, InventoryLot, Supplier
                    snapshot = {}
                    for model in (Product, Ingredient, InventoryLot, Supplier):
                        records = s.scalars(select(model).where(model.store_id == b.store_id).limit(100001)).all()
                        if len(records) > 100000:
                            raise AuthError("RESOURCE_LIMIT_EXCEEDED", 413)
                        snapshot[model.__tablename__] = [{"id": str(record.id),
                            "base_unit": getattr(record, "base_unit", None),
                            "selling_unit": getattr(record, "selling_unit", None)} for record in records]
                    # Re-evaluate row identities against this approved spec. New
                    # tokens remain issues; canonical IDs/approved aliases need no
                    # draft or profile approval merely because rows are new.
                    issues = [i for i in issues if not (i.sheet_id == sheet.sheet_id
                        and i.issue_type == "identity")]
                    fresh_identities = identity_issues([sheet], issues,
                        b.analysis_json["sources"], snapshot, {str(sheet.sheet_id): spec})
                    ref = dto.BindingRef(
                        sheet_id=sheet.sheet_id,
                        profile_id=v.profile_id,
                        version=v.version,
                        content_digest=v.content_digest,
                    )
                    sheets = [
                        (
                            sh.model_copy(
                                update={
                                    "profile_id": v.profile_id,
                                    "selected_type": spec.schema,
                                    "classification_origin": "REUSED",
                                    "confidence": None,
                                    "shared_field_bindings": spec.shared_field_bindings,
                                    "import_values": (),
                                }
                            )
                            if sh.sheet_id == sheet.sheet_id
                            else sh
                        )
                        for sh in sheets
                    ]
                    issues = [
                        (
                            i.model_copy(
                                update={
                                    "status": "auto_mapped",
                                    "resolution_origin": "APPROVED_PROFILE",
                                    "suggestion_origin": "REUSED",
                                    "confidence": None,
                                    "ignored": any(
                                        f.ignored
                                        and f.source_column_index
                                        == i.source_location.source_column_index
                                        for f in spec.field_bindings
                                    ),
                                    "profile_ref": ref,
                                    "resolution": body if i.issue_type == "source_context" else i.resolution,
                                    "resolved_by": actor.user_id if i.issue_type == "source_context" else i.resolved_by,
                                    "target_field": next(
                                        (
                                            f.target_field
                                            for f in spec.field_bindings
                                            if f.source_column_index
                                            == i.source_location.source_column_index
                                        ),
                                        None,
                                    ),
                                }
                            )
                            if i.sheet_id == sheet.sheet_id
                            else i
                        )
                        for i in issues
                    ]
                    issues.extend(fresh_identities)
                    analysis = dict(b.analysis_json)
                    analysis["issues"] = [i.model_dump(mode="json") for i in issues]
                    analysis["sheets"] = [sh.model_dump(mode="json") for sh in sheets]
                    analysis["bindings"] = [
                        r
                        for r in analysis["bindings"]
                        if r["sheet_id"] != str(sheet.sheet_id)
                    ] + [ref.model_dump(mode="json")]
                    analysis["schemas"] = sorted(
                        {i.target_field.split(".")[0] for i in issues if i.target_field}
                    )
                    b.analysis_json = analysis
                    b.mapping_revision = rev()
                    b.revision = rev()
                    b.status = (
                        "ready_for_preview"
                        if len(analysis["bindings"]) == len(sheets) and not self._progress(issues).unresolved
                        else "review_required"
                    )
                    target = s.get(ImportProfile, v.profile_id)
                    result = dto.MappingUpdated(
                        mapping_id=mapping_id,
                        status="auto_mapped",
                        mapping_revision=b.mapping_revision,
                        progress=self._progress(issues),
                        sheets=tuple(sheets),
                        proposal_revision=target.proposal_revision,
                        approval_required=False,
                    )
                    self._save(s, actor, b.store_id, op, kd, fp, result)
                    self._audit(
                        s,
                        actor,
                        b.store_id,
                        "SOURCE_CONTEXT_SELECTED",
                        body.model_dump(mode="json"),
                    )
                    s.commit()
                    return result
            inherited = {}
            if (
                p
                and p.active_version
                and (
                    issue.status == "auto_mapped"
                    or isinstance(body, dto.ResolveRequest)
                    and isinstance(body.resolution, dto.SourceContext)
                )
            ):
                v = s.get(ImportProfileVersion, (p.id, p.active_version))
                if (
                    v is None
                    or v.store_id != b.store_id
                    or content_digest(v.spec_json) != v.content_digest
                ):
                    raise AuthError("SOURCE_INTEGRITY_ERROR", 409)
                inherited_spec = dto.ProfileSpec.model_validate(v.spec_json, context={"retained_evidence": True})
                inherited_context = dto.ResolveRequest(
                    resolution=dto.SourceContext(
                        kind="source_context",
                        source_system_key=inherited_spec.scope.source_system_key,
                        report_type=inherited_spec.scope.report_type,
                        evidence_reference=inherited_spec.source_provenance.evidence_references[
                            0
                        ],
                        sales_semantics=inherited_spec.sales_semantics,
                        inventory_semantics=inherited_spec.inventory_semantics,
                        planned_arrival_expiry_rule=inherited_spec.planned_arrival_expiry_rule,
                        term_period_amendments=inherited_spec.term_period_amendments,
                        fee_period_amendments=inherited_spec.fee_period_amendments,
                    )
                )
                declared_context = next((i.resolution for i in issues if
                    i.sheet_id == sheet.sheet_id and i.issue_type == "source_context"
                    and i.resolution and isinstance(i.resolution.resolution, dto.SourceContext)), None)
                if declared_context is not None:
                    inherited_context = declared_context
                inherited = {"spec": v.spec_json, "base_spec": v.spec_json}
                issues = [
                    (
                        i.model_copy(
                            update={
                                "status": "resolved",
                                "resolution_origin": "USER_PROPOSAL",
                                "profile_ref": None,
                                "resolution": (
                                    inherited_context
                                    if i.issue_type == "source_context"
                                    else i.resolution
                                ),
                            }
                        )
                        if i.sheet_id == sheet.sheet_id
                        else i
                    )
                    for i in issues
                ]
                issue = next(i for i in issues if i.mapping_id == mapping_id)
                if (
                    isinstance(body, dto.ResolveRequest)
                    and isinstance(body.resolution, dto.SourceContext)
                    and body.resolution.source_system_key == v.source_system_key
                    and body.resolution.report_type == v.report_type
                ):
                    p.import_id = b.id
                    p.sheet_id = sheet.sheet_id
                    p.proposal_json = inherited
                else:
                    p = None
            if p is None or p.import_id != b.id:
                p = ImportProfile(
                    id=uuid4(),
                    store_id=b.store_id,
                    import_id=b.id,
                    sheet_id=sheet.sheet_id,
                    lifecycle_revision=rev(),
                    proposal_revision=rev(),
                    proposal_json=inherited,
                    rejected=False,
                )
                s.add(p)
                s.flush()
                sheet = sheet.model_copy(update={"profile_id": p.id})
                sheets = [
                    sheet if sh.sheet_id == sheet.sheet_id else sh for sh in sheets
                ]
            if isinstance(body, dto.TargetRequest):
                if any(
                    r.target_field == body.target_field
                    for r in sheet.shared_field_bindings
                ):
                    sheet = sheet.model_copy(
                        update={
                            "shared_field_bindings": tuple(
                                r
                                for r in sheet.shared_field_bindings
                                if r.target_field != body.target_field
                            ),
                            "import_values": tuple(
                                v
                                for v in sheet.import_values
                                if v.target_field != body.target_field
                            ),
                        }
                    )
                    sheets = [
                        sheet if sh.sheet_id == sheet.sheet_id else sh for sh in sheets
                    ]
                if issue.issue_type != "column" or body.target_field not in {
                    o.key
                    for o in options(sheet.selected_type)
                    if o.available and o.support != "unsupported"
                }:
                    raise AuthError("INVALID_MAPPING_TARGET", 422)
                if any(
                    i.issue_type == "column"
                    and i.mapping_id != issue.mapping_id
                    and i.sheet_id == issue.sheet_id
                    and i.target_field == body.target_field
                    for i in issues
                ):
                    raise AuthError("DUPLICATE_MAPPING", 409)
                issue = issue.model_copy(
                    update={
                        "target_field": body.target_field,
                        "status": "resolved",
                        "resolution_origin": "USER_PROPOSAL",
                        "suggestion_origin": "MANUAL",
                        "confidence": None,
                        "ignored": False,
                        "resolution": None,
                    }
                )
            else:
                resolution = body.resolution
                if isinstance(resolution, dto.SourceContext):
                    if issue.issue_type != "source_context":
                        raise AuthError("INVALID_MAPPING_TARGET", 422)
                elif isinstance(resolution, dto.Ignored):
                    if issue.issue_type != "column":
                        raise AuthError("INVALID_MAPPING_TARGET", 422)
                    issue = issue.model_copy(
                        update={
                            "target_field": None,
                            "ignored": True,
                            "suggestion_origin": "MANUAL",
                            "confidence": None,
                        }
                    )
                elif isinstance(resolution, (dto.IdentityBinding, dto.NewEntity)):
                    if issue.issue_type != "identity":
                        raise AuthError("INVALID_MAPPING_TARGET", 422)
                    entity = issue.code.removeprefix("UNKNOWN_").lower()
                    data = dict(p.proposal_json)
                    prior_spec = data.get("spec") or data.get("base_spec") or {}
                    rules = data.get("identities", prior_spec.get("identity_rules", []))
                    entities = data.get(
                        "entities", prior_spec.get("entity_proposals", [])
                    )
                    if isinstance(resolution, dto.IdentityBinding):
                        from app.models import (
                            Product,
                            Ingredient,
                            InventoryLot,
                            Supplier,
                        )

                        model = {
                            "product": Product,
                            "ingredient": Ingredient,
                            "lot": InventoryLot,
                            "supplier": Supplier,
                        }[entity]
                        exists = (
                            s.scalar(
                                select(model).where(
                                    model.id == resolution.canonical_id,
                                    model.store_id == b.store_id,
                                )
                            )
                            is not None
                        )
                        if not exists:
                            candidates = s.scalars(
                                select(ImportProfile).where(
                                    ImportProfile.store_id == b.store_id,
                                    ImportProfile.import_id == b.id,
                                )
                            ).all()
                            reserved = any(
                                e["entity"] == entity
                                and e["reserved_canonical_id"]
                                == str(resolution.canonical_id)
                                for candidate in candidates
                                for e in candidate.proposal_json.get(
                                    "entities",
                                    (candidate.proposal_json.get("spec") or {}).get(
                                        "entity_proposals", []
                                    ),
                                )
                            )
                            if not reserved:
                                raise AuthError("RESOURCE_NOT_FOUND", 404)
                        rules = [
                            r
                            for r in rules
                            if not (
                                r["entity"] == entity
                                and r["source_token"] == issue.source_header
                            )
                        ] + [
                            dto.IdentityRule(
                                entity=entity,
                                source_token=issue.source_header,
                                canonical_id=resolution.canonical_id,
                                reference_state="existing" if exists else "reserved",
                            ).model_dump(mode="json")
                        ]
                    else:
                        if (
                            entity == "lot"
                            or resolution.entity != entity
                            or resolution.source_business_key != issue.source_header
                        ):
                            raise AuthError("INVALID_MAPPING_TARGET", 422)
                        prior = next(
                            (
                                e
                                for e in entities
                                if e["entity"] == entity
                                and e["source_business_key"] == issue.source_header
                            ),
                            None,
                        )
                        reservation = dto.EntityReservation(
                            proposal_id=(
                                UUID(prior["proposal_id"]) if prior else uuid4()
                            ),
                            entity=entity,
                            source_business_key=issue.source_header,
                            reserved_canonical_id=(
                                UUID(prior["reserved_canonical_id"])
                                if prior
                                else uuid4()
                            ),
                            metadata=resolution.metadata,
                            evidence_reference=resolution.evidence_reference,
                            approval_revision=rev(),
                        )
                        entities = [
                            e
                            for e in entities
                            if not (
                                e["entity"] == entity
                                and e["source_business_key"] == issue.source_header
                            )
                        ] + [reservation.model_dump(mode="json")]
                    data["identities"] = rules
                    data["entities"] = entities
                    p.proposal_json = data
                elif isinstance(resolution, dto.Conversion):
                    if issue.issue_type != "conversion":
                        raise AuthError("INVALID_MAPPING_TARGET", 422)
                    if (
                        resolution.from_unit != issue.source_header
                        or resolution.to_unit != issue.samples[-1]
                    ):
                        raise AuthError("INVALID_MAPPING_TARGET", 422)
                    data = dict(p.proposal_json)
                    data["conversions"] = data.get("conversions", []) + [
                        resolution.model_dump(mode="json")
                    ]
                    p.proposal_json = data
                else:
                    raise AuthError("INVALID_MAPPING_TARGET", 422)
                issue = issue.model_copy(
                    update={
                        "resolution": body,
                        "status": "resolved",
                        "resolution_origin": "USER_PROPOSAL",
                    }
                )
            issue = issue.model_copy(update={"resolved_by": actor.user_id})
            issues = [issue if i.mapping_id == mapping_id else i for i in issues]
            if isinstance(body, dto.TargetRequest):
                from app.models import Product, Ingredient, InventoryLot, Supplier

                snapshot = {}
                for model in (Product, Ingredient, InventoryLot, Supplier):
                    values = s.scalars(
                        select(model).where(model.store_id == b.store_id).limit(100001)
                    ).all()
                    if len(values) > 100000:
                        raise AuthError("RESOURCE_LIMIT_EXCEEDED", 413)
                    snapshot[model.__tablename__] = [
                        {
                            "id": str(v.id),
                            "base_unit": getattr(v, "base_unit", None),
                            "selling_unit": getattr(v, "selling_unit", None),
                        }
                        for v in values
                    ]
                extra = identity_issues(
                    sheets, issues, b.analysis_json["sources"], snapshot
                )
                existing = {
                    (i.sheet_id, i.code, i.source_header)
                    for i in issues
                    if i.issue_type in {"identity", "conversion"}
                }
                issues.extend(
                    i
                    for i in extra
                    if (i.sheet_id, i.code, i.source_header) not in existing
                )
            p.proposal_revision = rev()
            p.lifecycle_revision = rev()
            p.rejected = False
            pdata = p.proposal_json
            prior_spec = pdata.get("spec") or pdata.get("base_spec") or {}
            spec, missing = build_spec(
                sheet,
                issues,
                actor.user_id,
                tuple(
                    dto.IdentityRule.model_validate(r)
                    for r in pdata.get(
                        "identities", prior_spec.get("identity_rules", [])
                    )
                ),
                tuple(
                    dto.EntityReservation.model_validate(r)
                    for r in pdata.get(
                        "entities", prior_spec.get("entity_proposals", [])
                    )
                ),
                tuple(
                    dto.Conversion.model_validate(r)
                    for r in pdata.get("conversions", prior_spec.get("conversions", []))
                ),
                tuple(
                    dto.Normalization.model_validate(r)
                    for r in prior_spec.get("normalizations", [])
                ),
                prior_spec=(
                    dto.ProfileSpec.model_validate(prior_spec) if prior_spec else None
                ),
            )
            p.proposal_json = {
                **pdata,
                "spec": spec.model_dump(mode="json") if spec else None,
                "missing_fields": missing,
            }
            analysis = dict(b.analysis_json)
            analysis["issues"] = [i.model_dump(mode="json") for i in issues]
            analysis["sheets"] = [sh.model_dump(mode="json") for sh in sheets]
            analysis["bindings"] = [
                r for r in analysis["bindings"] if r["sheet_id"] != str(sheet.sheet_id)
            ]
            analysis["schemas"] = sorted(
                {i.target_field.split(".")[0] for i in issues if i.target_field}
            )
            b.analysis_json = analysis
            b.mapping_revision = rev()
            b.revision = rev()
            b.status = "review_required"
            result = dto.MappingUpdated(
                mapping_id=mapping_id,
                status=issue.status,
                mapping_revision=b.mapping_revision,
                progress=self._progress(issues),
                sheets=tuple(sheets),
                proposal_revision=p.proposal_revision,
                approval_required=True,
            )
            self._save(s, actor, b.store_id, op, kd, fp, result)
            self._audit(
                s,
                actor,
                b.store_id,
                "MAPPING_PROPOSED",
                dict(
                    mapping_id=str(mapping_id),
                    profile_id=str(p.id),
                    revision=p.proposal_revision,
                    resolution=body.model_dump(mode="json"),
                ),
            )
            s.commit()
        return result

    def _resolve_shared(self, s, b, actor, issue, body, op, kd, fp):
        from app.application.contracts.import_field_values import (
            ProfileConstant,
            ImportValueRequirement,
            ImportValue,
        )

        choice = body.resolution
        sheets = self._sheets(b)
        sheet = next(sh for sh in sheets if sh.sheet_id == issue.sheet_id)
        if (
            sheet.ignored
            or not sheet.selected_type
            or not choice.target_field.startswith(sheet.selected_type + ".")
        ):
            raise AuthError("INVALID_MAPPING_TARGET", 422)
        issues = self._issues(b)
        column = next(
            (
                i
                for i in issues
                if i.sheet_id == sheet.sheet_id
                and i.issue_type == "column"
                and i.target_field == choice.target_field
            ),
            None,
        )
        if column:
            if (
                choice.replace_source_column_index
                != column.source_location.source_column_index
                or not choice.acknowledgment
            ):
                raise AuthError("FIELD_SOURCE_CONFLICT", 409)
            replacement = column.model_copy(
                update={
                    "target_field": None,
                    "ignored": True,
                    "status": "resolved",
                    "suggestion_origin": "MANUAL",
                    "confidence": None,
                    "resolution": dto.ResolveRequest(
                        resolution=dto.Ignored(
                            kind="ignored_optional_field",
                            evidence_reference=choice.evidence_reference,
                        )
                    ),
                    "resolved_by": actor.user_id,
                }
            )
            issues = [
                replacement if i.mapping_id == column.mapping_id else i for i in issues
            ]
        elif choice.replace_source_column_index is not None:
            raise AuthError("FIELD_SOURCE_CONFLICT", 409)
        p = s.get(ImportProfile, sheet.profile_id) if sheet.profile_id else None
        data = dict(p.proposal_json) if p and p.import_id == b.id else {}
        raw = data.get("spec") or data.get("base_spec")
        existing = dto.ProfileSpec.model_validate(raw) if raw else None
        pin = next(
            (
                item
                for item in b.analysis_json["bindings"]
                if item["sheet_id"] == str(sheet.sheet_id)
            ),
            None,
        )
        if pin:
            version = s.get(
                ImportProfileVersion, (UUID(pin["profile_id"]), pin["version"])
            )
            if (
                not version
                or version.store_id != b.store_id
                or version.retired
                or content_digest(version.spec_json) != pin["content_digest"]
            ):
                raise AuthError("SOURCE_INTEGRITY_ERROR", 409)
            existing = dto.ProfileSpec.model_validate(version.spec_json, context={"retained_evidence": True})
        rules = list(
            sheet.shared_field_bindings
            or (existing.shared_field_bindings if existing else ())
        )
        current = next(
            (r for r in rules if r.target_field == choice.target_field), None
        )
        value_only = bool(
            pin
            and current
            and current.scope == "IMPORT_VALUE"
            and choice.scope == "IMPORT_VALUE"
            and column is None
        )
        declaration_id = uuid4()
        if choice.scope == "IMPORT_VALUE":
            declaration = ImportValue(
                target_field=choice.target_field,
                declaration_id=declaration_id,
                value=choice.value,
                evidence_reference=choice.evidence_reference,
            )
            imports = sorted(
                [
                    v
                    for v in sheet.import_values
                    if v.target_field != choice.target_field
                ]
                + [declaration],
                key=lambda v: v.target_field,
            )
            rule = ImportValueRequirement(target_field=choice.target_field)
        else:
            imports = [
                v for v in sheet.import_values if v.target_field != choice.target_field
            ]
            rule = ProfileConstant(
                target_field=choice.target_field,
                declaration_id=declaration_id,
                value=choice.value,
                evidence_reference=choice.evidence_reference,
            )
        rules = tuple(
            sorted(
                [r for r in rules if r.target_field != choice.target_field] + [rule],
                key=lambda r: r.target_field,
            )
        )
        sheet = sheet.model_copy(
            update={"shared_field_bindings": rules, "import_values": tuple(imports)}
        )
        if not value_only:
            if pin:
                # Materialize reviewed context before forking the immutable approved source rule.
                context = dto.ResolveRequest(
                    resolution=dto.SourceContext(
                        kind="source_context",
                        source_system_key=existing.scope.source_system_key,
                        report_type=existing.scope.report_type,
                        evidence_reference=existing.source_provenance.evidence_references[
                            0
                        ],
                        sales_semantics=existing.sales_semantics,
                        inventory_semantics=existing.inventory_semantics,
                    )
                )
                issues = [
                    (
                        i.model_copy(
                            update={
                                "status": "resolved",
                                "profile_ref": None,
                                "resolution_origin": "USER_PROPOSAL",
                                "resolution": (
                                    context
                                    if i.issue_type == "source_context"
                                    else i.resolution
                                ),
                            }
                        )
                        if i.sheet_id == sheet.sheet_id
                        else i
                    )
                    for i in issues
                ]
                data = {"base_spec": existing.model_dump(mode="json")}
                p = None
            if p is None or p.import_id != b.id:
                p = ImportProfile(
                    id=uuid4(),
                    store_id=b.store_id,
                    import_id=b.id,
                    sheet_id=sheet.sheet_id,
                    lifecycle_revision=rev(),
                    proposal_revision=rev(),
                    proposal_json=data,
                    rejected=False,
                )
                s.add(p)
            sheet = sheet.model_copy(update={"profile_id": p.id})
            spec, missing = build_spec(
                sheet,
                issues,
                actor.user_id,
                identities=tuple(
                    dto.IdentityRule.model_validate(r)
                    for r in data.get("identities", ())
                )
                or (existing.identity_rules if existing else ()),
                entities=tuple(
                    dto.EntityReservation.model_validate(r)
                    for r in data.get("entities", ())
                )
                or (existing.entity_proposals if existing else ()),
                conversions=tuple(
                    dto.Conversion.model_validate(r)
                    for r in data.get("conversions", ())
                )
                or (existing.conversions if existing else ()),
                prior_normalizations=existing.normalizations if existing else (),
                prior_spec=existing,
                shared_field_bindings=rules,
            )
            p.proposal_revision = rev()
            p.lifecycle_revision = rev()
            p.rejected = False
            p.proposal_json = {
                **data,
                "spec": spec.model_dump(mode="json") if spec else None,
                "missing_fields": missing,
            }
        analysis = dict(b.analysis_json)
        analysis.update(
            sheets=[
                (sheet if sh.sheet_id == sheet.sheet_id else sh).model_dump(mode="json")
                for sh in sheets
            ],
            issues=[i.model_dump(mode="json") for i in issues],
        )
        if not value_only:
            analysis["bindings"] = [
                r for r in analysis["bindings"] if r["sheet_id"] != str(sheet.sheet_id)
            ]
        analysis.pop("confirmation", None)
        b.analysis_json = analysis
        b.mapping_revision = rev()
        b.revision = rev()
        b.status = "ready_for_preview" if value_only else "review_required"
        result = dto.MappingUpdated(
            mapping_id=issue.mapping_id,
            status="resolved",
            mapping_revision=b.mapping_revision,
            progress=self._progress(issues),
            sheets=tuple(dto.SheetInfo.model_validate(sh) for sh in analysis["sheets"]),
            proposal_revision=p.proposal_revision if p else None,
            approval_required=not value_only,
        )
        self._save(s, actor, b.store_id, op, kd, fp, result)
        self._audit(
            s,
            actor,
            b.store_id,
            "SHARED_VALUE_DECLARED",
            dict(
                import_id=str(b.id),
                sheet_id=str(sheet.sheet_id),
                declaration_id=str(declaration_id),
                resolution=body.model_dump(mode="json"),
                profile_rule_changed=not value_only,
            ),
        )
        s.commit()
        return result

    @staticmethod
    def _allowed(actions, permissions):
        keys = {
            "upload": "import.upload",
            "analyze": "import.analyze",
            "preview": "import.preview",
            "resolve_mapping": "mapping.propose",
            "review_mapping": "mapping.read",
            "confirm_review": "import.commit",
            "commit": "import.commit",
        }
        return tuple(action for action in actions if keys[action] in permissions)

    def decision(self, token, store, profile_id, body, key, match, csrf):
        body = type(body).model_validate(body.model_dump())
        payload = body.model_dump(mode="json")
        if payload.get("submission_id") is None:
            # Optional C2 references must preserve the pre-C2 receipt fingerprint.
            payload.pop("submission_id", None)
            payload.pop("expected_submission_version", None)
        kd, fp, m = self._request(key, payload, match, True)
        with auth_session(self.engine) as s:
            actor, summary, _ = self.auth.authorize_in_session(
                s, token, store, owner_only=True, csrf=csrf or ""
            )
            op = "POST:profiles/" + str(profile_id) + "/decisions"
            old = self._old(s, actor, store, op, kd, fp)
            if old:
                return dto.DecisionResult.model_validate(old)
            initial = s.scalar(select(ImportProfile).where(ImportProfile.id == profile_id, ImportProfile.store_id == store))
            if initial is None:
                raise AuthError("RESOURCE_NOT_FOUND", 404)
            b = self._batch(s, initial.import_id)
            p = s.scalar(
                select(ImportProfile)
                .where(ImportProfile.id == profile_id, ImportProfile.store_id == store)
                .with_for_update()
            )
            if p is None:
                raise AuthError("RESOURCE_NOT_FOUND", 404)
            if p.lifecycle_revision != m:
                raise AuthError("PROFILE_REVISION_CONFLICT", 412)
            from app.application.use_cases.mapping_submissions import MappingSubmissions
            queue = MappingSubmissions(self)
            submission = queue.decision_target(s, p, b, body, actor, summary)
            now = self.clock()
            approved = None
            if isinstance(body, dto.Retire):
                if p.active_version != body.active_version:
                    raise AuthError("PROFILE_REVISION_CONFLICT", 412)
                v = s.get(ImportProfileVersion, (p.id, p.active_version))
                v.retired = True
                p.active_version = None
            else:
                if p.proposal_revision != body.proposal_revision:
                    raise AuthError("PROFILE_REVISION_CONFLICT", 412)
                if isinstance(body, dto.Reject):
                    p.rejected = True
                elif isinstance(body, dto.RequestChanges):
                    pass
                else:
                    if p.active_version != body.expected_active_version:
                        raise AuthError("PROFILE_REVISION_CONFLICT", 412)
                    if p.proposal_json.get("missing_fields") or not p.proposal_json.get(
                        "spec"
                    ):
                        raise AuthError("UNRESOLVED_REQUIRED_FIELDS", 409)
                    spec = dto.ProfileSpec.model_validate(submission.spec if submission else p.proposal_json["spec"])
                    spec = spec.model_copy(
                        update={
                            "source_provenance": spec.source_provenance.model_copy(
                                update={"owner_reviewed": True}
                            )
                        }
                    )
                    approved = rev()
                    s.add(
                        ImportProfileVersion(
                            profile_id=p.id,
                            version=approved,
                            store_id=store,
                            source_system_key=spec.scope.source_system_key,
                            report_type=spec.scope.report_type,
                            schema_signature=spec.structure.schema_signature,
                            content_digest=content_digest(spec.model_dump(mode="json")),
                            spec_json=spec.model_dump(mode="json"),
                            approved_at=now,
                            approved_by=actor.user_id,
                            retired=False,
                        )
                    )
                    contextkey = (
                        store,
                        spec.scope.source_system_key,
                        spec.scope.report_type,
                    )
                    if s.get(ImportSourceContext, contextkey) is None:
                        s.add(
                            ImportSourceContext(
                                store_id=store,
                                source_system_key=spec.scope.source_system_key,
                                report_type=spec.scope.report_type,
                                evidence_reference=spec.source_provenance.evidence_references[
                                    0
                                ],
                                approved_by=actor.user_id,
                                approved_at=now,
                            )
                        )
                    p.active_version = approved
                    p.rejected = False
                    if b.active_job_id:
                        raise AuthError("IMPORT_STATE_CONFLICT", 409)
                    if not (b.analysis_json or {}).get("completion"):
                        ref = dto.BindingRef(
                            sheet_id=p.sheet_id,
                            profile_id=p.id,
                            version=approved,
                            content_digest=content_digest(spec.model_dump(mode="json")),
                        )
                        analysis = dict(b.analysis_json)
                        analysis["bindings"] = [
                            r
                            for r in analysis["bindings"]
                            if r["sheet_id"] != str(p.sheet_id)
                        ] + [ref.model_dump(mode="json")]
                        # N5 approves the displayed complete spec as a group.
                        analysis["issues"] = [
                            dto.MappingIssue.model_validate(item).model_copy(update={
                                "status": "auto_mapped", "resolution_origin": "APPROVED_PROFILE",
                                "profile_ref": ref, "resolved_by": actor.user_id,
                            }).model_dump(mode="json")
                            if item["sheet_id"] == str(p.sheet_id)
                            and item["status"] == "needs_confirmation"
                            and item.get("suggestion_origin") == "RULE"
                            and item["issue_type"] in {"classification", "column"}
                            else item
                            for item in analysis["issues"]
                        ]
                        b.analysis_json = analysis
                        b.mapping_revision = rev()
                        b.revision = rev()
                        b.status = (
                            "ready_for_preview"
                            if len(analysis["bindings"])
                            == sum(
                                not sh.get("ignored", False) for sh in analysis["sheets"]
                            )
                            else "review_required"
                        )
            p.lifecycle_revision = rev()
            ident = uuid4()
            aid = self._audit(
                s,
                actor,
                store,
                "PROFILE_" + body.decision.upper(),
                dict(
                    profile_id=str(p.id),
                    decision_id=str(ident),
                    body=body.model_dump(mode="json"),
                    approved_version=approved,
                ),
            )
            projection = queue.finish_decision(s, submission, p, b, body, actor, summary, ident, aid, now, approved) if submission else None
            from app.application.contracts.collaboration import NotificationDelivery
            result = dto.DecisionResult(
                profile_id=p.id,
                approved_version=approved,
                active_version=p.active_version,
                lifecycle_revision=p.lifecycle_revision,
                decision_id=ident,
                decided_at=now,
                audit_id=aid,
                submission=projection,
                notification_delivery=NotificationDelivery(status='pending' if submission else 'not_required', event_id=aid if submission else None),
            )
            self._save(s, actor, store, op, kd, fp, result)
            s.commit()
        return result

    @staticmethod
    def _verify_preview(p):
        payload = dict(p.content_json)
        payload["summary"] = {
            k: v for k, v in payload["summary"].items() if k != "digest"
        }
        if content_digest(payload) != p.digest:
            raise AuthError("SOURCE_INTEGRITY_ERROR", 409)

    @staticmethod
    def _preview_read_authority(p,permissions):
        needed=set(p.content_json.get('source_read_permissions',()))
        needed.update(permission for schema in p.content_json['read_set']['_captured_schemas'] for permission in READS[schema])
        needed.update(permission for row in p.content_json['rows'] for permission in row.get('required_permissions',()))
        if not needed<=set(permissions):raise AuthError('PERMISSION_DENIED',403)

    def confirm_review(self, token, ident, body, key, match, csrf):
        body = dto.ConfirmReviewRequest.model_validate(body.model_dump())
        kd, fp, m = self._request(key, body.model_dump(mode="json"), match, True)
        op = "POST:imports/" + str(ident) + "/process:confirm_review"
        with auth_session(self.engine) as s:
            b = self._batch(s, ident, False)
            actor, _, permissions = self._authority(
                s, token, b, "import.commit", csrf or "", True
            )
            p = s.get(ImportPreview, body.preview_id)
            if p is None or p.import_id != b.id or p.store_id != b.store_id:
                raise AuthError("RESOURCE_NOT_FOUND", 404)
            self._verify_preview(p)
            needed = set(p.content_json["summary"]["required_actions"])
            if not needed <= set(permissions):
                raise AuthError("PERMISSION_DENIED")
            old = self._old(s, actor, b.store_id, op, kd, fp)
            if old:
                return dto.ConfirmationResult.model_validate(old)
            schemas = p.content_json["read_set"]["_captured_schemas"]
            store = b.store_id
            s.commit()
        _, current = capture_read_set(self.engine, store, schemas)
        with auth_session(self.engine) as s:
            b = self._batch(s, ident, False)
            actor, _, permissions = self._authority(
                s, token, b, "import.commit", csrf or "", True
            )
            b = self._batch(s, ident)
            p = s.get(ImportPreview, body.preview_id)
            self._verify_preview(p)
            needed = set(p.content_json["summary"]["required_actions"])
            if not needed <= set(permissions):
                raise AuthError("PERMISSION_DENIED")
            old = self._old(s, actor, b.store_id, op, kd, fp)
            if old:
                return dto.ConfirmationResult.model_validate(old)
            if (b.analysis_json or {}).get("completion"):
                raise AuthError("IMPORT_STATE_CONFLICT", 409)
            if b.revision != m:
                raise AuthError("IMPORT_REVISION_CONFLICT", 412)
            if b.active_job_id:
                raise AuthError("IMPORT_STATE_CONFLICT", 409)
            self._receipt_preview_day(p)
            refs = [ref.model_dump(mode="json") for ref, _ in self._bindings(s, b)]
            if (
                body.mapping_revision != b.mapping_revision
                or p.mapping_revision != b.mapping_revision
                or body.preview_digest != p.digest
                or p.read_set_digest != current
                or refs != p.content_json["bindings"]
                or p.content_json["summary"]["source_set_version"] != b.file_set_version
            ):
                raise AuthError("PREVIEW_STALE", 409)
            if p.content_json["summary"]["blockers"]:
                raise AuthError("PREVIEW_BLOCKED", 409)
            # Review is separate from future domain-specific correction confirmations.
            facts = dict(
                confirmation_id=uuid4(),
                import_id=b.id,
                preview_id=p.id,
                preview_digest=p.digest,
                file_set_version=b.file_set_version,
                source_digest=content_digest(
                    [
                        (str(f.id), f.digest)
                        for f in self._files(s, b)
                        if f.upload_status == "uploaded"
                    ]
                ),
                mapping_revision=b.mapping_revision,
                binding_digest=content_digest(refs),
                read_set_digest=p.read_set_digest,
                reviewed_import_revision=b.revision,
                confirmed_by=actor.user_id,
                confirmed_at=self.clock(),
                reason=body.reason,
            )
            confirmation = dto.ReviewConfirmation(**facts, content_digest="")
            confirmation = confirmation.model_copy(
                update={
                    "content_digest": content_digest(
                        confirmation.model_dump(mode="json", exclude={"content_digest"})
                    )
                }
            )
            analysis = dict(b.analysis_json)
            analysis["confirmation"] = confirmation.model_dump(mode="json")
            b.analysis_json = analysis
            b.revision = rev()
            result = dto.ConfirmationResult(
                import_revision=b.revision, confirmation=confirmation,
                canonical_commit_supported=all((r.get("canonical_domain") or (r.get("after") or {}).get("domain")) in SUPPORTED
                                               for r in p.content_json["rows"]),
            )
            self._audit(
                s,
                actor,
                b.store_id,
                "IMPORT_REVIEW_CONFIRMED",
                confirmation.model_dump(mode="json"),
            )
            self._save(s, actor, b.store_id, op, kd, fp, result)
            s.commit()
        return result

    def _receipt_preview_day(self, p):
        if 'inventory_receipts' in p.content_json['read_set']['_captured_schemas']:
            zone = ZoneInfo(p.content_json['read_set']['stores'][0]['timezone'])
            observed = datetime.fromisoformat(p.content_json['summary']['created_at'])
            if observed.astimezone(zone).date() != self.clock().astimezone(zone).date():
                raise AuthError('PREVIEW_STALE', 409)

    def _commit_preview(self, s, b, body, permissions, *, fence=False):
        p = s.get(ImportPreview, body.preview_id)
        if p is None or p.import_id != b.id or p.store_id != b.store_id:
            raise AuthError("RESOURCE_NOT_FOUND", 404)
        self._verify_preview(p)
        schemas = p.content_json["read_set"]["_captured_schemas"]
        self._receipt_preview_day(p)
        needed = set(p.content_json["summary"]["required_actions"])
        needed.update(key for schema in schemas for key in READS[schema])
        needed.add("import.commit")
        if not needed <= set(permissions):
            raise AuthError("PERMISSION_DENIED")
        confirmation_json = (b.analysis_json or {}).get("confirmation")
        if not confirmation_json:
            raise AuthError("PREVIEW_BLOCKED", 409)
        confirmation = dto.ReviewConfirmation.model_validate(confirmation_json)
        if content_digest(confirmation.model_dump(mode="json", exclude={"content_digest"})) != confirmation.content_digest:
            raise AuthError("SOURCE_INTEGRITY_ERROR", 409)
        bindings = self._bindings(s, b)
        refs = [ref.model_dump(mode="json") for ref, _ in bindings]
        source_digest = content_digest([(str(f.id), f.digest) for f in self._files(s, b)
                                        if f.upload_status == "uploaded"])
        if (body.preview_digest != p.digest or confirmation.import_id != b.id
                or confirmation.preview_id != p.id or confirmation.preview_digest != p.digest
                or confirmation.file_set_version != b.file_set_version
                or confirmation.source_digest != source_digest
                or confirmation.mapping_revision != b.mapping_revision
                or p.mapping_revision != b.mapping_revision
                or p.content_json["file_set_version"] != b.file_set_version
                or p.content_json["bindings"] != refs
                or confirmation.binding_digest != content_digest(refs)
                or confirmation.read_set_digest != p.read_set_digest):
            raise AuthError("PREVIEW_STALE", 409)
        rows = commit_rows(p, body)
        snapshot, current = read_set_in_session(s, b.store_id, schemas, fence=fence)
        if current != p.read_set_digest:
            raise AuthError("PREVIEW_STALE", 409)
        specs = {str(ref.sheet_id): spec for ref, spec in bindings}
        return p, confirmation, rows, specs, snapshot

    def commit(self, token, ident, body, key, match, csrf):
        body = dto.CommitRequest.model_validate(body.model_dump())
        kd, fp, m = self._request(key, body.model_dump(mode="json"), match, True)
        op = "POST:imports/" + str(ident) + "/process:commit"
        with auth_session(self.engine) as s:
            b = self._batch(s, ident, False)
            actor, _, permissions = self._authority(s, token, b, "import.commit", csrf or "", True)
            b = self._batch(s, ident)
            # Reauthorize the full write set even on a retained acceptance replay.
            p = s.get(ImportPreview, body.preview_id)
            if p is None or p.import_id != b.id or p.store_id != b.store_id:
                raise AuthError("RESOURCE_NOT_FOUND", 404)
            self._verify_preview(p)
            if not set(p.content_json["summary"]["required_actions"]) <= set(permissions):
                raise AuthError("PERMISSION_DENIED")
            old = self._old(s, actor, b.store_id, op, kd, fp)
            if old:
                return dto.CommitAccepted.model_validate(old)
            if b.revision != m:
                raise AuthError("IMPORT_REVISION_CONFLICT", 412)
            if b.active_job_id or (b.analysis_json or {}).get("completion"):
                raise AuthError("IMPORT_STATE_CONFLICT", 409)
            p, confirmation, _, _, _ = self._commit_preview(s, b, body, permissions, fence=True)
            plan_digest = effective_digest(p, body, confirmation)
            commit_id = uuid4()
            job = self._accept(s, b, actor, "import_commit", dict(
                request=body.model_dump(mode="json"), commit_id=str(commit_id),
                confirmation_digest=confirmation.content_digest, effective_plan_digest=plan_digest,
            ))
            b.status = "committing"
            result = dto.CommitAccepted(import_id=b.id, job_id=job.id, commit_id=commit_id,
                                        preview_id=p.id, effective_plan_digest=plan_digest,
                                        import_revision=b.revision)
            self._save(s, actor, b.store_id, op, kd, fp, result)
            self._audit(s, actor, b.store_id, "IMPORT_COMMIT_ACCEPTED", result.model_dump(mode="json"))
            s.commit()
        return result

    def _execute_commit(self, job_id, claim):
        with auth_session(self.engine) as s:
            candidate = s.get(ImportJob, job_id)
            actor, _, permissions = self._job_authority(s, candidate)
            b = self._batch(s, candidate.import_id)
            j = s.scalar(select(ImportJob).where(ImportJob.id == job_id).with_for_update()
                         .execution_options(populate_existing=True))
            if j.status != "running" or j.claim != claim or b.active_job_id != j.id:
                raise AuthError("IMPORT_STATE_CONFLICT", 409)
            body = dto.CommitRequest.model_validate(j.input_json["request"])
            from app.repositories.readiness import fence_readiness_inputs
            fence_readiness_inputs(s)
            p, confirmation, rows, specs, snapshot = self._commit_preview(s, b, body, permissions, fence=True)
            if (j.input_json["confirmation_digest"] != confirmation.content_digest
                    or j.input_json["effective_plan_digest"] != effective_digest(p, body, confirmation)):
                raise AuthError("PREVIEW_STALE", 409)
            j.stage = "committing"
            impacts, references, sales_sources = write_rows(s, b.store_id, rows, specs, snapshot, body, actor_id=actor.user_id, recorded_at=self.clock())
            s.flush()
            now = self.clock()
            audit_id = uuid4()
            commit_id = UUID(j.input_json["commit_id"])
            post_snapshot, _ = read_set_in_session(s, b.store_id, snapshot["_captured_schemas"])
            if "import_sales_sources" in post_snapshot:
                post_snapshot["import_sales_sources"].extend({**r, "audit_id": str(audit_id)} for r in sales_sources)
            evaluated, omitted = [], []
            for action, required in (("import", {"import.read"}), ("menu", {"menu.read"}),
                                     ("inventory", {"inventory.read", "ingredient.read"})):
                if required <= set(permissions):
                    evaluated.append(action)
                else:
                    omitted.append(dto.OmittedAction(action=action))
            warnings = p.content_json["summary"]["warnings"]
            from app.application.use_cases.readiness import ReadinessReads
            completion = dto.ImportCompletion(
                import_id=b.id, status="completed_with_warnings" if warnings else "completed",
                data_date=b.data_date, outcome="committed" if impacts["inserted"] or impacts["changed"] else "no_changes",
                completed_at=now, commit_id=commit_id, preview_id=p.id,
                effective_plan_digest=j.input_json["effective_plan_digest"],
                mapping_bindings=p.content_json["bindings"], audit_reference=audit_id,
                canonical_references=references,
                summary=dto.CompletionSummary(
                    files=sum(f.upload_status == "uploaded" for f in self._files(s, b)),
                    sheets=sum(not sh.ignored for sh in self._sheets(b)),
                    rows=sum(len(source["rows"]) for source in b.analysis_json["sources"]
                             if str(source["sheet_id"]) not in {str(sh.sheet_id) for sh in self._sheets(b) if sh.ignored}),
                    mapped_fields=sum(not i.ignored and i.target_field is not None for i in self._issues(b)
                                      if i.issue_type == "column"),
                    warnings=len(warnings), counts=p.content_json["summary"]["counts"],
                    inserted_record_count=impacts["inserted"], changed_record_count=impacts["changed"],
                    no_op_count=impacts["noops"],
                ),
                updated_resources=dto.UpdatedResources(
                    inventory=dto.InventoryImpact(updated=bool(impacts["inventory_changes"]),
                        affected_ingredient_count=impacts["affected_ingredients"] or None,
                        changed_record_count=impacts["inventory_changes"] or None),
                    menu=dto.MenuImpact(updated=bool(impacts["affected_products"]),
                                        affected_product_count=impacts["affected_products"] or None,
                                        changed_record_count=(impacts["products"] + impacts["recipes"]) or None),
                    sales=dto.SalesImpact(updated=bool(impacts["added_sales"] or impacts["changed_sales"]),
                                          added_record_count=impacts["added_sales"], changed_record_count=impacts["changed_sales"]),
                    **{name:dto.ConfigurationImpact(updated=bool(counts["created"] or counts["changed"]),created_count=counts["created"],changed_count=counts["changed"]) for name,counts in impacts["configurations"].items()},
                    catalog=dto.CatalogImpact(created_product_count=impacts["products"], created_ingredient_count=impacts["ingredients"]),
                ),
                readiness=ReadinessReads.completion_in_transaction(s,b.store_id,now,permissions),
            )
            record = completion.model_dump(mode="json")
            s.add(ImportAudit(id=audit_id, store_id=b.store_id, actor_id=actor.user_id,
                              occurred_at=now, kind="IMPORT_CANONICAL_COMMITTED",
                              record_json=dict(completion=record, sales_sources=sales_sources,
                                               confirmation=confirmation.model_dump(mode="json"), request=body.model_dump(mode="json"))))
            b.analysis_json = {**b.analysis_json, "completion": record, "completion_digest": content_digest(record)}
            b.status, b.active_job_id, b.revision = completion.status, None, rev()
            j.status, j.stage, j.completed_at = "completed", "completed", now
            j.result_json = dto.CompletionResult(resource_id=b.id, commit_id=commit_id).model_dump(mode="json")
            self._audit(s, actor, b.store_id, "IMPORT_JOB_COMPLETED", dict(job_id=str(j.id), operation=j.operation, result=j.result_json))
            try:
                s.commit()
            except Exception as error:
                if _is_uncertain_commit(error):
                    raise _ImportCommitUncertain() from error
                raise
        # HTTP 2xx is not proof; durable completion is checked in a fresh Session.
        with auth_session(self.engine) as fresh:
            durable = self._batch(fresh, completion.import_id, False)
            if durable.analysis_json.get("completion_digest") != content_digest(record):
                raise AuthError("SOURCE_INTEGRITY_ERROR", 409)
        return job_id

    def completion(self, token, ident):
        with auth_session(self.engine) as s:
            b = self._batch(s, ident, False)
            self._authority(s, token, b, "import.read", sensitive=True)
            b = self._batch(s, ident)
            record = (b.analysis_json or {}).get("completion")
            if not record:
                raise AuthError("IMPORT_NOT_COMPLETED", 409)
            if content_digest(record) != b.analysis_json.get("completion_digest"):
                raise AuthError("SOURCE_INTEGRITY_ERROR", 409)
            result = dto.ImportCompletion.model_validate(record)
            s.commit()
        return result

    def preview(self, token, ident, body, key, match, csrf):
        if isinstance(body, dto.CommitRequest):
            return self.commit(token, ident, body, key, match, csrf)
        body = type(body).model_validate(body.model_dump())
        kd, fp, m = self._request(key, body.model_dump(mode="json"), match, True)
        with auth_session(self.engine) as s:
            b = self._batch(s, ident, False)
            actor, _, _ = self._authority(
                s, token, b, "import.preview", csrf or "", True
            )
            b = self._batch(s, ident)
            op = "POST:imports/" + str(ident) + "/process:" + body.phase
            old = self._old(s, actor, b.store_id, op, kd, fp)
            if old:
                return dto.PreviewAccepted.model_validate(old)
            if b.analysis_json and b.analysis_json.get("completion"):
                raise AuthError("IMPORT_STATE_CONFLICT", 409)
            if m != b.revision:
                raise AuthError("IMPORT_REVISION_CONFLICT", 412)
            if body.mapping_revision != b.mapping_revision:
                raise AuthError("MAPPING_REVISION_CONFLICT", 412)
            summary = self._summary(s, b)
            if not summary.can_preview:
                raise AuthError(summary.blockers[0].code, 409)
            job = self._accept(
                s,
                b,
                actor,
                "import_preview",
                dict(
                    mapping_revision=b.mapping_revision,
                    file_set_version=b.file_set_version,
                    bindings=[r.model_dump(mode="json") for r in summary.binding_refs],
                ),
            )
            b.status = "previewing"
            result = dto.PreviewAccepted(
                import_id=b.id,
                status="previewing",
                phase="preview",
                job_id=job.id,
                job_status="queued",
                import_revision=b.revision,
            )
            self._save(s, actor, b.store_id, op, kd, fp, result)
            s.commit()
        return result

    def _job_authority(self, s, job):
        repo = AuthRepository(s)
        user = repo.lock_user(job.actor_id)
        session = repo.lock_session(job.session_digest)
        account = s.get(AuthAccount, job.actor_id)
        now = self.clock()
        if (
            not user
            or not user.active
            or not session
            or session.user_id != job.actor_id
            or session.revoked_at
            or now >= min(session.idle_expires_at, session.absolute_expires_at)
            or not account
            or not account.credential_ready
            or session.credential_revision != account.credential_revision
            or account.verified_email != user.email
        ):
            raise AuthError("UNAUTHENTICATED", 401)
        store = repo.lock_store(job.store_id)
        member = repo.lock_membership(job.store_id, job.actor_id)
        if not store or not store.active or not member or not member.active:
            raise AuthError("PERMISSION_DENIED")
        summary, permissions = self.auth._summary(s, store, member)
        needed = {"import_analyze": "import.analyze", "import_preview": "import.preview",
                  "import_commit": "import.commit"}[job.operation]
        if needed not in permissions:
            raise AuthError("PERMISSION_DENIED")
        return Actor(user.id, session.digest), summary, permissions

    def run_one(self):
        if not self._execution.acquire(False):
            return None
        self._current = None
        try:
            return self._run_one()
        except Exception as primary:
            from app.application.contracts.import_source import SourceParseError

            known = isinstance(primary, (AuthError, SourceParseError))
            if self._current:
                jid, claim = self._current
                try:
                    with auth_session(self.engine) as s:
                        j = s.get(ImportJob, jid)
                        if (isinstance(primary, _ImportCommitUncertain)
                                and j.operation == "import_commit" and j.status == "completed"):
                            b = self._batch(s, j.import_id, False)
                            record = (b.analysis_json or {}).get("completion")
                            if (record and content_digest(record) == b.analysis_json.get("completion_digest")
                                    and j.result_json == dto.CompletionResult(resource_id=b.id, commit_id=record["commit_id"]).model_dump(mode="json")):
                                return jid
                        b = self._batch(s, j.import_id)
                        j = s.scalar(
                            select(ImportJob)
                            .where(ImportJob.id == jid)
                            .with_for_update()
                            .execution_options(populate_existing=True)
                        )
                        if j.status == "running" and j.claim == claim:
                            details = dto.JobErrorDetails(blockers=getattr(primary, "blockers", ()))
                            if isinstance(primary, SourceParseError) and getattr(
                                primary, "file_id", None
                            ):
                                details = dto.JobErrorDetails(
                                    source_locations=(
                                        dto.ParseFailureLocation(
                                            file_id=primary.file_id,
                                            sheet_name=primary.sheet,
                                            row_number=primary.row,
                                            source_column_index=primary.column,
                                        ),
                                    )
                                )
                                failed_file = s.get(ImportFile, primary.file_id)
                                failed_file.parse_status = "failed"
                            self._fail(
                                s,
                                b,
                                j,
                                primary.code if known else "IMPORT_EXECUTION_ERROR",
                                details,
                            )
                            s.commit()
                    with auth_session(self.engine) as fresh:
                        durable = fresh.get(ImportJob, jid)
                        failed = durable.status == "failed" and durable.claim == claim
                    if known and failed:
                        return jid
                except Exception as secondary:
                    primary.add_note(
                        "Import failure recording failed: " + type(secondary).__name__
                    )
                    logging.getLogger(__name__).error(
                        "Import failure recording failed (%s)", type(secondary).__name__
                    )
            raise
        finally:
            self._execution.release()

    def _run_one(self):
        claim = uuid4()
        job_id = None
        with auth_session(self.engine) as s:
            candidate = s.scalar(
                select(ImportJob)
                .where(ImportJob.status == "queued")
                .order_by(ImportJob.created_at, ImportJob.id)
                .limit(1)
            )
            if candidate is None:
                return None
            job_id = candidate.id
            try:
                self._job_authority(s, candidate)
            except AuthError as e:
                b = self._batch(s, candidate.import_id)
                j = s.scalar(
                    select(ImportJob)
                    .where(ImportJob.id == job_id)
                    .with_for_update()
                    .execution_options(populate_existing=True)
                )
                if j.status == "queued":
                    self._fail(s, b, j, e.code)
                    s.commit()
                return job_id
            b = self._batch(s, candidate.import_id)
            j = s.scalar(
                select(ImportJob)
                .where(ImportJob.id == job_id)
                .with_for_update()
                .execution_options(populate_existing=True)
            )
            if j.status != "queued":
                return None
            j.status = "running"
            j.stage = "parsing" if j.operation == "import_analyze" else "validating"
            j.claim = claim
            j.started_at = self.clock()
            inputs = dict(j.input_json)
            inputs["process"] = current_process().model_dump(mode="json")
            j.input_json = inputs
            operation = j.operation
            store_id = j.store_id
            mapping_revision = b.mapping_revision
            file_names = {f.id: f.filename for f in self._files(s, b)}
            files = [
                (
                    f.id,
                    s.get(ImportBlob, (b.store_id, f.digest)).content,
                    f.format,
                    f.digest,
                )
                for f in self._files(s, b)
                if f.upload_status == "uploaded" and operation != "import_commit"
            ]
            sources = b.analysis_json["sources"] if b.analysis_json else []
            import_values = (
                {str(sh.sheet_id): sh.import_values for sh in self._sheets(b)}
                if b.analysis_json
                else {}
            )
            ignored_sheets = (
                # Batch stockout declarations do not change reusable profile semantics.
                {str(sh.sheet_id) for sh in self._sheets(b) if sh.ignored}
                if b.analysis_json
                else set()
            )
            specs = (
                {str(ref.sheet_id): spec for ref, spec in self._bindings(s, b)}
                if operation == "import_preview"
                else {}
            )
            stockout_policies = {
                str(i.sheet_id): (i.resolution.resolution.missing_stockout,
                                 i.resolution.resolution.evidence_reference)
                for i in self._issues(b) if i.issue_type == 'source_context' and i.resolution
                and isinstance(i.resolution.resolution, dto.SourceContext)
                and i.resolution.resolution.missing_stockout is not None
            } if b.analysis_json else {}
            actor_id = j.actor_id
            import_id = j.import_id
            self._current = (job_id, claim)
            s.commit()
        if operation == "import_commit":
            return self._execute_commit(job_id, claim)
        # No Session, transaction, row lock or checked-out connection during parsing.
        try:
            if operation == "import_analyze":
                sheets = []
                issues = []
                sources = []
                total_rows = 0
                total_sheets = 0
                expanded = 0
                for fid, content, fmt, expected in files:
                    if "sha256:" + hashlib.sha256(content).hexdigest() != expected:
                        raise AuthError("SOURCE_INTEGRITY_ERROR", 409)
                    if fmt == "xlsx":
                        try:
                            with zipfile.ZipFile(io.BytesIO(content)) as archive:
                                expanded += sum(e.file_size for e in archive.infolist())
                        except zipfile.BadZipFile:
                            raise AuthError("MALFORMED_WORKBOOK", 422) from None
                        if expanded > 200 * 1024 * 1024:
                            raise AuthError("RESOURCE_LIMIT_EXCEEDED", 413)
                    try:
                        parsed = parse_source(content, fmt)
                    except Exception as error:
                        from app.application.contracts.import_source import (
                            SourceParseError,
                        )

                        if isinstance(error, SourceParseError):
                            error.file_id = fid
                        raise
                    ss, ii, raw = discover(fid, parsed)
                    total_sheets += len(parsed.sheets)
                    total_rows += sum(sh.row_count for sh in ss)
                    if total_sheets > 100 or total_rows > 100000:
                        raise AuthError("RESOURCE_LIMIT_EXCEEDED", 413)
                    sheets.extend(ss)
                    issues.extend(ii)
                    sources.extend(raw)
                result = (sheets, issues, sources)
                with auth_session(self.engine) as lookup:
                    job = lookup.get(ImportJob, job_id)
                    _, _, provider_permissions = self._job_authority(lookup, job)
                    lookup.commit()
                capture_schemas = captured_domains(
                    sources,
                    {
                        str(sh.sheet_id): [
                            i
                            for i in issues
                            if i.sheet_id == sh.sheet_id and i.issue_type == "column"
                        ]
                        for sh in sheets
                    },
                )
                capture_unknown = any(
                    i.issue_type == "schema_blocker"
                    or i.issue_type == "column"
                    and i.target_field is None
                    for i in issues
                )
                needed = (
                    set(ALL_READS)
                    if capture_unknown or not capture_schemas
                    else {p for schema in capture_schemas for p in READS[schema]}
                )
                from app.application.import_analysis import receipt_sensitive_reads
                needed.update(receipt_sensitive_reads(sources,{str(sh.sheet_id):[i for i in issues
                    if i.sheet_id==sh.sheet_id and i.issue_type=='column'] for sh in sheets}))
                if not needed <= set(provider_permissions):
                    raise AuthError("PERMISSION_DENIED")
                snapshot, _ = capture_read_set(
                    self.engine, store_id, None if capture_unknown else capture_schemas
                )
                warnings = []
                from app.infrastructure.import_suggestions import suggest_sheet
                from app.application.import_descriptors import rule_classification

                provider_sheets = 0
                for index, sheet in enumerate(sheets):
                    _, _, _, low_quality = rule_classification(
                        sheet.headers, sheet.name
                    )
                    if not low_quality:
                        continue
                    own_columns = [i for i in issues if i.sheet_id == sheet.sheet_id and i.issue_type == 'column']
                    if own_columns and all(i.suggested_ignore for i in own_columns):
                        continue
                    if self.settings.import_llm_suggestions_enabled:
                        if provider_sheets >= 2:
                            warnings.append(notice("LLM_CALL_LIMIT", dto.SourceLocation(
                                file_id=sheet.file_id, sheet_id=sheet.sheet_id), True))
                            continue
                        provider_sheets += 1
                    rawsheet = next(
                        raw for raw in sources if raw["sheet_id"] == str(sheet.sheet_id)
                    )
                    rule = dict(
                        sheet_type=sheet.selected_type,
                        columns=[
                            dict(
                                source_column_index=i.source_location.source_column_index,
                                target_field=i.target_field,
                                candidates=list(i.candidate_targets),
                                reason=i.suggestion_reason,
                            )
                            for i in issues
                            if i.sheet_id == sheet.sheet_id and i.issue_type == "column"
                        ],
                        related_sheets=[dict(sheet_type=other.selected_type, headers=list(other.headers[:16]))
                                        for other in sheets if other.sheet_id != sheet.sheet_id
                                        and other.selected_type is not None][:4],
                    )
                    filename = file_names[sheet.file_id]
                    diagnostics = []
                    suggestion, unavailable = suggest_sheet(
                        self.settings, sheet, rawsheet, filename, rule, sheet.selected_type, diagnostics
                    )
                    if diagnostics:
                        sheet = sheet.model_copy(update={'suggestion_diagnostic': diagnostics[0]})
                        sheets[index] = sheet
                    if unavailable:
                        warnings.append(
                            notice(
                                unavailable,
                                dto.SourceLocation(
                                    file_id=sheet.file_id, sheet_id=sheet.sheet_id
                                ),
                                True,
                            )
                        )
                        continue
                    proposals = {c.source_column_index: c for c in suggestion.columns}
                    sheets[index] = sheet.model_copy(
                        update={
                            "selected_type": suggestion.sheet_type,
                            "suggested_type": suggestion.sheet_type,
                            "classification_origin": "QWEN",
                            "confidence": suggestion.confidence,
                        }
                    ) if sheet.selected_type is None else sheet
                    issues = [
                        (
                            item.model_copy(
                                update={
                                    "target_field": proposals[
                                        item.source_location.source_column_index
                                    ].target_field,
                                    "suggested_target_field": proposals[
                                        item.source_location.source_column_index
                                    ].target_field,
                                    "suggestion_origin": "QWEN",
                                    "suggestion_reason": "MODEL_SEMANTIC_PROPOSAL_REQUIRES_REVIEW",
                                    "model_reason": proposals[item.source_location.source_column_index].reason,
                                    "candidate_targets": proposals[item.source_location.source_column_index].candidates or item.candidate_targets,
                                    "confidence": proposals[
                                        item.source_location.source_column_index
                                    ].confidence,
                                    "status": (
                                        "needs_confirmation"
                                        if proposals[
                                            item.source_location.source_column_index
                                        ].target_field
                                        else "unmatched"
                                    ),
                                }
                            )
                            if item.sheet_id == sheet.sheet_id
                            and item.issue_type == "column"
                            and item.target_field is None
                            and (item.status != "ambiguous" or item.suggestion_reason != "DUPLICATE_OR_AMBIGUOUS_TARGET")
                            else (
                                item.model_copy(
                                    update={
                                        "suggestion_origin": "QWEN",
                                        "confidence": suggestion.confidence,
                                        "status": (
                                            "needs_confirmation"
                                            if suggestion.sheet_type
                                            else "unmatched"
                                        ),
                                    }
                                )
                                if item.sheet_id == sheet.sheet_id
                                and item.issue_type == "classification"
                                and sheet.selected_type is None
                                else item
                            )
                        )
                        for item in issues
                    ]
                    # Model wording is advisory and untrusted, never a backend status/code.
                    if suggestion.warnings:
                        warnings.append(
                            notice(
                                "LLM_ADVISORY_REVIEW_REQUIRED",
                                dto.SourceLocation(
                                    file_id=sheet.file_id, sheet_id=sheet.sheet_id
                                ),
                                True,
                            )
                        )
                for fid, content, fmt, expected in files:
                    if not any(sh.file_id == fid for sh in sheets):
                        warnings.append(notice("EMPTY_SHEET_SKIPPED", None, True))
                result = (sheets, issues, sources, snapshot, warnings)
            else:
                with auth_session(self.engine) as s:
                    job = s.get(ImportJob, job_id)
                    _, summary, permissions = self._job_authority(s, job)
                    s.commit()
                capture_schemas = captured_domains(
                    sources, {key: spec.field_bindings for key, spec in specs.items()}
                )
                needed = {p for schema in capture_schemas for p in READS[schema]}
                from app.application.import_analysis import receipt_sensitive_reads
                needed.update(receipt_sensitive_reads(sources,{key:spec.field_bindings for key,spec in specs.items()},import_values))
                if not needed <= set(permissions):
                    raise AuthError("PERMISSION_DENIED")
                snapshot, read_digest = capture_read_set(
                    self.engine, store_id, capture_schemas
                )
                rows = make_preview(
                    [
                        source
                        for source in sources
                        if source["sheet_id"] not in ignored_sheets
                    ],
                    specs,
                    snapshot,
                    self.clock(),
                    snapshot["stores"][0]["timezone"],
                    snapshot["stores"][0]["currency"],
                    import_values=import_values,
                    stockout_policies=stockout_policies,
                )
                result = (rows, read_digest, snapshot)
        except Exception as e:
            raise
        with auth_session(self.engine) as s:
            j = s.get(ImportJob, job_id)
            actor, _, permissions = self._job_authority(s, j)
            b = self._batch(s, j.import_id)
            j = s.scalar(
                select(ImportJob)
                .where(ImportJob.id == job_id)
                .with_for_update()
                .execution_options(populate_existing=True)
            )
            if j.status != "running" or j.claim != claim:
                raise AuthError("IMPORT_STATE_CONFLICT", 409)
            if (
                b.active_job_id != j.id
                or b.file_set_version != j.input_json["file_set_version"]
                or operation == "import_analyze" and b.mapping_revision != mapping_revision
            ):
                raise AuthError("IMPORT_STATE_CONFLICT", 409)
            if operation == "import_analyze":
                sheets, issues, sources, snapshot, warnings = result
                bindings = []
                # I03 carries no attested source context. Signature candidates are
                # discovery only; M04 establishes source before binding a version.
                for sheet in sheets:
                    versions = s.scalars(select(ImportProfileVersion).join(
                        ImportProfile, ImportProfile.id == ImportProfileVersion.profile_id
                    ).where(
                        ImportProfileVersion.store_id == store_id,
                        ImportProfileVersion.schema_signature == sheet.schema_signature,
                        ImportProfileVersion.retired.is_(False),
                        ImportProfile.active_version == ImportProfileVersion.version,
                    )).all()
                    if len(versions) > 1:
                        issues = [i.model_copy(update={"code": "PROFILE_MATCH_AMBIGUOUS",
                            "status": "ambiguous"}) if i.sheet_id == sheet.sheet_id
                            and i.issue_type == "source_context" else i for i in issues]
                issues.extend(identity_issues(sheets, issues, sources, snapshot))
                schemas = sorted(
                    {i.target_field.split(".")[0] for i in issues if i.target_field}
                )
                needed = (
                    {p for schema in capture_schemas for p in READS[schema]}
                    if capture_schemas
                    else set(ALL_READS)
                )
                if not needed <= set(permissions):
                    raise AuthError("PERMISSION_DENIED")
                from app.application.import_analysis import receipt_sensitive_reads
                extra_reads=receipt_sensitive_reads(sources,{str(sh.sheet_id):[i for i in issues
                    if i.sheet_id==sh.sheet_id and i.issue_type=='column'] for sh in sheets})
                if not extra_reads <= set(permissions): raise AuthError('PERMISSION_DENIED')
                b.analysis_json = dict(
                    sheets=[sh.model_dump(mode="json") for sh in sheets],
                    issues=[i.model_dump(mode="json") for i in issues],
                    sources=sources,
                    bindings=bindings,
                    schemas=schemas,
                    warnings=[n.model_dump(mode="json") for n in warnings],
                )
                b.mapping_revision = rev()
                b.status = (
                    "ready_for_preview"
                    if len(bindings) == sum(not sh.ignored for sh in sheets)
                    and any(not sh.ignored for sh in sheets)
                    else "review_required"
                )
                for f in self._files(s, b):
                    if f.upload_status == "uploaded":
                        f.parse_status = "parsed"
                j.result_json = dto.AnalysisResult(
                    resource_type="import_analysis",
                    resource_id=b.id,
                    analysis_id=b.analysis_id,
                ).model_dump(mode="json")
            else:
                if (
                    mapping_revision != b.mapping_revision
                    or j.input_json["bindings"] != b.analysis_json["bindings"]
                ):
                    raise AuthError("PREVIEW_STALE", 409)
                self._bindings(s, b)
                rows, read_digest, _ = result
                pid = uuid4()
                groups = []
                for schema in sorted(
                    {
                        row.canonical_domain or row.after.domain
                        for row in rows
                        if row.canonical_domain or row.after
                    }
                ):
                    own = [
                        r
                        for r in rows
                        if (r.canonical_domain or (r.after.domain if r.after else None))
                        == schema
                    ]
                    groups.append(
                        dto.PreviewGroup(
                            canonical_domain=schema,
                            required_write_action=WRITES[schema],
                            row_count=len(own),
                            planned_insert_count=sum(
                                r.classification == "NEW" for r in own
                            ),
                            planned_update_count=sum(
                                r.classification == "CHANGED" for r in own
                            ),
                            no_op_count=sum(
                                r.classification == "UNCHANGED" for r in own
                            ),
                            blocked_count=sum(bool(r.blockers) for r in own),
                        )
                    )
                blockers = tuple(x for r in rows for x in r.blockers)
                warnings = tuple(x for r in rows for x in r.warnings) + tuple(
                    notice(
                        (
                            "SHEET_EXPLICITLY_IGNORED"
                            if sh.ignored
                            else "COLUMN_EXPLICITLY_IGNORED"
                        ),
                        dto.SourceLocation(file_id=sh.file_id, sheet_id=sh.sheet_id),
                        True,
                    )
                    for sh in self._sheets(b)
                    if sh.ignored
                    or any(
                        i.ignored for i in self._issues(b) if i.sheet_id == sh.sheet_id
                    )
                )
                counts = dto.ClassificationCounts(
                    **{
                        k: sum(r.classification == k for r in rows)
                        for k in ("NEW", "UNCHANGED", "CHANGED", "INVALID", "CONFLICT")
                    }
                )
                payload = dict(
                    rows=[r.model_dump(mode="json") for r in rows],
                    read_set=result[2],
                    read_set_digest=read_digest,
                    source_evidence_digest=content_digest(b.analysis_json['sources']),
                    source_read_permissions=self._sensitive_reads(b),
                    analysis_id=str(b.analysis_id),
                    file_set_version=b.file_set_version,
                    mapping_revision=b.mapping_revision,
                    bindings=b.analysis_json["bindings"],
                    reviewed_sheets=[
                        sh.model_dump(mode="json") for sh in self._sheets(b)
                    ],
                    reviewed_mappings=[
                        i.model_dump(mode="json", exclude={"samples"})
                        for i in self._issues(b)
                    ],
                    policy_version="import_mapping_policy/1",
                    source_files=[
                        dict(file_id=str(f.id), content_digest=f.digest)
                        for f in self._files(s, b)
                        if f.upload_status == "uploaded"
                    ],
                )
                actions = {
                    WRITES[g.canonical_domain]
                    for g in groups
                    if g.canonical_domain != "scope_declarations"
                }
                for row in rows:
                    actions.update(row.required_permissions)
                    if row.proposed_action == "REPLACE_DAILY_TOTAL":
                        actions.add("sales.correct")
                    elif row.proposed_action == "MERGE_DISJOINT_SALES":
                        actions.add("sales.merge")
                    elif row.after and row.after.domain == "scope_declarations":
                        kind = row.after.declaration.kind
                        actions.update(
                            ("inventory.count.correct",)
                            if kind == "INVENTORY"
                            else (
                                ("sales.record",)
                                if kind == "SALES_COVERAGE"
                                else ("supplier.fees.manage", "budget.read")
                            )
                        )
                summary = dto.PreviewSummary(
                    preview_id=pid,
                    digest="",
                    created_at=self.clock(),
                    source_set_version=b.file_set_version,
                    mapping_bindings=tuple(ref for ref, _ in self._bindings(s, b)),
                    validation_status=(
                        "blocked"
                        if blockers
                        else (
                            "confirmation_required"
                            if any(r.confirmation_required for r in rows)
                            else "ready"
                        )
                    ),
                    required_actions=tuple(sorted(actions)),
                    groups=tuple(groups),
                    counts=counts,
                    blockers=blockers,
                    warnings=warnings,
                )
                payload["summary"] = {
                    k: v
                    for k, v in summary.model_dump(mode="json").items()
                    if k != "digest"
                }
                pdigest = content_digest(payload)
                summary = summary.model_copy(update={"digest": pdigest})
                payload["summary"] = summary.model_dump(mode="json")
                s.add(
                    ImportPreview(
                        id=pid,
                        import_id=b.id,
                        store_id=b.store_id,
                        digest=pdigest,
                        created_at=summary.created_at,
                        mapping_revision=b.mapping_revision,
                        content_json=payload,
                        read_set_digest=read_digest,
                    )
                )
                b.status = "blocked" if blockers else "preview_ready"
                analysis = dict(b.analysis_json)
                analysis["latest_preview_id"] = str(pid)
                analysis.pop("confirmation", None)
                b.analysis_json = analysis
                j.result_json = dto.PreviewResult(
                    resource_type="import_preview", resource_id=b.id, preview_id=pid
                ).model_dump(mode="json")
            j.status = "completed"
            j.stage = "completed"
            j.completed_at = self.clock()
            b.active_job_id = None
            b.revision = rev()
            self._audit(
                s,
                actor,
                b.store_id,
                "IMPORT_JOB_COMPLETED",
                dict(job_id=str(j.id), operation=j.operation, result=j.result_json),
            )
            from app.application.use_cases.mapping_submissions import invalidate_submissions
            invalidate_submissions(self, s, actor, b.store_id)
            s.commit()
        return job_id

    def _fail(self, s, b, j, code, details=None):
        j.status = "failed"
        j.stage = "failed"
        j.completed_at = self.clock()
        j.error_json = dto.JobError(
            code=code, message=code, details=details or dto.JobErrorDetails()
        ).model_dump(mode="json")
        j.result_json = None
        if b.active_job_id == j.id:
            b.active_job_id = None
            b.status = "failed"
            b.revision = rev()

    def recover(self):
        """Explicit local process-death proof; no timeout/re-execution/live-config switch."""
        recovered = []
        with auth_session(self.engine) as lookup:
            candidates = [
                (
                    j.id,
                    j.import_id,
                    j.store_id,
                    j.actor_id,
                    j.session_digest,
                    j.claim,
                    j.input_json.get("process"),
                )
                for j in lookup.scalars(
                    select(ImportJob).where(ImportJob.status == "running")
                ).all()
            ]
        for jid, bid, store, actor, session_digest, claim, process in candidates:
            if (
                not process
                or liveness(ProcessIdentity.model_validate(process)) != "DEAD"
            ):
                continue
            with auth_session(self.engine) as s:
                # Same lock order as transitions; recovery conveys no new authority.
                repo = AuthRepository(s)
                repo.lock_user(actor)
                repo.lock_session(session_digest)
                repo.lock_store(store)
                repo.lock_membership(store, actor)
                b = self._batch(s, bid)
                j = s.scalar(
                    select(ImportJob)
                    .where(ImportJob.id == jid)
                    .with_for_update()
                    .execution_options(populate_existing=True)
                )
                if (
                    j.status == "running"
                    and j.claim == claim
                    and j.input_json.get("process") == process
                ):
                    self._fail(s, b, j, "IMPORT_EXECUTOR_INTERRUPTED")
                    recovered.append(j.id)
                s.commit()
        return tuple(recovered)

    def job(self, token, ident):
        with auth_session(self.engine) as s:
            j = s.get(ImportJob, ident)
            if j is None:
                raise AuthError("RESOURCE_NOT_FOUND", 404)
            b = self._batch(s, j.import_id, False)
            self._authority(s, token, b, "import.read", sensitive=True)
            result = dto.JobView(
                job_id=j.id,
                operation=j.operation,
                status=j.status,
                stage=j.stage,
                progress=1 if j.status == "completed" else None,
                created_at=j.created_at,
                started_at=j.started_at,
                completed_at=j.completed_at,
                context=dto.JobContext(store_id=j.store_id, import_id=j.import_id),
                result=j.result_json,
                error=j.error_json,
            )
            s.commit()
            return result

    def read(
        self,
        token,
        ident,
        files_limit=50,
        files_cursor=None,
        include_preview=False,
        preview_id=None,
        rows_limit=50,
        rows_cursor=None,
        classification=None,
        configurations=False,
        file_id=None,
        sheet_id=None,
        projection="summary",
    ):
        if projection not in ('summary','source_effect') or ((file_id or sheet_id or projection!='summary') and not include_preview):
            raise AuthError('INVALID_FILTER',422)
        if (file_id or sheet_id or projection!='summary') and preview_id is None:
            raise AuthError('INVALID_FILTER',422)
        with auth_session(self.engine) as s:
            b = self._batch(s, ident, False)
            # Keep the established User/session/Store-before-batch lock order.
            # Refresh cached metadata after authorization may have waited on a writer.
            self._authority(s, token, b, "import.read")
            b = self._batch(s, ident)
            confirmation = (
                dto.ReviewConfirmation.model_validate(b.analysis_json["confirmation"])
                if b.analysis_json and b.analysis_json.get("confirmation")
                else None
            )
            actor, summary, permissions = self._authority(
                s,
                token,
                b,
                "import.read",
                sensitive=include_preview or configurations or confirmation is not None,
            )
            if (
                confirmation
                and content_digest(
                    confirmation.model_dump(mode="json", exclude={"content_digest"})
                )
                != confirmation.content_digest
            ):
                raise AuthError("SOURCE_INTEGRITY_ERROR", 409)
            files = self._files(s, b)
            page, paging = self._page(
                [self._file(f) for f in files],
                token,
                actor,
                summary,
                [str(b.id), b.file_set_version, "files"],
                files_limit,
                files_cursor,
            )
            preview = None
            configuration_data = None
            if include_preview or configurations or confirmation is not None:
                query = select(ImportPreview).where(ImportPreview.import_id == b.id)
                latest = preview_id or (
                    UUID(b.analysis_json["latest_preview_id"])
                    if b.analysis_json and b.analysis_json.get("latest_preview_id")
                    else None
                )
                p = s.scalar(
                    query.where(ImportPreview.id == latest)
                    if latest
                    else query.order_by(
                        ImportPreview.created_at.desc(), ImportPreview.id
                    ).limit(1)
                )
                if p is None and (include_preview or preview_id):
                    raise AuthError("PREVIEW_NOT_AVAILABLE", 409)
                if p is None:
                    if b.analysis_json is None:
                        raise AuthError("ANALYSIS_NOT_READY", 409)
                    staged = []
                    for rawsheet in b.analysis_json["sources"]:
                        sheet = next(
                            sh
                            for sh in self._sheets(b)
                            if str(sh.sheet_id) == rawsheet["sheet_id"]
                        )
                        own = [
                            i
                            for i in self._issues(b)
                            if i.sheet_id == sheet.sheet_id and i.issue_type == "column"
                        ]
                        schemas = {
                            i.target_field.split(".")[0] for i in own if i.target_field
                        }
                        schema = next(iter(schemas)) if len(schemas) == 1 else None
                        if schema and schema not in {
                            "suppliers",
                            "supplier_terms",
                            "payable_fees",
                            "scope_declarations",
                        }:
                            continue
                        for row in rawsheet["rows"]:
                            location = dto.SourceLocation(
                                file_id=sheet.file_id,
                                sheet_id=sheet.sheet_id,
                                row_number=row["row_number"],
                                record_number=row["record_number"],
                                line_start=row["line_start"],
                                line_end=row["line_end"],
                            )
                            cells = tuple(
                                dto.StagedConfigurationCell(
                                    source_column_index=c["column_index"],
                                    source_header=(
                                        sheet.headers[c["column_index"]]
                                        if c["column_index"] < len(sheet.headers)
                                        else ""
                                    ),
                                    raw_value=c["raw"],
                                    kind=c["kind"],
                                    proposed_target_field=next(
                                        (
                                            i.target_field
                                            for i in own
                                            if i.source_location.source_column_index
                                            == c["column_index"]
                                        ),
                                        None,
                                    ),
                                )
                                for c in row["cells"]
                            )
                            staged.append(
                                dto.StagedConfigurationRow(
                                    schema=schema, source_location=location, cells=cells
                                )
                            )
                    ap, arp = self._page(
                        staged,
                        token,
                        actor,
                        summary,
                        [str(b.id), b.mapping_revision, "configuration-analysis"],
                        rows_limit,
                        rows_cursor,
                    )
                    configuration_data = dto.Configurations(
                        suppliers=(),
                        terms=(),
                        fees=(),
                        declarations=(),
                        preview_id=None,
                        preview_digest=None,
                        blocked_row_ids=(),
                        rows_page=arp,
                        analysis_rows=ap,
                        basis="analysis",
                    )
                    result = dto.ImportRead(
                        **self._draft(b, files).model_dump(),
                        quota=self._quota(files),
                        completion_available=bool((b.analysis_json or {}).get("completion")),
                        active_job_id=b.active_job_id,
                        files=page,
                        files_page=paging,
                        source_set=dto.SourceSet(
                            version=b.file_set_version,
                            sealed=b.sealed,
                            accepted_file_ids=tuple(
                                f.id for f in files if f.upload_status == "uploaded"
                            ),
                            digest=content_digest(
                                [
                                    (str(f.id), f.digest)
                                    for f in files
                                    if f.upload_status == "uploaded"
                                ]
                            ),
                        ),
                        allowed_actions=("review_mapping",),
                        preview=None,
                        configurations=configuration_data,
                    )
                    result = result.model_copy(
                        update={
                            "allowed_actions": self._allowed(
                                result.allowed_actions, permissions
                            )
                        }
                    )
                    s.commit()
                    return result
                payload = dict(p.content_json)
                stored_summary = payload["summary"]
                payload["summary"] = {
                    k: v for k, v in stored_summary.items() if k != "digest"
                }
                if content_digest(payload) != p.digest:
                    raise AuthError("SOURCE_INTEGRITY_ERROR", 409)
                self._preview_read_authority(p,permissions)
                items = [
                    dto.PreviewRow.model_validate(r, context={"retained_evidence": True}) for r in p.content_json["rows"]
                ]
                from app.application.import_read_projection import scoped_rows,pinned_sources,preview_aggregates,source_effect_rows
                scope=dto.PreviewScope(file_id=file_id,sheet_id=sheet_id,classification=classification)
                known=p.content_json.get('reviewed_sheets',())
                if file_id and str(file_id) not in {f['file_id'] for f in p.content_json.get('source_files',())}:raise AuthError('RESOURCE_NOT_FOUND',404)
                if sheet_id and str(sheet_id) not in {sh['sheet_id'] for sh in known}:raise AuthError('RESOURCE_NOT_FOUND',404)
                sources=pinned_sources(p.content_json,b.analysis_json)
                aggregates=preview_aggregates(p.content_json,items,sources,scope)
                items=scoped_rows(items,scope)
                rowpage, rp = self._page(
                    items,
                    token,
                    actor,
                    summary,
                    [str(b.id), str(p.id), p.digest, classification, "rows",str(file_id),str(sheet_id),projection],
                    rows_limit,
                    rows_cursor,
                )
                if projection=='source_effect':
                    rowpage=source_effect_rows(rowpage,p.content_json,sources)
                stale = p.mapping_revision != b.mapping_revision
                try:
                    self._bindings(s, b)
                except AuthError:
                    stale = True
                preview = dto.PreviewPage(
                    aggregates=aggregates,
                    mapping_revision=p.mapping_revision,
                    read_set_digest=p.read_set_digest,
                    source_evidence_digest=p.content_json.get('source_evidence_digest'),
                    summary=dto.PreviewSummary.model_validate(stored_summary),
                    rows=rowpage,
                    rows_page=rp,
                    stale=stale,
                )
                if configurations:
                    entries = {
                        "suppliers": [],
                        "supplier_terms": [],
                        "payable_fees": [],
                        "scope_declarations": [],
                    }
                    blocked = []
                    for row in rowpage:
                        if (
                            row.canonical_domain
                            and row.canonical_domain in entries
                            and row.after is None
                        ):
                            blocked.append(row.row_id)
                            continue
                        if row.after is None or row.after.domain not in entries:
                            continue
                        if row.blockers:
                            blocked.append(row.row_id)
                            continue
                        binding = next(
                            r
                            for r in p.content_json["bindings"]
                            if r["sheet_id"] == str(row.source_location.sheet_id)
                        )
                        version_row = s.get(
                            ImportProfileVersion,
                            (UUID(binding["profile_id"]), binding["version"]),
                        )
                        spec = dto.ProfileSpec.model_validate(version_row.spec_json, context={"retained_evidence": True})
                        value = row.after
                        key = (
                            getattr(value, "source_supplier_key", None)
                            or getattr(value, "source_term_key", None)
                            or getattr(value, "source_fee_key", None)
                            or getattr(value, "source_declaration_key", None)
                        )
                        configuration_id = (
                            next(
                                (
                                    r.canonical_id
                                    for r in row.entity_refs
                                    if r.entity == "supplier"
                                ),
                                row.row_id,
                            )
                            if value.domain == "suppliers"
                            else row.target_reserved_or_existing_id or row.row_id
                        )
                        common = dict(
                            canonical_id=configuration_id,
                            version=str(row.row_id),
                            source_identity=dto.SourceIdentity(
                                source_system_key=spec.scope.source_system_key,
                                source_record_key=key,
                            ),
                            expected_before_version=row.expected_version,
                            provenance=row.model_dump()["provenance"],
                            payload=value,
                        )
                        completion = (b.analysis_json or {}).get("completion")
                        committed = next((ref for ref in (completion or {}).get("canonical_references", ())
                                          if ref["row_id"] == str(row.row_id)), None)
                        if committed:
                            common.update(canonical_id=UUID(committed["canonical_id"]),
                                          version=committed.get("canonical_version") or str(row.row_id), state="committed")
                        cls = {
                            "suppliers": dto.SupplierConfiguration,
                            "supplier_terms": dto.TermConfiguration,
                            "payable_fees": dto.FeeConfiguration,
                            "scope_declarations": dto.DeclarationConfiguration,
                        }[value.domain]
                        if value.domain == "supplier_terms":
                            existing = next(
                                (
                                    r
                                    for r in p.content_json["read_set"][
                                        "supplier_terms"
                                    ]
                                    if r["id"] == str(configuration_id)
                                ),
                                None,
                            )
                            common["internal_term_version"] = (
                                existing["version"]
                                if existing
                                else max(
                                    (
                                        r["version"]
                                        for r in p.content_json["read_set"][
                                            "supplier_terms"
                                        ]
                                        if r["supplier_id"] == str(value.supplier_id)
                                        and r["ingredient_id"]
                                        == str(value.ingredient_id)
                                    ),
                                    default=0,
                                )
                                + 1
                            )
                            if committed and committed.get("canonical_version"):
                                common["internal_term_version"] = int(committed["canonical_version"])
                        entries[value.domain].append(cls(**common))
                    configuration_data = dto.Configurations(
                        suppliers=tuple(entries["suppliers"]),
                        terms=tuple(entries["supplier_terms"]),
                        fees=tuple(entries["payable_fees"]),
                        declarations=tuple(entries["scope_declarations"]),
                        preview_id=p.id,
                        preview_digest=p.digest,
                        blocked_row_ids=tuple(blocked),
                        rows_page=rp,
                        stale=stale,
                    )
            result = dto.ImportRead(
                **self._draft(b, files).model_dump(),
                quota=self._quota(files),
                completion_available=bool((b.analysis_json or {}).get("completion")),
                active_job_id=b.active_job_id,
                files=page,
                files_page=paging,
                source_set=dto.SourceSet(
                    version=b.file_set_version,
                    sealed=b.sealed,
                    accepted_file_ids=tuple(
                        f.id for f in files if f.upload_status == "uploaded"
                    ),
                    digest=content_digest(
                        [
                            (str(f.id), f.digest)
                            for f in files
                            if f.upload_status == "uploaded"
                        ]
                    ),
                ),
                allowed_actions=(
                    ("upload", "analyze")
                    if not b.sealed
                    else (
                        ("preview",)
                        if b.status in {"ready_for_preview", "preview_ready", "blocked"}
                        else ("review_mapping",)
                    )
                ),
                preview=preview if include_preview else None,
                configurations=configuration_data,
                review_confirmation=confirmation,
                confirmation_usable=bool(
                    confirmation
                    and preview
                    and not preview.stale
                    and b.active_job_id is None
                    and confirmation.preview_id == preview.summary.preview_id
                    and confirmation.preview_digest == preview.summary.digest
                    and confirmation.mapping_revision == b.mapping_revision
                    and confirmation.file_set_version == b.file_set_version
                    and "import.commit" in permissions
                    and set(preview.summary.required_actions) <= set(permissions)
                ),
            )
            actions = result.allowed_actions
            if (
                preview
                and not preview.stale
                and not preview.summary.blockers
                and set(preview.summary.required_actions) <= set(permissions)
            ):
                actions = (*actions, "confirm_review")
            supported = bool(preview and all(g.canonical_domain in SUPPORTED for g in preview.summary.groups))
            if result.confirmation_usable and supported:
                actions = (*actions, "commit")
            if (b.analysis_json or {}).get("completion"):
                result = result.model_copy(update={"confirmation_usable": False})
                actions = ()
            elif b.active_job_id:
                actions = ()
            elif not b.sealed and not any(f.upload_status == "uploaded" for f in files):
                actions = ("upload",)
            elif b.sealed and b.analysis_json is None and b.status == "failed":
                actions = ("analyze",)
            elif (
                b.sealed
                and b.analysis_json is not None
                and not self._summary(s, b, False).can_preview
            ):
                actions = ("review_mapping",)
            result = result.model_copy(
                update={"allowed_actions": self._allowed(actions, permissions)}
            )
            s.commit()
        if preview and not preview.stale:
            _, current = capture_read_set(
                self.engine,
                result.store_id,
                p.content_json["read_set"]["_captured_schemas"],
            )
            # Checking versions does not recompute or mutate the retained preview.
            with auth_session(self.engine) as s:
                b = self._batch(s, ident, False)
                _, _, permissions = self._authority(
                    s, token, b, "import.read", sensitive=True
                )
                result = result.model_copy(
                    update={
                        "allowed_actions": self._allowed(
                            result.allowed_actions, permissions
                        ),
                        "confirmation_usable": (
                            bool(
                                result.confirmation_usable
                                and confirmation.mapping_revision == b.mapping_revision
                                and "import.commit" in permissions
                                and set(preview.summary.required_actions)
                                <= set(permissions)
                            )
                            if confirmation
                            else False
                        ),
                    }
                )
                p = s.get(ImportPreview, preview.summary.preview_id)
                self._preview_read_authority(p,permissions)
                retired = False
                try:
                    self._bindings(s, b)
                except AuthError:
                    retired = True
                if (
                    current != p.read_set_digest
                    or p.mapping_revision != b.mapping_revision
                    or retired
                ):
                    update = {
                        "confirmation_usable": False,
                        "allowed_actions": tuple(
                            a for a in result.allowed_actions if a not in {"confirm_review", "commit"}
                        ),
                    }
                    if include_preview:
                        update["preview"] = preview.model_copy(update={"stale": True})
                    if configuration_data:
                        update["configurations"] = configuration_data.model_copy(
                            update={"stale": True}
                        )
                    result = result.model_copy(update=update)
                elif "import.commit" not in permissions or not set(
                    preview.summary.required_actions
                ) <= set(permissions):
                    result = result.model_copy(
                        update={
                            "confirmation_usable": False,
                            "allowed_actions": tuple(
                                a
                                for a in result.allowed_actions
                                if a not in {"confirm_review", "commit"}
                            ),
                        }
                    )
                s.commit()
        if result.preview:
            result = result.model_copy(update={"preview": result.preview.model_copy(update={
                "summary": result.preview.summary.model_copy(update={"can_commit": "commit" in result.allowed_actions})
            })})
        return result
