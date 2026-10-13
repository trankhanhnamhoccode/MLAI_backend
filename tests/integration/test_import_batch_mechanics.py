"""Real guarded PostgreSQL/HTTP batch accounting; no parser/provider execution."""

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier, Event
from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.application.contracts import import_mapping as dto
from app.infrastructure import import_suggestions
from app.models import StoreMembership
from app.models.auth import MembershipGrant
from app.models.import_staging import ImportBatch, ImportBlob, ImportFile, ImportJob
from tests.integration.test_import_staging import env, imp, post

MIB = 1024 * 1024


@pytest.fixture(autouse=True)
def forbid_provider(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("Batch mechanics must not call the provider")

    monkeypatch.setattr(import_suggestions, "suggest_sheet", forbidden)


def draft(imp):
    response = post(
        imp, f"/stores/{imp[1].store_id}/imports", {"data_date": "2026-10-10"}
    )
    assert response.status_code == 201
    return response.json()["data"]["import_id"]


def upload(imp, ident, contents, *, ids=None, key=None, names=None):
    ids = ids or [str(uuid4()) for _ in contents]
    names = names or ["synthetic.csv"] * len(contents)
    return imp[0][5].post(
        f"/api/v1/imports/{ident}/files",
        headers={**imp[3], "Idempotency-Key": key or str(uuid4())},
        files=[("files[]", (name, content, "application/octet-stream"))
               for name, content in zip(names, contents)],
        data={"client_file_ids[]": ids},
    )


def read(imp, ident, *, limit=50):
    response = imp[0][5].get(f"/api/v1/imports/{ident}?files_limit={limit}")
    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert response.headers["etag"] == '"' + data["import_revision"] + '"'
    return data


def assert_quota(imp, ident, count, size, *, limit=50):
    data = read(imp, ident, limit=limit)
    assert data["quota"] == {
        "accepted_file_count": count,
        "accepted_total_bytes": size,
        "remaining_file_slots": 20 - count,
        "remaining_bytes": 100 * MIB - size,
    }
    assert data["file_count"] == len(data["source_set"]["accepted_file_ids"]) == count
    assert data["file_set_version"] == data["source_set"]["version"]
    with Session(imp[0][1]) as fresh:
        rows = fresh.scalars(select(ImportFile).where(ImportFile.import_id == UUID(ident))).all()
        accepted = [r for r in rows if r.upload_status == "uploaded"]
        batch = fresh.get(ImportBatch, UUID(ident))
        assert len(accepted) == count and sum(r.size for r in accepted) == size
        assert batch.file_set_version == data["file_set_version"]
        assert batch.revision == data["import_revision"]
    return data


def accepted_items(response):
    return response.json()["data"]["items"]


def analyze_body(data):
    return dto.AnalyzeRequest(
        file_set_version=data["file_set_version"],
        accepted_file_ids=data["source_set"]["accepted_file_ids"],
        acknowledged_rejected_client_file_ids=[
            f["client_file_id"] for f in data["files"] if f["upload_status"] == "rejected"
        ],
    )


def test_multicall_8_7_6_accepts_five_and_rejects_one(imp):
    ident = draft(imp)
    for count in (8, 7):
        assert upload(imp, ident, [b"a\n"] * count).status_code == 200
    response = upload(imp, ident, [b"a\n"] * 6)
    assert response.status_code == 200
    items = accepted_items(response)
    assert [i["upload_status"] for i in items] == ["uploaded"] * 5 + ["rejected"]
    assert items[-1]["error"]["code"] == "RESOURCE_LIMIT_EXCEEDED"
    assert_quota(imp, ident, 20, 40)


def test_18_two_valid_one_invalid_and_required_rejected_ack(imp):
    ident = draft(imp)
    assert upload(imp, ident, [b"a\n"] * 18).status_code == 200
    response = upload(imp, ident, [b"a\n", b"a\n", b"invalid"],
                      names=["a.csv", "b.csv", "bad.exe"])
    assert response.status_code == 200
    items = accepted_items(response)
    assert [i["upload_status"] for i in items] == ["uploaded", "uploaded", "rejected"]
    assert items[-1]["error"]["code"] == "RESOURCE_LIMIT_EXCEEDED"
    data = assert_quota(imp, ident, 20, 40)
    body = analyze_body(data)
    bad = body.model_copy(update={"acknowledged_rejected_client_file_ids": ()})
    result = post(imp, f"/imports/{ident}/analyze", bad.model_dump(mode="json"),
                  match=data["import_revision"])
    assert result.status_code == 422
    assert not read(imp, ident)["source_set"]["sealed"]
    result = post(imp, f"/imports/{ident}/analyze", body.model_dump(mode="json"),
                  match=data["import_revision"])
    assert result.status_code == 202
    sealed = assert_quota(imp, ident, 20, 40)
    assert sealed["source_set"]["sealed"]
    assert sealed["file_set_version"] == data["file_set_version"]


def bytes_file(size):
    return b"a\n" + b"x" * (size - 2)


@pytest.mark.parametrize("candidate_sizes,expected", [([MIB, MIB], [True, False]),
                                                    ([2 * MIB, MIB], [False, True])])
def test_byte_boundary_and_later_small_file_fits(imp, candidate_sizes, expected):
    ident = draft(imp)
    twenty = bytes_file(20 * MIB)
    assert upload(imp, ident, [twenty] * 4 + [bytes_file(19 * MIB)]).status_code == 200
    assert_quota(imp, ident, 5, 99 * MIB)
    response = upload(imp, ident, [bytes_file(n) for n in candidate_sizes])
    assert response.status_code == 200
    assert [i["upload_status"] == "uploaded" for i in accepted_items(response)] == expected
    assert_quota(imp, ident, 6, 100 * MIB)


def test_dedup_replays_rejected_pagination_and_parse_failed_accounting(imp):
    ident = draft(imp)
    key, client = str(uuid4()), str(uuid4())
    first = upload(imp, ident, [b"a\n"], key=key, ids=[client])
    original = assert_quota(imp, ident, 1, 2)
    replay = upload(imp, ident, [b"a\n"], key=key, ids=[client])
    assert replay.json()["data"] == first.json()["data"]
    same = assert_quota(imp, ident, 1, 2)
    assert same["import_revision"] == original["import_revision"]
    assert same["file_set_version"] == original["file_set_version"]
    new_key = upload(imp, ident, [b"a\n"], ids=[client])
    assert new_key.status_code == 200
    next_state = assert_quota(imp, ident, 1, 2)
    assert next_state["file_set_version"] != original["file_set_version"]
    assert next_state["import_revision"] != original["import_revision"]
    assert upload(imp, ident, [b"a\n"]).status_code == 200
    with Session(imp[0][1]) as fresh:
        assert fresh.scalar(select(func.count()).select_from(ImportBlob)) == 1
        row = fresh.scalar(select(ImportFile).where(ImportFile.import_id == UUID(ident)))
        row.parse_status = "failed"
        fresh.commit()
    before_bad = assert_quota(imp, ident, 2, 4)
    bad = upload(imp, ident, [b"invalid"] * 3, names=["bad.exe"] * 3)
    assert bad.status_code == 422 and bad.json()["error"]["code"] == "UPLOAD_REJECTED"
    paged = assert_quota(imp, ident, 2, 4, limit=1)
    assert len(paged["files"]) == 1 and paged["files_page"]["total_count"] == 5
    assert paged["file_set_version"] != before_bad["file_set_version"]


def test_request_guards_and_conflicts_rollback_all_items(imp):
    ident = draft(imp)
    client = str(uuid4())
    assert upload(imp, ident, [b"a\n"], ids=[client]).status_code == 200
    before = assert_quota(imp, ident, 1, 2)
    assert upload(imp, ident, [b"a\n"] * 21).status_code == 413
    # A staged valid first file must roll back when the later client identity conflicts.
    assert upload(imp, ident, [b"new\n", b"changed\n"], ids=[str(uuid4()), client]).status_code == 409
    after = assert_quota(imp, ident, 1, 2)
    assert after["file_set_version"] == before["file_set_version"]


@pytest.mark.parametrize("byte_boundary", [False, True])
def test_concurrent_i02_cannot_exceed_count_or_bytes(imp, byte_boundary):
    ident = draft(imp)
    if byte_boundary:
        twenty = bytes_file(20 * MIB)
        assert upload(imp, ident, [twenty] * 4 + [bytes_file(19 * MIB)]).status_code == 200
        content, count, size = bytes_file(MIB), 6, 100 * MIB
    else:
        assert upload(imp, ident, [b"a\n"] * 19).status_code == 200
        content, count, size = b"a\n", 20, 40
    token = imp[0][5].cookies.get("__Host-shelfcash_session")
    barrier = Barrier(2)

    def run():
        barrier.wait(timeout=10)
        return imp[2].upload(token, UUID(ident), [(uuid4(), "a.csv", content)],
                             str(uuid4()), imp[3]["X-CSRF-Token"])

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(run) for _ in range(2)]
        results = [f.result(timeout=30) for f in futures]
    assert sorted(r.items[0].upload_status for r in results) == ["rejected", "uploaded"]
    assert_quota(imp, ident, count, size)


