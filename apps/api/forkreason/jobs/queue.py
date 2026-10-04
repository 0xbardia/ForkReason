"""PostgreSQL-backed durable job queue.

No Redis: the server already runs PostgreSQL, and one fewer broker is one fewer
thing to keep alive (spec FR-I-003). Claims use `FOR UPDATE SKIP LOCKED` so
concurrent workers never contend and a crashed worker's job is picked up again
once its lease expires.

The invariants that matter for correctness:
  * A job is claimed at most once at a time (lease).
  * A crashed worker's job returns to `queued` when the lease expires
    (recovery on restart, spec FR-I-005).
  * `idempotency_key` is unique, so a resubmitted identical pair cannot create
    duplicate work (spec FR-I-004).
"""

from __future__ import annotations

import datetime as dt
import logging
from contextlib import contextmanager
from typing import Iterator

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from ..domain import AnalysisCancelledError, AnalysisError, AnalysisTimeoutError
from ..models import PIPELINE_STAGES, AnalysisJob

log = logging.getLogger(__name__)

LEASE_SECONDS = 900
MAX_ATTEMPTS = 3

# Terminal states. A job in one of these will never be claimed again.
TERMINAL_STATES = {"succeeded", "failed", "cancelled", "timed_out"}


def utcnow() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def enqueue_job(
    session: Session,
    *,
    job_id: str,
    origin_snapshot_id: str,
    target_snapshot_id: str,
    origin_full_name: str,
    target_full_name: str,
    origin_commit: str,
    target_commit: str,
    idempotency_key: str,
) -> tuple[AnalysisJob, bool]:
    """Create a job, or return the existing one for this idempotency key.

    Returns (job, created). The caller must not start work when `created` is
    False: the existing job already owns this pinned pair.
    """
    existing = session.scalar(
        select(AnalysisJob).where(AnalysisJob.idempotency_key == idempotency_key)
    )
    if existing is not None:
        return existing, False

    job = AnalysisJob(
        id=job_id,
        status="queued",
        stage="queued",
        stage_states={stage: "pending" for stage in PIPELINE_STAGES},
        origin_snapshot_id=origin_snapshot_id,
        target_snapshot_id=target_snapshot_id,
        origin_full_name=origin_full_name,
        target_full_name=target_full_name,
        origin_commit=origin_commit,
        target_commit=target_commit,
        idempotency_key=idempotency_key,
        attempts=0,
    )
    session.add(job)
    try:
        session.commit()
    except Exception:
        # A concurrent submission may have won the race on the unique key.
        session.rollback()
        existing = session.scalar(
            select(AnalysisJob).where(AnalysisJob.idempotency_key == idempotency_key)
        )
        if existing is not None:
            return existing, False
        raise
    return job, True


@contextmanager
def claim_job(session: Session, worker_id: str) -> Iterator[AnalysisJob | None]:
    """Atomically claim the next available job.

    Uses `FOR UPDATE SKIP LOCKED` so N workers never block each other. The
    lease is a timestamp rather than a lock, so a worker that dies mid-analysis
    releases its job automatically once the lease lapses.
    """
    now = utcnow()
    job = session.scalar(
        select(AnalysisJob)
        .where(
            AnalysisJob.status == "queued",
            (AnalysisJob.lease_expires_at.is_(None))
            | (AnalysisJob.lease_expires_at < now),
        )
        .order_by(AnalysisJob.created_at)
        .limit(1)
        .with_for_update(skip_locked=True)
    )
    if job is None:
        yield None
        return

    job.status = "running"
    job.stage = PIPELINE_STAGES[0]
    job.attempts += 1
    job.started_at = job.started_at or now
    job.lease_expires_at = now + dt.timedelta(seconds=LEASE_SECONDS)
    job.stage_states = {stage: "pending" for stage in PIPELINE_STAGES}
    session.commit()

    log.info(
        "job claimed",
        extra={"job_id": job.id, "worker": worker_id, "attempt": job.attempts},
    )
    try:
        yield job
        # Normal completion: release the lease so the row is not stuck in
        # `running`. The caller sets the terminal status.
        session.refresh(job)
        job.lease_expires_at = None
        session.commit()
    except BaseException:
        # The worker died mid-analysis (crash, kill, OOM). The lease is left
        # intact on purpose: `recover_stale_jobs` finds jobs whose lease has
        # expired, so clearing it here would leave the job permanently stuck in
        # `running` with nothing left to recover it.
        log.warning(
            "worker slot exited without finishing job",
            extra={"job_id": job.id, "worker": worker_id},
        )
        session.rollback()
        raise


def set_stage(
    session: Session, job: AnalysisJob, stage: str, state: str, *, lease_seconds: int = LEASE_SECONDS
) -> None:
    """Record a real stage transition and extend the lease.

    Called from inside the pipeline reporter, so what the frontend sees is the
    pipeline's actual progress and never a synthesized percentage.
    """
    states = dict(job.stage_states or {})
    states[stage] = state
    job.stage_states = states
    job.stage = stage if state == "working" else job.stage
    job.lease_expires_at = utcnow() + dt.timedelta(seconds=lease_seconds)
    session.commit()


