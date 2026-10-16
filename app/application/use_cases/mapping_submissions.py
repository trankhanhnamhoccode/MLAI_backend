"""Pinned full-spec review tasks; N5 remains the only profile decision boundary."""
import json
import hashlib
from bisect import bisect_right
from uuid import UUID, uuid4
from app.repositories.collaboration import CollaborationRepository
from app.application.contracts.auth import AuthError
from app.application.contracts import mapping_submissions as dto, import_mapping as mapping
from app.application.contracts.collaboration import WorkflowError
from app.application.use_cases.collaboration_paging import mutation_headers, page, window
from app.application.use_cases.auth import version
from app.application.use_cases.permission_requests import owners
from app.domain.notifications import NotificationEvent, EventType
from app.infrastructure.auth_crypto import digest
from app.infrastructure.database.auth_session import auth_session
from app.models.collaboration import MappingSubmissionRecord
from app.models.import_staging import ImportBatch, ImportProfile, ImportProfileVersion, ImportFile, ImportBlob
from app.repositories.import_staging import content_digest
from app.repositories import notifications


def drift(row, batch, profile):
    f=row.facts
    checks=(('proposal_revision',profile.proposal_revision),('mapping_revision',batch.mapping_revision),
        ('import_revision',batch.revision),('file_set_version',batch.file_set_version),
        ('lifecycle_revision_at_submission',profile.lifecycle_revision),('expected_active_version',profile.active_version))
    return any(f[k]!=v for k,v in checks) or content_digest(profile.proposal_json.get('spec'))!=f['spec_digest']


def invalidate_submissions(imports, s, actor, store):
    """Explicit caller transaction hook; retained pins never change."""
    for row in CollaborationRepository(s).pending_submissions(store):
        batch=s.get(ImportBatch,row.import_id); profile=s.get(ImportProfile,row.profile_id)
        if drift(row,batch,profile):
            row.state,row.version='stale',str(uuid4())
            imports._audit(s,actor,store,'MAPPING_SUBMISSION_STALE',dict(submission_id=str(row.id),pins=row.facts))