@pytest.mark.parametrize("seal_first", [False, True])
def test_upload_analyze_race_fenced_at_actual_database_batch_lock(imp, seal_first, monkeypatch):
    from app.application.contracts.auth import AuthError

    ident = draft(imp)
    first_key, client = str(uuid4()), str(uuid4())
    first = upload(imp, ident, [b"a\n"], key=first_key, ids=[client])
    before = assert_quota(imp, ident, 1, 2)
    token = imp[0][5].cookies.get("__Host-shelfcash_session")
    acquired, release, attempted = Event(), Event(), Event()
    original = imp[2]._batch

    def batch(session, batch_id, lock=True):
        if lock and not acquired.is_set():
            row = original(session, batch_id, lock)
            acquired.set()
            assert release.wait(10)
            return row
        if not lock and acquired.is_set():
            attempted.set()
        return original(session, batch_id, lock)

    monkeypatch.setattr(imp[2], "_batch", batch)

    def seal():
        return imp[2].analyze(token, UUID(ident), analyze_body(before), str(uuid4()),
                              '"' + before["import_revision"] + '"', imp[3]["X-CSRF-Token"])

    def add():
        return imp[2].upload(token, UUID(ident), [(uuid4(), "b.csv", b"b\n")],
                             str(uuid4()), imp[3]["X-CSRF-Token"])

    with ThreadPoolExecutor(max_workers=2) as pool:
        winner = pool.submit(seal if seal_first else add)
        assert acquired.wait(10)
        loser = pool.submit(add if seal_first else seal)
        try:
            assert attempted.wait(10) and not loser.done()
        finally:
            release.set()
        winner.result(timeout=20)
        with pytest.raises(AuthError) as error:
            loser.result(timeout=20)
    assert error.value.code == ("IMPORT_STATE_CONFLICT" if seal_first else "IMPORT_REVISION_CONFLICT")
    after = assert_quota(imp, ident, 1 if seal_first else 2, 2 if seal_first else 4)
    assert after["source_set"]["sealed"] == seal_first
    if seal_first:
        replay = upload(imp, ident, [b"a\n"], key=first_key, ids=[client])
        assert replay.status_code == 200 and replay.json()["data"] == first.json()["data"]
        assert read(imp, ident)["import_revision"] == after["import_revision"]


