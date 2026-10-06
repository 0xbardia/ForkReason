"""The durable analysis worker.

One process, N concurrent analysis slots (bounded by configuration), each slot
taking one job at a time from the PostgreSQL queue. The worker owns no global
mutable analysis state: everything it needs comes from the job row and the
pinned snapshots, so a restart loses nothing that was not already committed.
"""

from __future__ import annotations

import datetime as dt
import logging
import os
import signal
import threading
import time

from sqlalchemy import select

from ..analysis.pipeline import PipelineConfig, run_pipeline
from ..config import get_settings
from ..db import session_scope
from ..domain import AnalysisCancelledError, AnalysisError
from ..models import ChainTransaction
from . import queue as q
from .profile_store import ProfileStore

log = logging.getLogger(__name__)

WORKER_ID = f"worker-{os.getpid()}"
POLL_INTERVAL_SECONDS = 2.0
IDLE_BACKOFF_SECONDS = 5.0

_stop = threading.Event()


class AnalysisWorker:
    """Claims and processes analysis jobs until stopped."""

    def __init__(self, *, concurrency: int | None = None, store: ProfileStore | None = None) -> None:
        settings = get_settings()
        self.concurrency = concurrency or settings.analysis_worker_concurrency
        self.store = store or ProfileStore(settings.snapshot_dir)
        self.config = PipelineConfig(
            max_evidence_items=settings.analysis_max_evidence_items,
            excerpt_limit=settings.max_excerpt_chars,
            digest_limit=settings.max_manifest_digest_chars,
            timeout_seconds=settings.analysis_timeout_seconds,
            upstream_candidate_limit=settings.upstream_candidate_limit,
        )
        self._threads: list[threading.Thread] = []
        self._chain_thread: threading.Thread | None = None

    # --- lifecycle -------------------------------------------------------

    def start(self) -> None:
        recovered = self._recover()
        log.info(
            "worker started",
            extra={
                "worker": WORKER_ID,
                "concurrency": self.concurrency,
                "recovered_jobs": recovered,
            },
        )
        for index in range(self.concurrency):
            thread = threading.Thread(
                target=self._loop, name=f"{WORKER_ID}-{index}", daemon=True
            )
            thread.start()
            self._threads.append(thread)
        self._chain_thread = threading.Thread(
            target=self._reconcile_loop, name=f"{WORKER_ID}-chain", daemon=True
        )
        self._chain_thread.start()

    def stop(self) -> None:
        _stop.set()

    def join(self, timeout: float | None = None) -> None:
        for thread in self._threads:
            thread.join(timeout)
        if self._chain_thread:
            self._chain_thread.join(timeout)

    def _reconcile_loop(self) -> None:
        """Keep chain RPC latency out of the analysis job slots."""
        while not _stop.is_set():
            try:
                with session_scope() as session:
                    pending = session.scalar(
                        select(ChainTransaction)
                        .where(ChainTransaction.status.in_(("submitted", "consensus_pending")))
                        .order_by(ChainTransaction.observed_at)
                        .limit(1)
                        .with_for_update(skip_locked=True)
                    )
                    if pending is not None:
                        from ..chain_reconciliation import reconcile_transaction

                        try:
                            reconcile_transaction(session, pending)
                        except Exception as exc:  # noqa: BLE001 - persisted id stays retryable
                            log.warning("chain reconciliation will retry", extra={"error": str(exc)[:160]})
                        finally:
                            # ponytail: one poller; add a queue only if serial polling bottlenecks.
                            pending.observed_at = dt.datetime.now(dt.timezone.utc)
            except Exception as exc:  # noqa: BLE001 - the persisted id remains retryable
                log.warning("chain reconciliation will retry", extra={"error": str(exc)[:160]})
            _stop.wait(5.0)

    def _recover(self) -> int:
        """Return abandoned jobs to the queue before accepting new work."""
        with session_scope() as session:
            return q.recover_stale_jobs(session)

    # --- worker loop -----------------------------------------------------

    def _loop(self) -> None:
        while not _stop.is_set():
            processed = self._run_one()
            _stop.wait(POLL_INTERVAL_SECONDS if processed else IDLE_BACKOFF_SECONDS)

    def _run_one(self) -> bool:
        """Claim and process at most one job. Returns True if work was done."""
        try:
            with session_scope() as session:
                with q.claim_job(session, WORKER_ID) as job:
                    if job is None:
                        return False
                    check = q.cancel_checker(session, job)
                    self._process(session, job, check)
                    return True
        except Exception as exc:  # noqa: BLE001 - a slot must never die
            log.exception("worker slot failed", extra={"worker": WORKER_ID, "error": str(exc)[:200]})
            return False

    # --- processing ------------------------------------------------------

    def _process(self, session, job, check_cancel) -> None:
        settings = get_settings()
        job_id = job.id
        origin_snapshot_id = job.origin_snapshot_id
        target_snapshot_id = job.target_snapshot_id

        def report(stage: str, state: str) -> None:
            try:
                q.set_stage(session, job, stage, state)
            except Exception as exc:  # noqa: BLE001
                # Losing a progress write must not abort a running analysis.
                log.warning(
                    "stage update failed",
                    extra={"job_id": job_id, "stage": stage, "error": str(exc)[:160]},
                )

        try:
            origin = self.store.load_profile(session, origin_snapshot_id)
            target = self.store.load_profile(session, target_snapshot_id)
            if origin is None or target is None:
                q.finish_job(
                    session,
                    job,
                    status="failed",
                    error_code="snapshot_unavailable",
                    error_message="The pinned repository snapshot is no longer available.",
                )
                return

            deadline = time.monotonic() + settings.analysis_timeout_seconds

            result = run_pipeline(
                origin,
                target,
                self.config,
                upstream_pool=(),
                report=report,
                cancel_check=check_cancel,
                deadline=deadline,
            )

            self.store.persist_case(session, job_id, result)
            q.finish_job(session, job, status="succeeded", case_id=result.case_id)
            log.info(
                "analysis complete",
                extra={
                    "job_id": job_id,
                    "case_id": result.case_id,
                    "verdict": result.outcome.verdict,
                    "confidence": result.outcome.confidence,
                    "evidence": len(result.outcome.evidence),
                    "elapsed": result.elapsed_seconds,
                },
            )

        except AnalysisCancelledError as exc:
            # Cancellation is a user action, not a failure: no stack trace.
            q.finish_job(
                session, job, status="cancelled", error_code=exc.code, error_message=exc.message
            )
            log.info("analysis cancelled", extra={"job_id": job_id})
        except AnalysisError as exc:
            # Covers intake errors too: IntakeError subclasses AnalysisError, so
            # both carry a stable code and a message safe to show a user.
            status, code = q.status_for_error(exc)
            q.finish_job(
                session, job, status=status, error_code=code, error_message=exc.message
            )
            log.warning(
                "analysis failed",
                extra={"job_id": job_id, "code": code, "detail": exc.detail},
            )
        except Exception:  # noqa: BLE001
            # The traceback is logged; the user is shown a bounded,
            # non-leaking message.
            log.exception("unexpected analysis error", extra={"job_id": job_id})
            q.finish_job(
                session,
                job,
                status="failed",
                error_code="analysis_failed",
                error_message=(
                    "Analysis failed for an internal reason. The failure was "
                    "logged with this job id."
                ),
            )


def main() -> None:  # pragma: no cover - process entrypoint
    logging.basicConfig(
        level=getattr(logging, get_settings().log_level, logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    worker = AnalysisWorker()

    def _shutdown(_signum, _frame):
        log.info("worker shutting down", extra={"worker": WORKER_ID})
        worker.stop()

    signal.signal(signal.SIGTERM, _shutdown)
    signal.signal(signal.SIGINT, _shutdown)

    worker.start()
    try:
        while not _stop.is_set():
            _stop.wait(1.0)
    finally:
        worker.join(timeout=30)
        log.info("worker stopped", extra={"worker": WORKER_ID})


if __name__ == "__main__":  # pragma: no cover
    main()