def finish_job(
    session: Session,
    job: AnalysisJob,
    *,
    status: str,
    case_id: str | None = None,
    error_code: str | None = None,
    error_message: str | None = None,
) -> None:
    """Move a job to a terminal state with a bounded, user-safe error."""
    job.status = status
    job.finished_at = utcnow()
    job.lease_expires_at = None
    if case_id:
        job.case_id = case_id
    if error_code:
        job.error_code = error_code
        # Never store a stack trace: it can contain absolute paths and, if the
        # failure came from analyzed content, fragments of that content.
        job.error_message = (error_message or "")[:500]
    states = dict(job.stage_states or {})
    for stage, state in list(states.items()):
        if state in {"pending", "working"}:
            states[stage] = "failed"
    job.stage_states = states
    session.commit()
    log.info("job finished", extra={"job_id": job.id, "status": status, "code": error_code})


def request_cancel(session: Session, job_id: str) -> bool:
    """Ask a running job to stop. Cooperative: the worker checks between stages."""
    job = session.get(AnalysisJob, job_id)
    if job is None:
        return False
    if job.status in TERMINAL_STATES:
        return False
    job.cancel_requested = True
    if job.status == "queued":
        # Nothing has started, so cancel immediately.
        finish_job(session, job, status="cancelled", error_code="analysis_cancelled",
                   error_message="Cancelled before analysis began.")
    session.commit()
    return True


def recover_stale_jobs(session: Session, *, max_attempts: int = MAX_ATTEMPTS) -> int:
    """Return jobs abandoned by a dead worker to the queue.

    Called on worker startup. A job whose lease expired is requeued, unless it
    has already been attempted too many times, in which case it fails rather
    than looping forever on a poison input.
    """
    now = utcnow()
    stale = session.scalars(
        select(AnalysisJob).where(
            AnalysisJob.status == "running",
            AnalysisJob.lease_expires_at.is_not(None),
            AnalysisJob.lease_expires_at < now,
        )
    ).all()

    recovered = 0
    for job in stale:
        if job.attempts >= max_attempts:
            finish_job(
                session,
                job,
                status="failed",
                error_code="analysis_repeated_failure",
                error_message=(
                    "Analysis failed repeatedly and was stopped to avoid an "
                    "endless retry."
                ),
            )
            log.warning("job exceeded max attempts", extra={"job_id": job.id})
            continue
        job.status = "queued"
        job.stage = "queued"
        job.lease_expires_at = None
        job.stage_states = {stage: "pending" for stage in PIPELINE_STAGES}
        session.commit()
        recovered += 1
        log.warning("recovered stale job", extra={"job_id": job.id, "attempts": job.attempts})

    return recovered


def cancel_checker(session: Session, job: AnalysisJob):
    """Return a callable the pipeline uses to honour cancellation."""

    def check() -> bool:
        # Refresh from the database so a cancel issued by another process is seen.
        session.expire(job, ["cancel_requested"])
        return bool(job.cancel_requested)

    return check


def status_for_error(exc: Exception) -> tuple[str, str]:
    """Map an exception to (terminal status, error code)."""
    if isinstance(exc, AnalysisCancelledError):
        return "cancelled", exc.code
    if isinstance(exc, AnalysisTimeoutError):
        return "timed_out", exc.code
    if isinstance(exc, AnalysisError):
        return "failed", exc.code
    return "failed", "analysis_failed"


def job_progress(job: AnalysisJob) -> dict:
    """Progress payload for the frontend. Real stages only, never percentages."""
    states = dict(job.stage_states or {})
    done = sum(1 for s in states.values() if s == "complete")
    total = len(PIPELINE_STAGES)
    return {
        "job_id": job.id,
        "status": job.status,
        "stage": job.stage,
        "stages": [{"name": name, "state": states.get(name, "pending")} for name in PIPELINE_STAGES],
        # A count of completed real stages. Not a time estimate, not a guess.
        "stages_complete": done,
        "stages_total": total,
        "case_id": job.case_id,
        "error_code": job.error_code,
        "error_message": job.error_message,
        "created_at": job.created_at.isoformat() if job.created_at else None,
        "started_at": job.started_at.isoformat() if job.started_at else None,
        "finished_at": job.finished_at.isoformat() if job.finished_at else None,
        "origin": {"repo": job.origin_full_name, "commit": job.origin_commit},
        "target": {"repo": job.target_full_name, "commit": job.target_commit},
        "cancel_requested": bool(job.cancel_requested),
    }


def queue_depth(session: Session) -> dict:
    """Queue metrics for the readiness endpoint."""
    rows = session.execute(
        text(
            "SELECT status, count(*) FROM analysis_jobs GROUP BY status"
        )
    ).all()
    counts = {row[0]: row[1] for row in rows}
    return {
        "queued": counts.get("queued", 0),
        "running": counts.get("running", 0),
        "succeeded": counts.get("succeeded", 0),
        "failed": counts.get("failed", 0),
        "cancelled": counts.get("cancelled", 0),
        "timed_out": counts.get("timed_out", 0),
    }