def test_reader_refreshes_batch_metadata_after_upload_during_authorization(imp, monkeypatch):
    ident = draft(imp)
    assert upload(imp, ident, [b"a\n"]).status_code == 200
    token = imp[0][5].cookies.get("__Host-shelfcash_session")
    observed, resume = Event(), Event()
    original = imp[2]._authority

    def gate(s, session_token, batch, action, *args, **kwargs):
        if action == "import.read" and not observed.is_set():
            observed.set()
            assert resume.wait(10)
        return original(s, session_token, batch, action, *args, **kwargs)

    monkeypatch.setattr(imp[2], "_authority", gate)
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(imp[2].read, token, UUID(ident), 1)
        assert observed.wait(10)
        try:
            result = upload(imp, ident, [b"b\n"])
            assert result.status_code == 200
        finally:
            resume.set()
        data = future.result(timeout=20)
    assert data.file_set_version == result.json()["data"]["file_set_version"]
    assert data.import_revision == result.json()["data"]["import_revision"]
    assert data.quota.accepted_file_count == data.file_count == 2
    assert data.quota.accepted_total_bytes == 4


def test_quota_read_has_current_rights_store_isolation_and_no_import_writes(imp, monkeypatch):
    ident = draft(imp)
    assert upload(imp, ident, [b"a\n"]).status_code == 200
    from app.application.use_cases import import_staging as module
    from app.models.import_staging import ImportReceipt, ImportAudit

    def no_compute(*args, **kwargs):
        raise AssertionError("GET must not parse, execute jobs or compute preview")

    monkeypatch.setattr(module, "parse_source", no_compute)
    monkeypatch.setattr(imp[2], "run_one", no_compute)
    monkeypatch.setattr(module, "make_preview", no_compute)
    with Session(imp[0][1]) as s:
        b = s.get(ImportBatch, UUID(ident))
        snapshot = (b.revision, b.file_set_version, b.sealed)
        counts = [s.scalar(select(func.count()).select_from(cls))
                  for cls in (ImportFile, ImportBlob, ImportJob, ImportReceipt, ImportAudit)]
        member = s.scalar(select(StoreMembership).where(StoreMembership.store_id == imp[1].store_id))
        member.role = "STAFF"
        s.add(MembershipGrant(membership_id=member.id, permission="import.read"))
        s.commit()
    assert_quota(imp, ident, 1, 2)
    assert read(imp, ident)["allowed_actions"] == []
    with Session(imp[0][1]) as fresh:
        b = fresh.get(ImportBatch, UUID(ident))
        assert (b.revision, b.file_set_version, b.sealed) == snapshot
        assert [fresh.scalar(select(func.count()).select_from(cls))
                for cls in (ImportFile, ImportBlob, ImportJob, ImportReceipt, ImportAudit)] == counts
        grant = fresh.scalar(select(MembershipGrant))
        fresh.delete(grant)
        fresh.commit()
    assert imp[0][5].get(f"/api/v1/imports/{ident}").status_code == 403
    assert imp[0][5].get(f"/api/v1/imports/{uuid4()}").status_code == 404
