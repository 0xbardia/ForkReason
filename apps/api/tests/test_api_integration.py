"""API and worker integration tests.

These run against a real database (PostgreSQL when `TEST_DATABASE_URL` is set,
otherwise SQLite) so migrations, the durable queue, recovery, and idempotency are
exercised rather than mocked (spec FR-N-002).
"""

from __future__ import annotations

import os
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "apps" / "api"))

# Point the app at an isolated database before any module imports Settings.
TEST_DB_URL = os.environ.get(
    "TEST_DATABASE_URL", f"sqlite:///{ROOT / '_test_forkreason.db'}"
)
os.environ["DATABASE_URL"] = TEST_DB_URL
os.environ.setdefault("APP_ENV", "test")
os.environ.setdefault("SNAPSHOT_DIR", str(ROOT / "_test_snapshots"))
os.environ.setdefault("GITHUB_TOKEN", "")

from fastapi.testclient import TestClient  # noqa: E402

from forkreason import db as db_module  # noqa: E402
from forkreason.config import get_settings  # noqa: E402
from forkreason.jobs import queue as q  # noqa: E402
from forkreason.jobs.profile_store import ProfileStore  # noqa: E402
from forkreason.main import app  # noqa: E402
from forkreason.models import Base  # noqa: E402


def _fresh_db() -> None:
    db_module.reset_engine()
    engine = db_module.get_engine()
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


@pytest.fixture()
def client() -> TestClient:
    _fresh_db()
    return TestClient(app)


@pytest.fixture()
def session():
    db_module.reset_engine()
    engine = db_module.get_engine()
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    factory = db_module.get_session_factory()
    s = factory()
    try:
        yield s
    finally:
        s.close()


# --- health --------------------------------------------------------------


