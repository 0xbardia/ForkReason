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
# Assigned, not defaulted: the repository's own .env sets APP_ENV=production, so
# setdefault() would leave the suite running as a production deployment.
# create_app() validates configuration before serving, and a production start
# with no GITHUB_TOKEN is correctly refused — which is exactly the fail-closed
# behaviour the suite must not be subject to. No test makes a real GitHub call.
os.environ["APP_ENV"] = "test"
os.environ["SNAPSHOT_DIR"] = str(ROOT / "_test_snapshots")
os.environ["GITHUB_TOKEN"] = "test-token-not-used-for-api-calls"

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


def test_challenge_payload_requires_signing(client: TestClient, monkeypatch) -> None:
    """The prepared payload must never contain signature material."""
    from forkreason.models import Case, CaseRevision
    from types import SimpleNamespace
    from forkreason.routes import cases as cases_routes

    monkeypatch.setattr(
        cases_routes, "get_settings",
        lambda: SimpleNamespace(
            genlayer_contract_address="0x" + "a" * 40,
            genlayer_network="studionet",
            genlayer_rpc_url="https://studio.genlayer.com/api",
            max_manifest_digest_chars=6000,
        ),
    )

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
    assert body["write"]["args"][0] == "deadbeef"
    assert body["write"]["args"][1] == 1
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


def test_submit_preparation_requires_configured_contract(client: TestClient, monkeypatch) -> None:
    from types import SimpleNamespace

    from forkreason.routes import chain as chain_routes

    monkeypatch.setattr(
        chain_routes, "get_settings",
        lambda: SimpleNamespace(genlayer_contract_address=None),
    )
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

        revision = session.get(CaseRevision, "testcase1234567890-0")
        assert revision is not None
        assert revision.manifest == manifest
        assert revision.manifest_hash == manifest_hash(manifest)
        assert case.current_revision == 0
        assert case.lifecycle == "analysis_ready"
    finally:
        session.rollback()
        session.close()


def test_renamed_repository_snapshot_is_idempotent_under_a_different_id(tmp_path) -> None:
    """A renamed repository must not break snapshot bookkeeping.

    `tiangolo/typer` resolves to `fastapi/typer`, so the snapshot id computed
    from the canonical name can differ from one already on file. Two failures
    came out of that, and both are pinned here:

    * the insert violated the unique constraint on (full_name, commit_sha),
      which surfaced to the user as `internal_error`;
    * the pinned tree was extracted under the freshly-computed id while the row
      kept the old one, so the worker's `load_profile` looked in a directory
      that did not exist and every analysis failed with `snapshot_unavailable`.
    """
    import hashlib

    from forkreason.db import get_session_factory
    from forkreason.domain import CommitEntry, FileEntry, RepoProfile

    from forkreason.jobs.profile_store import ProfileStore
    from forkreason.models import RepositorySnapshot

    def _profile(full_name: str) -> RepoProfile:
        body = "def handler(event):\n    return event.payload\n"
        return RepoProfile(
            full_name=full_name,
            commit_sha="c" * 40,
            files=(
                FileEntry(
                    path="src/app.py",
                    size=len(body),
                    sha256=hashlib.sha256(body.encode()).hexdigest(),
                    language="python",
                    text=body,
                ),
            ),
            commits=(
                CommitEntry(
                    sha="c" * 40,
                    timestamp=1_600_000_000,
                    author="Dev <d@example.com>",
                    message="Initial commit",
                ),
            ),
            description="",
            is_fork=False,
            parent_full_name=None,
        )

    store = ProfileStore(tmp_path)
    session = get_session_factory()()
    try:
        session.add(
            RepositorySnapshot(
                id="stale_id_aaaaaaaaaa",
                owner="tiangolo",
                name="typer",
                full_name="tiangolo/typer",
                commit_sha="c" * 40,
                default_branch="main",
                is_fork=False,
                size_bytes=0,
                file_count=0,
            )
        )
        session.flush()

        profile = _profile("tiangolo/typer")

        # A freshly computed id must not collide with the stored row.
        row = store.upsert_snapshot(
            session, "fresh_id_bbbbbbbbbb", profile, truncated=False
        )
        session.commit()
        assert row.id == "stale_id_aaaaaaaaaa"
        assert row.full_name == "tiangolo/typer"

        # find_snapshot must find it by (full_name, commit), which is what the
        # analysis route uses to pin the tree to the id that actually holds it.
        found = store.find_snapshot(session, "tiangolo/typer", "c" * 40)
        assert found is not None
        assert found.id == "stale_id_aaaaaaaaaa"

        # A commit nobody has stored yields no row.
        assert store.find_snapshot(session, "tiangolo/typer", "d" * 40) is None
    finally:
        session.rollback()
        session.close()