class MappingSubmissions:
    def __init__(self, imports):
        self.imports,self.auth,self.engine,self.clock=imports,imports.auth,imports.engine,imports.clock

    def authority(self,s,token,batch,*,write=False,csrf=None,pinned=None):
        actor,summary,_=self.imports._authority(s,token,batch,'import.read',csrf,sensitive=True)
        required=('mapping.read','mapping.propose') if write else ('mapping.read',)
        if pinned:
            from app.application.use_cases.import_staging import READS
            required+=READS[pinned['schema']]
        self.auth.authorize_in_session(s,token,batch.store_id,required,csrf=csrf)
        return actor,summary

    def _profile(self,s,identity,batch):
        p=CollaborationRepository(s).profile(identity,batch.store_id,batch.id)
        if p is None: raise AuthError('RESOURCE_NOT_FOUND',404)
        return p

    def _row(self,s,identity,store,actor,summary):
        row=CollaborationRepository(s).submission(identity,store)
        if row is None or summary.role!='OWNER' and row.submitted_by_user_id!=actor.user_id:
            raise AuthError('RESOURCE_NOT_FOUND',404)
        return row

    def _dto(self,s,row,batch,profile,actor,summary):
        stale=row.state=='submitted' and drift(row,batch,profile)
        state='stale' if stale else row.state
        retired=False
        if row.reviewed_version:
            v=s.get(ImportProfileVersion,(profile.id,row.reviewed_version)); retired=v is None or v.retired
        reasons=[]
        if state!='submitted': reasons.append('MAPPING_SUBMISSION_STALE' if state=='stale' else 'MAPPING_SUBMISSION_STATE_CONFLICT')
        if batch.active_job_id: reasons.append('IMPORT_JOB_ACTIVE')
        if (batch.analysis_json or {}).get('completion'): reasons.append('IMPORT_ALREADY_COMMITTED')
        eligible=not reasons
        actions=('approve_activate','reject','request_changes','withdraw') if summary.role=='OWNER' else ('withdraw',)
        return dto.MappingSubmission(submission_id=row.id,store_id=row.store_id,profile_id=row.profile_id,
            import_id=row.import_id,submitted_by_user_id=row.submitted_by_user_id,submitted_at=row.submitted_at,
            version=row.version,state=state,decision=row.decision,**{k:v for k,v in row.facts.items() if k not in ('source','warnings','missing_fields')},
            review_eligibility=dto.Eligibility(eligible=eligible,reason_codes=reasons),
            current_profile=dto.CurrentProfile(lifecycle_revision=profile.lifecycle_revision,active_version=profile.active_version,reviewed_version_retired=retired),
            allowed_actions=actions if eligible else ())

    @staticmethod
    def _source(batch, sheet_id):
        source = next((x for x in batch.analysis_json['sources'] if x['sheet_id'] == str(sheet_id)), None)
        if source is None:
            raise AuthError('SOURCE_INTEGRITY_ERROR', 409)
        return source

    def _evidence(self, batch, sheet):
        source = self._source(batch, sheet.sheet_id)
        offsets = [0]
        for row in source['rows']:
            offsets.append(offsets[-1] + len(row['cells']))
        # Captured source rows/bytes are immutable under the existing DB guards.
        # Retain only the display index and pins; do not duplicate all raw cells.
        evidence = dict(source_digest=content_digest(source), headers=list(sheet.headers),
                        row_offsets=offsets, total_count=offsets[-1])
        warnings = [n for n in batch.analysis_json.get('warnings', ())
                    if not n.get('source_location') or n['source_location'].get('sheet_id') == str(sheet.sheet_id)]
        return evidence, warnings

    @staticmethod
    def _snapshot(projection, batch, profile):
        return [projection.model_dump(mode='json'), batch.revision, batch.mapping_revision,
                batch.file_set_version, profile.proposal_revision,
                profile.lifecycle_revision, profile.active_version]

    def _evidence_page(self, row, batch, projection, profile, token, authority, limit, cursor):
        evidence = row.evidence
        fingerprint = version([evidence, self._snapshot(projection, batch, profile)])
        start, end, meta = window(self.auth, token, f'mapping-evidence:{row.id}',
            evidence['total_count'], fingerprint, authority, [str(row.store_id), str(row.id)], limit, cursor)
        source = self._source(batch, row.facts['sheet_id'])
        offsets = evidence['row_offsets']
        cells, warnings = [], list(row.facts['warnings'])
        index = max(0, bisect_right(offsets, start) - 1)
        while index < len(source['rows']) and offsets[index] < end:
            record = source['rows'][index]
            for cell in record['cells'][max(0, start - offsets[index]):end - offsets[index]]:
                raw = cell.get('raw')
                labels = evidence['headers']
                label = labels[cell['column_index']] if cell['column_index'] < len(labels) else None
                location = mapping.SourceLocation(file_id=row.facts['file_id'], sheet_id=row.facts['sheet_id'],
                    row_number=record['row_number'], source_column_index=cell['column_index'],
                    record_number=record.get('record_number'), line_start=record.get('line_start'), line_end=record.get('line_end'))
                from app.application.import_read_projection import source_evidence_cell
                projected,partial=source_evidence_cell(cell,label,location)
                if partial:
                    warnings.append(mapping.Notice(code='SOURCE_CELL_DISPLAY_UNAVAILABLE',severity='WARNING',
                        message='Source display exceeds 200 characters.',source_location=location).model_dump(mode='json'))
                cells.append(projected)
            index += 1
        return tuple(cells), warnings, meta

    def mutate(self,token,identity,body,key,match,csrf):
        kd,expected=mutation_headers(key,match,cas=True)
        fp=digest(json.dumps([body.model_dump(mode='json'),match],sort_keys=True))
        with auth_session(self.engine) as s:
            initial=self.imports._batch(s,identity,lock=False)
            actor,summary=self.authority(s,token,initial,write=True,csrf=csrf or '')
            batch=self.imports._batch(s,identity)
            if summary.role!='OWNER' and batch.actor_id!=actor.user_id: raise AuthError('RESOURCE_NOT_FOUND',404)
            op=f'POST:imports/{identity}/mapping-submissions'
            old=self.imports._old(s,actor,batch.store_id,op,kd,fp)
            if old:
                retained=s.get(MappingSubmissionRecord,UUID(old['submission_id']))
                if retained is None or retained.import_id!=identity: raise AuthError('RESOURCE_NOT_FOUND',404)
                self.authority(s,token,batch,write=True,csrf=csrf or '',pinned=retained.spec)
                s.commit(); return dto.MappingSubmission.model_validate(old),expected
            if batch.revision!=expected: raise AuthError('IMPORT_REVISION_CONFLICT',412)
            if isinstance(body,dto.WithdrawMapping):
                row=self._row(s,body.submission_id,batch.store_id,actor,summary)
                if row.import_id!=identity: raise AuthError('RESOURCE_NOT_FOUND',404)
                profile=self._profile(s,row.profile_id,batch)
                self.authority(s,token,batch,write=True,csrf=csrf or '',pinned=row.spec)
                if row.state!='submitted': raise AuthError('MAPPING_SUBMISSION_STATE_CONFLICT',409)
                if row.version!=body.expected_submission_version or drift(row,batch,profile): raise AuthError('MAPPING_SUBMISSION_STALE',409)
                row.state,row.version='withdrawn',str(uuid4())
                self.imports._audit(s,actor,batch.store_id,'MAPPING_SUBMISSION_WITHDRAWN',dict(submission_id=str(row.id),reason=body.reason,pins=row.facts))
            else:
                profile=self._profile(s,body.profile_id,batch)
                invalidate_submissions(self.imports,s,actor,batch.store_id)
                if body.proposal_revision!=profile.proposal_revision or body.mapping_revision!=batch.mapping_revision: raise AuthError('MAPPING_SUBMISSION_STALE',409)
                oldrow=CollaborationRepository(s).live_submission(profile.id,locked=False)
                if oldrow:
                    raise WorkflowError('MAPPING_ALREADY_SUBMITTED',existing_submission_id=oldrow.id if summary.role=='OWNER' or oldrow.submitted_by_user_id==actor.user_id else None)
                missing=tuple(profile.proposal_json.get('missing_fields',()))
                blockers=[]
                if not batch.sealed or not batch.analysis_json: blockers.append('IMPORT_NOT_ANALYZED')
                if batch.active_job_id: blockers.append('IMPORT_JOB_ACTIVE')
                if (batch.analysis_json or {}).get('completion'): blockers.append('IMPORT_ALREADY_COMMITTED')
                if missing or not profile.proposal_json.get('spec'): blockers.append('UNRESOLVED_REQUIRED_FIELDS')
                if blockers: raise WorkflowError('REVIEW_NOT_READY',missing_fields=missing,reason_codes=blockers)
                spec=mapping.ProfileSpec.model_validate(profile.proposal_json['spec'])
                self.authority(s,token,batch,write=True,csrf=csrf or '',pinned=spec.model_dump(mode='json'))
                issues=[i for i in self.imports._issues(batch) if i.sheet_id==profile.sheet_id]
                from app.application.import_completion import review_blockers
                blockers = review_blockers(sealed=batch.sealed, analyzed=bool(batch.analysis_json),
                    job_active=bool(batch.active_job_id), completed=bool((batch.analysis_json or {}).get('completion')),
                    spec=spec, missing=missing, issues=issues)
                if blockers: raise WorkflowError('REVIEW_NOT_READY',missing_fields=missing,reason_codes=tuple(sorted(set(blockers))))
                sheet=next(sh for sh in self.imports._sheets(batch) if sh.sheet_id==profile.sheet_id)
                file=s.get(ImportFile,sheet.file_id); blob=s.get(ImportBlob,(batch.store_id,file.digest))
                if file.import_id!=batch.id or blob is None or 'sha256:'+hashlib.sha256(blob.content).hexdigest()!=file.digest:
                    raise AuthError('SOURCE_INTEGRITY_ERROR',409)
                evidence,warnings=self._evidence(batch,sheet)
                now=self.clock(); row=MappingSubmissionRecord(id=uuid4(),store_id=batch.store_id,profile_id=profile.id,import_id=batch.id,
                    submitted_by_user_id=actor.user_id,submitted_at=now,state='submitted',version=str(uuid4()),decision=None,reviewed_version=None,
                    spec=spec.model_dump(mode='json'),evidence=evidence,facts=dict(sheet_id=str(sheet.sheet_id),file_id=str(file.id),reason=body.reason,
                        proposal_revision=profile.proposal_revision,mapping_revision=batch.mapping_revision,import_revision=batch.revision,file_set_version=batch.file_set_version,
                        lifecycle_revision_at_submission=profile.lifecycle_revision,spec_digest=content_digest(spec.model_dump(mode='json')),expected_active_version=profile.active_version,
                        source=dict(file_id=str(file.id),filename=file.filename,sheet_id=str(sheet.sheet_id),sheet_name=sheet.name,
                            source_system_key=spec.scope.source_system_key,report_type=spec.scope.report_type,schema_signature=sheet.schema_signature,evidence_references=spec.source_provenance.evidence_references),
                        warnings=warnings,missing_fields=missing))
                s.add(row)
                aid=self.imports._audit(s,actor,batch.store_id,'MAPPING_SUBMITTED',dict(submission_id=str(row.id),pins=row.facts))
                recipients=owners(s,batch.store_id)
                if recipients: notifications.enqueue(s,NotificationEvent(aid,EventType.MAPPING_SUBMITTED,now,row.id,recipients,store_id=batch.store_id,object_revision=row.version))
            result=self._dto(s,row,batch,profile,actor,summary)
            self.imports._save(s,actor,batch.store_id,op,kd,fp,result); s.commit()
            return result,batch.revision

    def list(self,token,store,state=None,file_id=None,import_id=None,limit=50,cursor=None):
        with auth_session(self.engine) as s:
            actor,summary,_=self.auth.authorize_in_session(s,token,store,('import.read','mapping.read'))
            if import_id:
                batch=self.imports._batch(s,import_id,lock=False)
                if batch.store_id!=store or summary.role!='OWNER' and batch.actor_id!=actor.user_id: raise AuthError('RESOURCE_NOT_FOUND',404)
            if file_id:
                file=s.get(ImportFile,file_id)
                if file is None or file.store_id!=store: raise AuthError('RESOURCE_NOT_FOUND',404)
                batch=self.imports._batch(s,file.import_id,lock=False)
                if summary.role!='OWNER' and batch.actor_id!=actor.user_id: raise AuthError('RESOURCE_NOT_FOUND',404)
            all_items, snapshots = [], []
            rows=CollaborationRepository(s).submissions(store,None if summary.role=='OWNER' else actor.user_id,file_id,import_id)
            for row in rows:
                batch=self.imports._batch(s,row.import_id); profile=self._profile(s,row.profile_id,batch)
                # A forbidden row in the discovery scope denies the whole response.
                # State/page filtering must not silently remove it or expose counts.
                self.authority(s,token,batch,pinned=row.spec)
                item = self._dto(s,row,batch,profile,actor,summary)
                all_items.append(item)
                snapshots.append(self._snapshot(item,batch,profile))
            items=tuple(i for i in all_items if (i.state==state if state else summary.role!='OWNER' or i.state=='submitted' and i.review_eligibility.eligible))
            items,meta=page(self.auth,token,f'mapping-queue:{store}',items,summary.authorization_version,[str(store),state,str(file_id),str(import_id)],limit,cursor,
                fingerprint_facts=snapshots)
            s.commit(); return dto.MappingQueue(items=items),meta

    def detail(self,token,store,identity,limit=20,cursor=None):
        with auth_session(self.engine) as s:
            actor,summary,_=self.auth.authorize_in_session(s,token,store,('import.read','mapping.read'))
            row=self._row(s,identity,store,actor,summary); batch=self.imports._batch(s,row.import_id); profile=self._profile(s,row.profile_id,batch)
            self.authority(s,token,batch,pinned=row.spec)
            from app.application.import_analysis import receipt_sensitive_reads
            spec=mapping.ProfileSpec.model_validate(row.spec)
            required=receipt_sensitive_reads((batch.analysis_json or {}).get('sources',()),
                {str(row.facts['sheet_id']):spec.field_bindings})
            self.auth.authorize_in_session(s,token,store,tuple(sorted(required)))
            projection=self._dto(s,row,batch,profile,actor,summary)
            cells,warnings,meta=self._evidence_page(row,batch,projection,profile,token,summary.authorization_version,limit,cursor)
            data=mapping.MappingReviewDetail(submission=projection,source=row.facts['source'],spec=row.spec,warnings=warnings,missing_fields=row.facts['missing_fields'],
                evidence=mapping.ReviewEvidence(cells=cells,next_cursor=meta['pagination']['next_cursor'],total_count=meta['pagination']['total_count']))
            s.commit(); return data

    def decision_target(self,s,profile,batch,body,actor,summary):
        if body.decision=='retire': return None
        identity=body.submission_id
        if identity:
            row=self._row(s,identity,batch.store_id,actor,summary)
            if row.profile_id!=profile.id: raise AuthError('RESOURCE_NOT_FOUND',404)
            if row.state=='stale': raise AuthError('MAPPING_SUBMISSION_STALE',409)
            if row.state!='submitted': raise AuthError('MAPPING_SUBMISSION_STATE_CONFLICT',409)
            if row.version!=body.expected_submission_version: raise AuthError('MAPPING_SUBMISSION_STALE',409)
        else:
            row=CollaborationRepository(s).live_submission(profile.id)
        if row:
            if not self._dto(s,row,batch,profile,actor,summary).review_eligibility.eligible: raise AuthError('MAPPING_SUBMISSION_STALE',409)
        elif body.decision=='request_changes': raise AuthError('MAPPING_SUBMISSION_STATE_CONFLICT',409)
        return row

    def finish_decision(self,s,row,profile,batch,body,actor,summary,decision_id,audit_id,now,approved):
        row.state={'approve_activate':'approved','reject':'rejected','request_changes':'changes_requested'}[body.decision]
        row.version=str(uuid4()); row.reviewed_version=approved
        row.decision=dto.MappingDecision(decision_id=decision_id,decision=body.decision,actor_user_id=actor.user_id,reason=body.reason,decided_at=now).model_dump(mode='json')
        notifications.enqueue(s,NotificationEvent(audit_id,EventType('mapping_submission.'+row.state),now,row.id,(row.submitted_by_user_id,),store_id=row.store_id,object_revision=row.version,decision_id=decision_id))
        return self._dto(s,row,batch,profile,actor,summary)