def test_health_is_liveness_only(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_ready_reports_database(client: TestClient) -> None:
    response = client.get("/ready")
    assert response.status_code == 200
    assert response.json()["database"] is True


def test_every_response_carries_a_request_id(client: TestClient) -> None:
    response = client.get("/health")
    assert response.headers.get("X-Request-ID")


def test_incoming_request_id_is_preserved(client: TestClient) -> None:
    response = client.get("/health", headers={"X-Request-ID": "abc123"})
    assert response.headers["X-Request-ID"] == "abc123"


def test_security_header_is_present(client: TestClient) -> None:
    assert client.get("/health").headers.get("X-Content-Type-Options") == "nosniff"


def test_public_config_has_no_secrets(client: TestClient) -> None:
    body = client.get("/api/v1/config").text.lower()
    assert "token" not in body
    assert "password" not in body
    assert "secret" not in body


# --- repository validation ------------------------------------------------


@pytest.mark.parametrize(
    "payload",
    [
        {"origin": "", "target": "a/b"},
        {"origin": "a/b"},
        {"origin": "https://gitlab.com/a/b", "target": "a/b"},
        {"origin": "a/b; id", "target": "c/d"},
        {"origin": "javascript:alert(1)", "target": "c/d"},
    ],
)
def test_invalid_repository_input_is_rejected(client: TestClient, payload: dict) -> None:
    response = client.post("/api/v1/repositories/validate", json=payload)
    assert response.status_code in (400, 422)
    body = response.json()
    assert "error" in body or "fields" in body


def test_identical_repositories_are_rejected(client: TestClient) -> None:
    response = client.post(
        "/api/v1/repositories/validate", json={"origin": "a/b", "target": "a/b"}
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "identical_repositories"


def test_validation_error_never_echoes_raw_input(client: TestClient) -> None:
    payload = "https://github.com/a/b; DROP TABLE cases;--"
    response = client.post(
        "/api/v1/repositories/validate", json={"origin": payload, "target": "c/d"}
    )
    body = response.text
    assert "DROP TABLE" not in body, "user input was reflected into the response"


def test_missing_fields_return_validation_error(client: TestClient) -> None:
    response = client.post("/api/v1/repositories/validate", json={})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_failed"


# --- analysis jobs --------------------------------------------------------


def _enqueue(session, suffix: str = "a") -> object:
    from forkreason.models import RepositorySnapshot

    for i in (1, 2):
        sid = f"snap{i}{suffix}"
        session.add(
            RepositorySnapshot(
                id=sid,
                owner="acme",
                name=f"repo{i}{suffix}",
                full_name=f"acme/repo{i}{suffix}",
                commit_sha=f"{i}" * 40,
                default_branch="main",
                description="",
                is_fork=False,
                size_bytes=100,
                file_count=1,
            )
        )
    session.flush()
    job, _ = q.enqueue_job(
        session,
        job_id=f"job_{suffix}",
        origin_snapshot_id=f"snap1{suffix}",
        target_snapshot_id=f"snap2{suffix}",
        origin_full_name="acme/repo1",
        target_full_name="acme/repo2",
        origin_commit="1" * 40,
        target_commit="2" * 40,
        idempotency_key=f"idem_{suffix}",
    )
    return job


def test_enqueue_then_progress_is_visible(session) -> None:
    job = _enqueue(session, "p1")
    client = TestClient(app)
    response = client.get(f"/api/v1/analyses/{job.id}")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "queued"
    assert len(body["stages"]) == 8
    assert body["stages_complete"] == 0
    # No invented percentage anywhere in the payload.
    assert "%" not in response.text


def test_unknown_job_returns_404(client: TestClient) -> None:
    response = client.get("/api/v1/analyses/does-not-exist")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "job_not_found"


def test_idempotent_enqueue_does_not_duplicate(session) -> None:
    from forkreason.models import RepositorySnapshot

    for i in (1, 2):
        session.add(
            RepositorySnapshot(
                id=f"d{i}",
                owner="acme",
                name=f"d{i}",
                full_name=f"acme/d{i}",
                commit_sha=str(i) * 40,
                default_branch="main",
                size_bytes=10,
                file_count=1,
            )
        )
    session.flush()
    kwargs = dict(
        origin_snapshot_id="d1",
        target_snapshot_id="d2",
        origin_full_name="acme/d1",
        target_full_name="acme/d2",
        origin_commit="1" * 40,
        target_commit="2" * 40,
        idempotency_key="same-key",
    )
    first, created_first = q.enqueue_job(session, job_id="job-x", **kwargs)
    second, created_second = q.enqueue_job(session, job_id="job-y", **kwargs)
    assert created_first is True
    assert created_second is False
    assert first.id == second.id


def test_cancel_unknown_job_returns_404(client: TestClient) -> None:
    response = client.post("/api/v1/analyses/nope/cancel")
    assert response.status_code == 404


def test_cancel_queued_job_finishes_immediately(session) -> None:
    job = _enqueue(session, "c1")
    job_id = job.id
    client = TestClient(app)
    response = client.post(f"/api/v1/analyses/{job_id}/cancel")
    assert response.status_code == 202
    assert response.json()["status"] == "cancelled"


def test_cancel_finished_job_conflicts(session) -> None:
    job = _enqueue(session, "c2")
    job.status = "succeeded"
    session.commit()
    client = TestClient(app)
    response = client.post(f"/api/v1/analyses/{job.id}/cancel")
    assert response.status_code == 409


def test_manifest_requires_finished_analysis(session) -> None:
    job = _enqueue(session, "m1")
    client = TestClient(app)
    response = client.get(f"/api/v1/analyses/{job.id}/manifest")
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "analysis_not_finished"


# --- queue mechanics ------------------------------------------------------


def test_claim_marks_job_running(session) -> None:
    job = _enqueue(session, "q1")
    with q.claim_job(session, "test-worker") as claimed:
        assert claimed is not None
        assert claimed.id == job.id
        assert claimed.status == "running"
        assert claimed.attempts == 1
        assert claimed.lease_expires_at is not None


def test_second_claim_finds_nothing_while_leased(session) -> None:
    _enqueue(session, "q2")
    with q.claim_job(session, "worker-a") as first:
        assert first is not None
        with q.claim_job(session, "worker-b") as second:
            assert second is None, "a leased job must not be claimable twice"


def test_crashed_worker_leaves_a_recoverable_job(session) -> None:
    """A worker that dies mid-analysis must not strand its job.

    The lease is deliberately preserved on the failure path, because clearing it
    would leave a `running` job that recovery has no way to find.
    """
    import datetime as dt

    from forkreason.models import AnalysisJob, RepositorySnapshot

    job = _enqueue(session, "q3")
    with pytest.raises(RuntimeError):
        with q.claim_job(session, "worker-a") as claimed:
            assert claimed is not None
            raise RuntimeError("worker died")

    row = session.get(AnalysisJob, job.id)
    assert row.status == "running"
    assert row.lease_expires_at is not None, "a crashed worker must keep its lease"

    # Age the lease the way wall-clock time would.
    row.lease_expires_at = dt.datetime.now(dt.timezone.utc) - dt.timedelta(seconds=5)
    session.commit()

    assert q.recover_stale_jobs(session) == 1
    assert session.get(AnalysisJob, job.id).status == "queued"

    # And a fresh worker can pick it up as the next attempt.
    with q.claim_job(session, "worker-b") as reclaimed:
        assert reclaimed is not None
        assert reclaimed.id == job.id
        assert reclaimed.attempts == 2


def test_completed_job_releases_its_lease(session) -> None:
    from forkreason.models import AnalysisJob, RepositorySnapshot

    job = _enqueue(session, "q3b")
    with q.claim_job(session, "worker-a") as claimed:
        assert claimed.lease_expires_at is not None
    assert session.get(AnalysisJob, job.id).lease_expires_at is None


def test_recovery_stops_repeating_failures(session) -> None:
    import datetime as dt

    from forkreason.models import AnalysisJob, RepositorySnapshot

    job = _enqueue(session, "q4")
    with pytest.raises(RuntimeError):
        with q.claim_job(session, "worker-a") as claimed:
            raise RuntimeError("died")

    # The crash rolled the attempt counter back, so set the persisted value the
    # way repeated real failures would have left it.
    row = session.get(AnalysisJob, job.id)
    row.attempts = 5
    row.lease_expires_at = dt.datetime.now(dt.timezone.utc) - dt.timedelta(seconds=5)
    session.commit()

    q.recover_stale_jobs(session, max_attempts=3)
    failed = session.get(AnalysisJob, job.id)
    assert failed.status == "failed"
    assert failed.error_code == "analysis_repeated_failure"


def test_terminal_jobs_are_not_reclaimed(session) -> None:
    job = _enqueue(session, "q5")
    job.status = "succeeded"
    session.commit()
    with q.claim_job(session, "worker-a") as claimed:
        assert claimed is None


def test_stage_updates_are_recorded_in_order(session) -> None:
    job = _enqueue(session, "s1")
    with q.claim_job(session, "w") as claimed:
        from forkreason.models import PIPELINE_STAGES

        for stage in PIPELINE_STAGES:
            q.set_stage(session, claimed, stage, "working")
            assert claimed.stage_states[stage] == "working"
            q.set_stage(session, claimed, stage, "complete")
            assert claimed.stage_states[stage] == "complete"
        assert claimed.stage_states[PIPELINE_STAGES[0]] == "complete"


def test_failed_job_marks_unfinished_stages(session) -> None:
    job = _enqueue(session, "s2")
    with q.claim_job(session, "w") as claimed:
        q.set_stage(session, claimed, "repository_snapshots", "complete")
        q.finish_job(session, claimed, status="failed", error_code="boom", error_message="bad")
    reloaded = session.get(type(job), job.id)
    assert reloaded.stage_states["repository_snapshots"] == "complete"
    assert reloaded.stage_states["commit_history"] == "failed"


def test_error_message_is_bounded(session) -> None:
    job = _enqueue(session, "s3")
    with q.claim_job(session, "w") as claimed:
        q.finish_job(
            session, claimed, status="failed", error_code="x", error_message="y" * 5000
        )
    assert len(session.get(type(job), job.id).error_message) == 500


def test_queue_depth_counts_by_status(session) -> None:
    _enqueue(session, "d1")
    depth = q.queue_depth(session)
    assert depth["queued"] >= 1
    assert set(depth) == {"queued", "running", "succeeded", "failed", "cancelled", "timed_out"}


# --- cases, evidence, search ---------------------------------------------


def test_unknown_case_returns_404(client: TestClient) -> None:
    response = client.get("/api/v1/cases/deadbeef")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "case_not_found"


def test_cases_list_bounds_are_enforced(client: TestClient) -> None:
    """`limit` is bounded both by the Query type and by a clamp in the handler."""
    assert client.get("/api/v1/cases?limit=1").status_code == 200
    # Out-of-range values are rejected by validation, never silently accepted.
    assert client.get("/api/v1/cases?limit=51").status_code == 422
    assert client.get("/api/v1/cases?limit=0").status_code == 422
    assert client.get("/api/v1/cases?offset=-1").status_code == 422


def test_cases_list_clamp_is_inside_the_declared_bound(client: TestClient) -> None:
    """A route default must satisfy its own bounds, or omitting the param fails."""
    from forkreason.routes.cases import MAX_PAGE_SIZE

    assert client.get("/api/v1/cases").status_code == 200
    assert client.get(f"/api/v1/cases?limit={MAX_PAGE_SIZE}").status_code == 200
    assert client.get("/api/v1/cases/nope/evidence").status_code == 404


def test_cases_list_defaults(client: TestClient) -> None:
    body = client.get("/api/v1/cases").json()
    assert body["total"] == 0
    assert body["items"] == []
    assert body["has_more"] is False


def test_search_is_bounded(client: TestClient) -> None:
    assert client.get("/api/v1/search?q=" + "x" * 500).status_code == 422


def test_search_accepts_empty_query(client: TestClient) -> None:
    assert client.get("/api/v1/search?q=").status_code == 200


def test_evidence_for_unknown_case(client: TestClient) -> None:
    assert client.get("/api/v1/cases/nope/evidence").status_code == 404


def test_challenge_for_unknown_case(client: TestClient) -> None:
    response = client.post(
        "/api/v1/cases/nope/challenge-preparation",
        json={
            "rationale": "I found the real common ancestor upstream.",
            "evidence_summary": "The original project declares this fork parent.",
            "submitter": "0xabc123",
        },
    )
    assert response.status_code == 404


def test_challenge_payload_requires_signing(client: TestClient) -> None:
    """The prepared payload must never contain signature material."""
    from forkreason.models import Case, CaseRevision

    with db_module.session_scope() as s:
        s.add(
            Case(
                id="abc123abc123",
                origin_full_name="acme/a",
                target_full_name="acme/b",
                origin_commit="1" * 40,
                target_commit="2" * 40,
                manifest_hash="deadbeef",
                current_revision=1,
            )
        )
        s.add(
            CaseRevision(
                id="abc123abc123-1",
                case_id="abc123abc123",
                revision_number=1,
                verdict="LIKELY_DERIVED",
                confidence="HIGH",
                direction="ORIGIN_TO_TARGET",
                manifest_hash="deadbeef",
                summary={"layers": ["CODE"]},
            )
        )

    response = client.post(
        "/api/v1/cases/abc123abc123/challenge-preparation",
        json={
            "rationale": "I found the real common ancestor upstream.",
            "evidence_summary": "The original project declares this fork parent.",
            "submitter": "0xabc123",
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["write"]["requires_wallet_signature"] is True
    assert body["base_revision"] == 1
    assert body["expected_revision"] == 2
    for banned in ("private_key", "privateKey", "seed", "mnemonic", "signWith"):
        assert banned not in response.text.lower(), f"payload leaked {banned}"


# --- chain ---------------------------------------------------------------


def test_chain_contract_reports_honestly_when_unconfigured(client: TestClient) -> None:
    body = client.get("/api/v1/chain/contract").json()
    assert body["name"] == "ForkReasonRegistry"
    assert "deployed" in body
    assert "get_case" in body["read_methods"]
    assert "challenge_case" in body["write_methods"]


def test_chain_status_does_not_require_wallet(client: TestClient) -> None:
    response = client.get("/api/v1/chain/status")
    assert response.status_code == 200
    assert "indexed_transactions" in response.json()


def test_unknown_transaction(client: TestClient) -> None:
    assert client.get("/api/v1/chain/transactions/0xdeadbeef").status_code == 404


def test_submit_preparation_requires_configured_contract(client: TestClient) -> None:
    settings = get_settings()
    if settings.genlayer_contract_address:
        pytest.skip("contract is configured in this environment")
    response = client.post(
        "/api/v1/chain/submit-preparation",
        json={"case_id": "abc123abc123", "revision_number": 1},
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "contract_not_configured"


# --- error handling -------------------------------------------------------


def test_404_returns_a_structured_error(client: TestClient) -> None:
    response = client.get("/api/v1/definitely-not-a-route")
    assert response.status_code == 404
    assert "error" in response.json()


def test_errors_never_leak_stack_traces(client: TestClient) -> None:
    for path in ("/api/v1/cases/x", "/api/v1/analyses/x", "/api/v1/chain/transactions/x"):
        body = client.get(path).text
        assert "Traceback" not in body
        assert "/root/" not in body
        assert "Traceback" not in body


def test_wrong_method_returns_error_envelope(client: TestClient) -> None:
    response = client.post("/health")
    assert response.status_code in (404, 405)
    assert "error" in response.json() or response.status_code == 405


def test_persisted_case_records_pinned_commits_and_manifest(tmp_path) -> None:
    """A case must record which commits it analysed, and its manifest.

    Reproducibility rests on this. A case that names two repositories but not
    their pinned commits cannot be re-checked, and a manifest that is computed
    but never stored makes the manifest hash an unverifiable claim.
    """

    from forkreason.analysis.manifest import manifest_hash
    from forkreason.analysis.pipeline import PipelineResult
    from forkreason.db import get_session_factory
    from forkreason.domain import AnalysisOutcome
    from forkreason.jobs.profile_store import ProfileStore
    from forkreason.models import Case, CaseRevision

    manifest = {
        "schema_version": 1,
        "origin": {"full_name": "acme/origin", "commit": "a" * 40},
        "target": {"full_name": "acme/target", "commit": "b" * 40},
        "evidence": [],
    }
    outcome = AnalysisOutcome(
        verdict="INSUFFICIENT_EVIDENCE",
        confidence="LOW",
        direction="NONE",
        summary="not enough evidence",
        evidence=(),
        conflicting=(),
        explanations=(),
        upstream_candidates=(),
        shared_upstream=None,
        independent_origin_plausibility="LOW",
        origin_timeline=(),
        target_timeline=(),
    )
    result = PipelineResult(
        outcome=outcome,
        manifest=manifest,
        manifest_hash=manifest_hash(manifest),
        consensus_digest="",
        case_id="testcase1234567890",
        evidence_counts={},
        dropped_weak_evidence=0,
        elapsed_seconds=0.1,
    )

    from forkreason.models import AnalysisJob, RepositorySnapshot

    store = ProfileStore(tmp_path)
    session = get_session_factory()()
    try:
        # The case references its job, and the job references its snapshots, so
        # the parent chain must exist for the foreign keys to hold.
        session.add_all([
            RepositorySnapshot(
                id="snap_o",
                owner="acme",
                name="origin",
                full_name="acme/origin",
                commit_sha="a" * 40,
                default_branch="main",
                is_fork=False,
                size_bytes=0,
                file_count=0,
            ),
            RepositorySnapshot(
                id="snap_t",
                owner="acme",
                name="target",
                full_name="acme/target",
                commit_sha="b" * 40,
                default_branch="main",
                is_fork=False,
                size_bytes=0,
                file_count=0,
            ),
        ])
        session.flush()
        session.add(
            AnalysisJob(
                id="job_test",
                status="succeeded",
                stage="consensus_preparation",
                origin_snapshot_id="snap_o",
                target_snapshot_id="snap_t",
                origin_full_name="acme/origin",
                target_full_name="acme/target",
                origin_commit="a" * 40,
                target_commit="b" * 40,
                idempotency_key="k_test",
            )
        )
        session.flush()

        store.persist_case(session, job_id="job_test", result=result)
        session.commit()

        case = session.get(Case, "testcase1234567890")
        assert case is not None
        assert case.origin_commit == "a" * 40, case.origin_commit
        assert case.target_commit == "b" * 40, case.target_commit

        revision = session.get(CaseRevision, "testcase1234567890-1")
        assert revision is not None
        assert revision.manifest == manifest
        assert revision.manifest_hash == manifest_hash(manifest)
    finally:
        session.rollback()
        session.close()