# --- Configuration fail-closed -------------------------------------------


def test_database_url_has_no_hardcoded_default() -> None:
    """A missing DATABASE_URL must be visible, not silently substituted.

    `database_url` used to carry a baked-in DSN with a placeholder password.
    When the variable was absent, the application started cleanly and then
    failed at the first query with a confusing authentication error, naming
    neither the variable nor the fix. Config now starts empty so the failure is
    reported by validate_startup().
    """
    from forkreason.config import Settings

    bare = Settings(_env_file=None, DATABASE_URL="")
    assert bare.database_url == "", "a default DSN is masking a missing variable"


def test_missing_database_url_is_reported_actionably() -> None:
    from forkreason.config import Settings

    settings = Settings(_env_file=None, DATABASE_URL="", APP_ENV="test")
    with pytest.raises(RuntimeError) as excinfo:
        settings.validate_startup()
    message = str(excinfo.value)
    assert "DATABASE_URL" in message
    # The message must tell the operator what to do, not merely what is wrong.
    assert ".env.example" in message or "Copy" in message


def test_production_requires_a_github_token() -> None:
    """Without this the API inherits GitHub's 60/hour anonymous limit."""
    from forkreason.config import Settings

    settings = Settings(_env_file=None, APP_ENV="production", GITHUB_TOKEN=None)
    with pytest.raises(RuntimeError) as excinfo:
        settings.validate_startup()
    assert "GITHUB_TOKEN" in str(excinfo.value)


def test_startup_gate_actually_runs() -> None:
    """validate_startup must be called during application creation.

    The method existed and was correct, but nothing invoked it, so the whole
    check was dead code: the API started happily with an invalid configuration
    and failed later. This asserts the gate is wired, not merely present.
    """
    import inspect

    from forkreason import main as main_module

    source = inspect.getsource(main_module.create_app)
    assert "validate_startup" in source, "create_app does not validate configuration"


def _provisional_case(session):
    from forkreason.ids import case_id_for, content_hash
    from forkreason.models import Case, CaseRevision

    origin, target = "psf/requests", "pallets/werkzeug"
    origin_commit, target_commit = "1" * 40, "2" * 40
    manifest = {
        "origin": {"full_name": origin, "commit": origin_commit},
        "target": {"full_name": target, "commit": target_commit},
    }
    manifest_hash = content_hash(manifest)
    case_id = case_id_for(origin, origin_commit, target, target_commit)
    case = Case(
        id=case_id, origin_full_name=origin, target_full_name=target,
        origin_commit=origin_commit, target_commit=target_commit,
        manifest_hash=manifest_hash, current_revision=0, lifecycle="analysis_ready",
    )
    revision = CaseRevision(
        id=f"{case_id}-0", case_id=case_id, revision_number=0,
        verdict="INDEPENDENT", confidence="HIGH", direction="NONE",
        manifest_hash=manifest_hash, manifest=manifest, summary={"layers": []},
    )
    session.add_all((case, revision))
    session.commit()
    return case, revision


def test_submit_preparation_returns_exact_six_abi_arguments(client, session, monkeypatch) -> None:
    """The API mapping uses contract order and derives from the pinned Case."""
    from types import SimpleNamespace

    from forkreason.routes import chain as chain_routes

    case, _revision = _provisional_case(session)
    monkeypatch.setattr(
        chain_routes, "get_settings",
        lambda: SimpleNamespace(
            genlayer_contract_address="0x" + "a" * 40,
            genlayer_network="studionet",
            genlayer_rpc_url="https://studio.genlayer.com/api",
            max_manifest_digest_chars=6000,
        ),
    )
    response = client.post(
        "/api/v1/chain/submit-preparation",
        json={"case_id": case.id, "revision_number": 0},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["write"]["method"] == "submit_case"
    assert body["write"]["requires_wallet_signature"] is True
    assert body["write"]["args"] == [
        case.origin_full_name, case.origin_commit,
        case.target_full_name, case.target_commit,
        case.manifest_hash, body["evidence_digest"],
    ]
    assert len(body["write"]["args"]) == 6


def test_submit_case_mapping_rejects_missing_pins_and_malformed_manifest(session) -> None:
    from forkreason.chain_payloads import build_submit_case_args

    case, revision = _provisional_case(session)
    case.target_commit = ""
    with pytest.raises(ValueError, match="pinned repositories"):
        build_submit_case_args(case, revision, "evidence")
    case.target_commit = "2" * 40
    revision.manifest_hash = "not-hex"
    with pytest.raises(ValueError, match="manifest identity"):
        build_submit_case_args(case, revision, "evidence")


def test_submit_case_mapping_order_matches_the_shipping_contract_abi() -> None:
    import ast

    from forkreason.chain_payloads import SubmitCaseArgs

    source = (ROOT / "contracts" / "forkreason_registry.py").read_text()
    module = ast.parse(source)
    registry = next(
        node for node in module.body
        if isinstance(node, ast.ClassDef) and node.name == "ForkReasonRegistry"
    )
    function = next(
        node for node in registry.body
        if isinstance(node, ast.FunctionDef) and node.name == "submit_case"
    )
    abi = [arg for arg in function.args.args if arg.arg != "self"]

    assert [arg.arg for arg in abi] == list(SubmitCaseArgs._fields)
    assert all(isinstance(arg.annotation, ast.Name) and arg.annotation.id == "str" for arg in abi)


def test_unverified_registration_hash_is_retryable_then_blocks_when_chain_pending(client, session, monkeypatch, tmp_path) -> None:
    from types import SimpleNamespace

    from forkreason.routes import chain as chain_routes

    case, _ = _provisional_case(session)
    monkeypatch.setattr(
        chain_routes, "get_settings",
        lambda: SimpleNamespace(
            genlayer_contract_address="0x" + "a" * 40,
            genlayer_network="studionet",
            genlayer_rpc_url="https://studio.genlayer.com/api",
            max_manifest_digest_chars=6000,
            snapshot_dir=tmp_path,
        ),
    )
    first = "0x" + "5" * 64
    path = "/api/v1/chain/transactions"
    payload = {"case_id": case.id, "tx_hash": first, "kind": "registration"}
    response = client.post(path, json=payload)
    assert response.status_code == 202
    assert response.json()["status"] == "submitted"
    replay = client.post(path, json=payload)
    assert replay.status_code == 202
    assert replay.json()["tx_hash"] == first
    from forkreason.models import ChainTransaction
    # A claimed hash cannot freeze registration or appear pending before the
    # read-only worker has verified its contract calldata.
    assert client.post(
        "/api/v1/chain/submit-preparation",
        json={"case_id": case.id, "revision_number": 0},
    ).status_code == 200
    assert client.get(f"/api/v1/cases/{case.id}").json()["case"]["pending_tx_hash"] is None
    session.get(ChainTransaction, first).status = "consensus_pending"
    session.commit()
    assert client.post(
        "/api/v1/chain/submit-preparation",
        json={"case_id": case.id, "revision_number": 0},
    ).status_code == 409
    duplicate = client.post(path, json={**payload, "tx_hash": "0x" + "6" * 64})
    assert duplicate.status_code == 409
    assert duplicate.json()["error"]["code"] == "registration_pending"


def _registration_observation(case, revision, tx_id, contract, *, status="FINALIZED", method="submit_case", args=None):
    from forkreason.chain_payloads import build_submit_case_args
    from forkreason.routes.chain import _digest_for

    submit_args = list(build_submit_case_args(case, revision, _digest_for(case, revision)))
    return {
        "transaction": {
            "tx_id": tx_id, "status": status, "execution_success": True,
            "to": contract, "from": "0x" + "b" * 40,
            "call": {"method": method, "args": submit_args if args is None else args},
        },
        "case": {
            "case_id": revision.manifest_hash,
            "origin_repo": case.origin_full_name, "origin_commit": case.origin_commit,
            "target_repo": case.target_full_name, "target_commit": case.target_commit,
            "manifest_hash": revision.manifest_hash, "submitter": "0x" + "b" * 40,
            "current_revision": 1, "lifecycle": "RESOLVED",
        },
        "revision": {
            "case_id": revision.manifest_hash, "revision_number": 1,
            "manifest_hash": revision.manifest_hash, "verdict": "INDEPENDENT",
            "confidence": "HIGH", "direction": "NONE", "shared_upstream": "",
            "independent_origin_plausibility": "HIGH", "evidence_classes": ["CODE"],
            "rationale": "The repositories are independently implemented.", "is_current": True,
        },
        "challenge": None,
    }


def test_accepted_registration_reconciles_to_the_public_case_view(client, session) -> None:
    from forkreason.chain_reconciliation import reconcile_observed_write
    from forkreason.models import AlternativeExplanation, CaseRevision, ChainTransaction, EvidenceItem, EvidenceRelation

    case, provisional = _provisional_case(session)
    evidence = EvidenceItem(
        id="evidence-hash-0", case_id=case.id, revision_number=0,
        dna_layer="CODE", evidence_type="shared_function", strength="MEDIUM", score=0.6,
        rationale="Pinned code evidence.", origin_source={"repo": case.origin_full_name},
        target_source={"repo": case.target_full_name}, excerpt="bounded",
    )
    explanation = AlternativeExplanation(
        id=f"{case.id}-0-INDEPENDENT_SAME_SPEC", case_id=case.id, revision_number=0,
        kind="INDEPENDENT_SAME_SPEC", support="HIGH", score=0.8,
        rationale="Independent implementations.", evidence_refs=["evidence-hash"],
    )
    relation = EvidenceRelation(
        id="evidence-relation-0", case_id=case.id, subject_kind="evidence",
        subject_ref="evidence-hash", relation="observed_in", object_kind="repository",
        object_ref=case.origin_full_name, weight=0.6,
    )
    tx_id, contract = "0x" + "c" * 64, "0x" + "a" * 40
    row = ChainTransaction(
        id=tx_id, case_id=case.id, kind="registration", network="studionet",
        status="submitted", payload_summary={},
    )
    session.add_all((evidence, explanation, relation, row))
    session.commit()
    observed = _registration_observation(case, provisional, tx_id, contract)

    assert reconcile_observed_write(
        session, row, observed, expected_network="studionet", expected_contract=contract,
    ) == "accepted"
    session.commit()
    # Replaying the same finalized observation is idempotent.
    assert reconcile_observed_write(
        session, row, observed, expected_network="studionet", expected_contract=contract,
    ) == "accepted"
    session.commit()

    assert case.current_revision == 1
    assert session.get(CaseRevision, f"{case.id}-0").verdict == "INDEPENDENT"
    assert session.get(CaseRevision, f"{case.id}-1").tx_hash == tx_id
    assert session.get(EvidenceItem, "evidence-hash-0").revision_number == 0
    assert session.get(EvidenceItem, "evidence-hash-1").revision_number == 1
    assert session.get(AlternativeExplanation, f"{case.id}-1-INDEPENDENT_SAME_SPEC").evidence_refs == ["evidence-hash-1"]
    assert session.get(EvidenceRelation, "evidence-relation-0").subject_ref == "evidence-hash"
    assert session.get(EvidenceRelation, "evidence-relation-0-1").subject_ref == "evidence-hash-1"

    public_case = client.get(f"/api/v1/cases/{case.id}").json()
    assert public_case["case"]["current_revision"] == 1
    assert public_case["verdict"]["revision_number"] == 1
    assert public_case["verdict"]["tx_hash"] == tx_id
    assert [revision["revision_number"] for revision in public_case["revisions"]] == [1]
    assert public_case["evidence"][0]["id"] == "evidence-hash-1"


def _challenge_fixture(session):
    from forkreason.models import CaseRevision, ChainTransaction, Challenge

    case, provisional = _provisional_case(session)
    initial_tx = "0x" + "d" * 64
    case.current_revision = 1
    case.lifecycle = "resolved"
    case.submitter = "0x" + "b" * 40
    revision = CaseRevision(
        id=f"{case.id}-1", case_id=case.id, revision_number=1,
        verdict="INDEPENDENT", confidence="HIGH", direction="NONE",
        manifest_hash=provisional.manifest_hash, manifest=provisional.manifest,
        summary={"layers": ["CODE"]}, tx_hash=initial_tx, network="studionet",
    )
    rationale = "The shared implementation came from an earlier common ancestor."
    digest = "CHALLENGE against revision 1: new pinned evidence"
    challenge = Challenge(
        id="challenge-attempt-1", case_id=case.id, base_revision=1,
        submitter="0xclient", rationale=rationale, evidence_refs=["new evidence"],
        evidence_digest=digest, status="submitted", tx_hash="0x" + "e" * 64,
    )
    tx = ChainTransaction(
        id=challenge.tx_hash, case_id=case.id, kind="challenge", network="studionet",
        status="submitted", payload_summary={"challenge_id": challenge.id},
    )
    session.add_all((revision, challenge, tx))
    session.commit()
    return case, revision, challenge, tx


def _challenge_observation(case, revision, challenge, tx, contract, *, status="FINALIZED", challenge_base=1):
    chain_case_id = revision.manifest_hash
    manifest_hash = "f" * 64
    return {
        "transaction": {
            "tx_id": tx.id, "status": status, "execution_success": True, "to": contract,
            "from": "0x" + "9" * 40,
            "call": {"method": "challenge_case", "args": [
                chain_case_id, challenge.base_revision, challenge.rationale, challenge.evidence_digest,
            ]},
        },
        "case": {
            "case_id": chain_case_id, "origin_repo": case.origin_full_name,
            "origin_commit": case.origin_commit, "target_repo": case.target_full_name,
            "target_commit": case.target_commit, "manifest_hash": revision.manifest_hash,
            "submitter": case.submitter, "current_revision": 2,
            "lifecycle": "CHALLENGED",
        },
        "revision": {
            "case_id": chain_case_id, "revision_number": 2,
            "manifest_hash": manifest_hash, "verdict": "SHARED_UPSTREAM",
            "confidence": "MEDIUM", "direction": "NONE", "shared_upstream": "acme/common",
            "independent_origin_plausibility": "MEDIUM", "evidence_classes": ["HISTORY"],
            "rationale": "The chain accepted the common ancestor evidence.", "is_current": True,
        },
        "challenge": {
            "case_id": chain_case_id, "base_revision": challenge_base,
            "submitter": "0x" + "9" * 40, "rationale": challenge.rationale,
            "manifest_hash": manifest_hash, "status": "RECORDED",
        },
    }


def test_accepted_challenge_appends_revision_and_updates_public_case(client, session) -> None:
    from forkreason.chain_reconciliation import reconcile_observed_write
    from forkreason.models import CaseRevision

    case, revision1, challenge, tx = _challenge_fixture(session)
    original = (revision1.verdict, revision1.confidence, revision1.manifest_hash, revision1.tx_hash)
    contract = "0x" + "a" * 40
    observed = _challenge_observation(case, revision1, challenge, tx, contract)

    assert reconcile_observed_write(
        session, tx, observed, expected_network="studionet", expected_contract=contract,
    ) == "accepted"
    session.commit()
    assert reconcile_observed_write(
        session, tx, observed, expected_network="studionet", expected_contract=contract,
    ) == "accepted"
    session.commit()

    assert case.current_revision == 2
    assert (revision1.verdict, revision1.confidence, revision1.manifest_hash, revision1.tx_hash) == original
    assert session.get(CaseRevision, f"{case.id}-2").verdict == "SHARED_UPSTREAM"
    assert challenge.resulting_revision == 2 and challenge.status == "recorded"
    public_case = client.get(f"/api/v1/cases/{case.id}").json()
    assert public_case["case"]["current_revision"] == 2
    assert public_case["verdict"]["verdict"] == "SHARED_UPSTREAM"
    assert [item["revision_number"] for item in public_case["revisions"]] == [1, 2]


def test_pending_malformed_and_stale_chain_observations_fail_closed(client, session) -> None:
    from forkreason.chain_reconciliation import reconcile_observed_write
    from forkreason.models import ChainTransaction

    case, provisional = _provisional_case(session)
    contract = "0x" + "a" * 40
    pending_tx = ChainTransaction(
        id="0x" + "1" * 64, case_id=case.id, kind="registration", network="studionet",
        status="submitted", payload_summary={},
    )
    session.add(pending_tx)
    session.commit()
    pending = _registration_observation(case, provisional, pending_tx.id, contract, status="PROPOSING")
    assert reconcile_observed_write(
        session, pending_tx, pending, expected_network="studionet", expected_contract=contract,
    ) == "consensus_pending"
    session.commit()
    assert case.current_revision == 0

    malformed_tx = ChainTransaction(
        id="0x" + "2" * 64, case_id=case.id, kind="registration", network="studionet",
        status="submitted", payload_summary={},
    )
    session.add(malformed_tx)
    session.commit()
    malformed = _registration_observation(case, provisional, malformed_tx.id, contract)
    malformed["transaction"]["call"]["method"] = "challenge_case"
    assert reconcile_observed_write(
        session, malformed_tx, malformed, expected_network="studionet", expected_contract=contract,
    ) == "rejected"
    session.commit()
    assert case.current_revision == 0

    stale_tx = ChainTransaction(
        id="0x" + "3" * 64, case_id=case.id, kind="registration", network="studionet",
        status="submitted", payload_summary={},
    )
    session.add(stale_tx)
    session.commit()
    stale = _registration_observation(case, provisional, stale_tx.id, contract)
    stale["case"]["current_revision"] = 2
    assert reconcile_observed_write(
        session, stale_tx, stale, expected_network="studionet", expected_contract=contract,
    ) == "rejected"
    assert case.current_revision == 0

    forged_tx = ChainTransaction(
        id="0x" + "7" * 64, case_id=case.id, kind="registration", network="studionet",
        status="submitted", payload_summary={},
    )
    session.add(forged_tx)
    session.commit()
    forged = _registration_observation(case, provisional, "0x" + "8" * 64, contract)
    assert reconcile_observed_write(
        session, forged_tx, forged, expected_network="studionet", expected_contract=contract,
    ) == "rejected"

    wrong_contract_tx = ChainTransaction(
        id="0x" + "9" * 64, case_id=case.id, kind="registration", network="studionet",
        status="submitted", payload_summary={},
    )
    session.add(wrong_contract_tx)
    session.commit()
    wrong_contract = _registration_observation(case, provisional, wrong_contract_tx.id, contract)
    assert reconcile_observed_write(
        session, wrong_contract_tx, wrong_contract,
        expected_network="studionet", expected_contract="0x" + "f" * 40,
    ) == "rejected"

    wrong_network_tx = ChainTransaction(
        id="0x" + "a" * 64, case_id=case.id, kind="registration", network="testnet_bradbury",
        status="submitted", payload_summary={},
    )
    session.add(wrong_network_tx)
    session.commit()
    wrong_network = _registration_observation(case, provisional, wrong_network_tx.id, contract)
    assert reconcile_observed_write(
        session, wrong_network_tx, wrong_network,
        expected_network="studionet", expected_contract=contract,
    ) == "rejected"
    assert case.current_revision == 0


def test_database_rollback_keeps_transaction_retryable(session) -> None:
    from forkreason.chain_reconciliation import reconcile_observed_write
    from forkreason.models import Case, CaseRevision, ChainTransaction

    case, provisional = _provisional_case(session)
    contract, tx_id = "0x" + "a" * 40, "0x" + "4" * 64
    tx = ChainTransaction(
        id=tx_id, case_id=case.id, kind="registration", network="studionet",
        status="submitted", payload_summary={},
    )
    session.add(tx)
    session.commit()
    observed = _registration_observation(case, provisional, tx_id, contract)

    reconcile_observed_write(session, tx, observed, expected_network="studionet", expected_contract=contract)
    session.rollback()  # simulate failure of the atomic projection commit after chain finality
    retry = session.get(ChainTransaction, tx_id)
    assert retry is not None and retry.status == "submitted"
    assert session.get(Case, case.id).current_revision == 0
    assert session.get(CaseRevision, f"{case.id}-1") is None

    assert reconcile_observed_write(
        session, retry, observed, expected_network="studionet", expected_contract=contract,
    ) == "accepted"
    session.commit()
    assert session.get(Case, case.id).current_revision == 1


def test_stale_replays_cannot_roll_the_case_back_or_duplicate_a_revision(client, session) -> None:
    from forkreason.chain_reconciliation import reconcile_observed_write
    from forkreason.models import CaseRevision, ChainTransaction

    case, revision1, challenge, tx = _challenge_fixture(session)
    contract = "0x" + "a" * 40
    observed = _challenge_observation(case, revision1, challenge, tx, contract)
    late_id = "0x" + "1" * 64
    stale = _registration_observation(case, session.get(CaseRevision, f"{case.id}-0"), late_id, contract)
    assert reconcile_observed_write(
        session, tx, observed, expected_network="studionet", expected_contract=contract,
    ) == "accepted"
    session.commit()
    revision2 = session.get(CaseRevision, f"{case.id}-2")
    snapshot = (case.current_revision, revision2.tx_hash, revision2.manifest_hash)

    # A late registration observation (revision 1) for a Case already at 2.
    late = ChainTransaction(
        id=late_id, case_id=case.id, kind="registration", network="studionet",
        status="submitted", payload_summary={},
    )
    session.add(late)
    session.commit()
    assert reconcile_observed_write(
        session, late, stale, expected_network="studionet", expected_contract=contract,
    ) == "rejected"

    # A second transaction claiming the same challenge cannot add or replace revision 2.
    other = ChainTransaction(
        id="0x" + "2" * 64, case_id=case.id, kind="challenge", network="studionet",
        status="submitted", payload_summary={"challenge_id": challenge.id},
    )
    session.add(other)
    session.commit()
    replay = _challenge_observation(case, revision1, challenge, other, contract)
    assert reconcile_observed_write(
        session, other, replay, expected_network="studionet", expected_contract=contract,
    ) == "rejected"
    session.commit()
    response = client.post(
        "/api/v1/chain/transactions",
        json={"case_id": case.id, "tx_hash": "0x" + "3" * 64, "kind": "challenge", "challenge_id": challenge.id},
    )
    assert response.status_code == 409

    session.expire_all()
    revision2 = session.get(CaseRevision, f"{case.id}-2")
    assert (case.current_revision, revision2.tx_hash, revision2.manifest_hash) == snapshot
    assert session.query(CaseRevision).filter_by(case_id=case.id, revision_number=2).count() == 1
    assert [r["revision_number"] for r in client.get(f"/api/v1/cases/{case.id}").json()["revisions"]] == [1, 2]


def test_unseen_transaction_is_retried_inside_the_grace_window_then_rejected(session) -> None:
    import datetime as dt

    from forkreason.chain_reconciliation import reconcile_observed_write
    from forkreason.models import ChainTransaction

    case, _ = _provisional_case(session)
    contract = "0x" + "a" * 40
    fresh = ChainTransaction(
        id="0x" + "5" * 64, case_id=case.id, kind="registration", network="studionet",
        status="submitted",
        payload_summary={"recorded_at": dt.datetime.now(dt.timezone.utc).isoformat()},
    )
    old = ChainTransaction(
        id="0x" + "6" * 64, case_id=case.id, kind="registration", network="studionet",
        status="submitted",
        payload_summary={"recorded_at": (dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=1)).isoformat()},
    )
    session.add_all((fresh, old))
    session.commit()
    for row in (fresh, old):
        missing = {"transaction": {"tx_id": row.id, "status": "NOT_FOUND"}}
        reconcile_observed_write(session, row, missing, expected_network="studionet", expected_contract=contract)
    # An RPC that has not indexed the wallet's hash yet must not lose the write.
    assert fresh.status == "submitted"
    assert old.status == "rejected"
    assert case.current_revision == 0


def test_unverified_transaction_claims_per_case_are_bounded(client, session, monkeypatch, tmp_path) -> None:
    from types import SimpleNamespace

    from forkreason.routes import chain as chain_routes

    case, _ = _provisional_case(session)
    monkeypatch.setattr(
        chain_routes, "get_settings",
        lambda: SimpleNamespace(
            genlayer_contract_address="0x" + "a" * 40, genlayer_network="studionet",
            genlayer_rpc_url="https://studio.genlayer.com/api", max_manifest_digest_chars=6000,
            snapshot_dir=tmp_path,
        ),
    )
    statuses = [
        client.post("/api/v1/chain/transactions", json={
            "case_id": case.id, "tx_hash": "0x" + f"{index:064x}", "kind": "registration",
        }).status_code
        for index in range(1, chain_routes.MAX_UNVERIFIED_PER_CASE + 2)
    ]
    assert statuses[:-1] == [202] * chain_routes.MAX_UNVERIFIED_PER_CASE
    assert statuses[-1] == 409
