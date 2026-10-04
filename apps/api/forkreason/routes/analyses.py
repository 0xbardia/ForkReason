"""Analysis job endpoints.

Creating an analysis is a three-step flow, and the separation is deliberate:
validation is cheap and synchronous, the job is durable, and progress is polled
from real pipeline state. No long analysis ever runs inside a request handler.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, status

import logging
from pathlib import Path

from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..config import get_settings
from ..db import get_db
from ..errors import bad_request, conflict, not_found
from ..domain import AnalysisError, IntakeError
from ..ids import idempotency_key_for, snapshot_id_for
from ..jobs import queue as q
from ..jobs.profile_store import ProfileStore
from ..repos.github_api import fetch_repo_metadata
from ..repos.github_url import validate_repo_input
from ..repos.snapshot import (
    IntakeLimits,
    archive_commit,
    build_profile,
    cache_profile_metadata,
    read_commits,
)

log = logging.getLogger(__name__)

router = APIRouter(tags=["analyses"])


class CreateAnalysisRequest(BaseModel):
    origin: str = Field(min_length=1, max_length=300)
    target: str = Field(min_length=1, max_length=300)


def _store() -> ProfileStore:
    return ProfileStore(get_settings().snapshot_dir)


def _limits() -> IntakeLimits:
    s = get_settings()
    return IntakeLimits(
        max_repo_mb=s.analysis_max_repo_mb,
        max_file_mb=s.analysis_max_file_mb,
        max_files=s.analysis_max_files,
        max_commits=s.analysis_max_commits,
    )


@router.post("/analyses", status_code=status.HTTP_202_ACCEPTED)
async def create_analysis(
    payload: CreateAnalysisRequest, session: Session = Depends(get_db)
) -> dict:
    """Pin both repositories, snapshot them, and queue a durable analysis.

    Snapshotting happens here because it is bounded and fast relative to
    analysis; everything slow happens in the worker.
    """
    settings = get_settings()
    origin_ref = validate_repo_input(payload.origin)
    target_ref = validate_repo_input(payload.target)

    if origin_ref.full_name == target_ref.full_name:
        raise bad_request(
            "identical_repositories", "Choose two different repositories to compare."
        )

    profiles: list = []
    store = _store()
    for ref in (origin_ref, target_ref):
        try:
            metadata = fetch_repo_metadata(
                ref, token=settings.github_token, base_url=settings.github_api_base_url
            )
        except IntakeError as exc:
            raise bad_request(exc.code, exc.message) from exc

        # `fetch_repo_metadata` resolves renames and transfers, so the canonical
        # identity can differ from what the user typed. Everything downstream must
        # key off the RESOLVED name, and the snapshot id must be the one the store
        # actually holds: the worker re-derives the tree directory from the row's
        # own id, so extracting under a different id left the worker looking in a
        # directory that did not exist — every renamed repository failed with
        # `snapshot_unavailable`.
        ref = metadata.ref
        snapshot_id = snapshot_id_for(ref.full_name, metadata.commit_sha)
        existing = store.find_snapshot(session, ref.full_name, metadata.commit_sha)
        if existing is not None:
            snapshot_id = existing.id

        tree = store.snapshot_dir / ref.owner / f"{ref.name}__{snapshot_id[:16]}"

        try:
            archive_commit(str(ref.canonical_url), metadata.commit_sha, tree)
            commits = read_commits(
                str(ref.canonical_url),
                metadata.commit_sha,
                limit=settings.analysis_max_commits,
                staging_dir=Path(settings.snapshot_dir),
            )
            profile, truncated = build_profile(metadata, tree, commits, _limits())
        except AnalysisError as exc:
            raise bad_request(exc.code, exc.message) from exc

        if truncated:
            log.info(
                "snapshot truncated by limits",
                extra={"repo": ref.full_name, "commit": metadata.commit_sha},
            )
        if not profile.files:
            raise bad_request(
                "repository_unreadable",
                f"{ref.full_name} produced no analyzable files.",
            )

        cache_profile_metadata(tree / "_forkreason_inventory.json", ref, profile, truncated)
        profiles.append((snapshot_id, profile, truncated, tree, ref))

    origin_snapshot_id, origin_profile, origin_truncated, origin_tree, origin_ref_final = profiles[0]
    target_snapshot_id, target_profile, target_truncated, target_tree, target_ref_final = profiles[1]

    origin_row = store.upsert_snapshot(
        session, origin_snapshot_id, origin_profile, truncated=origin_truncated
    )
    target_row = store.upsert_snapshot(
        session, target_snapshot_id, target_profile, truncated=target_truncated
    )
    for row, tree in ((origin_row, origin_tree), (target_row, target_tree)):
        row.snapshot_path = str(tree / "_forkreason_inventory.json")
    session.commit()

    idem = idempotency_key_for(
        origin_profile.full_name,
        origin_profile.commit_sha,
        target_profile.full_name,
        target_profile.commit_sha,
    )
    # Derived from the idempotency key so a replay maps to the same job id.
    job_id = f"job_{idem[:24]}"
    job, created = q.enqueue_job(
        session,
        job_id=job_id,
        origin_snapshot_id=origin_snapshot_id,
        target_snapshot_id=target_snapshot_id,
        origin_full_name=origin_profile.full_name,
        target_full_name=target_profile.full_name,
        origin_commit=origin_profile.commit_sha,
        target_commit=target_profile.commit_sha,
        idempotency_key=idem,
    )

    warnings: list[str] = []
    if origin_truncated or target_truncated:
        warnings.append(
            "This analysis was bounded by ForkReason's size limits, so the "
            "inventory is partial."
        )

    return {
        "job": q.job_progress(job),
        "created": created,
        "idempotent_replay": not created,
        "warnings": warnings,
        "origin": {
            "repo": origin_profile.full_name,
            "commit": origin_profile.commit_sha,
            "files": len(origin_profile.files),
            "commits": len(origin_profile.commits),
            "truncated": origin_truncated,
        },
        "target": {
            "repo": target_profile.full_name,
            "commit": target_profile.commit_sha,
            "files": len(target_profile.files),
            "commits": len(target_profile.commits),
            "truncated": target_truncated,
        },
    }


@router.get("/analyses/{job_id}")
async def get_analysis(job_id: str, session: Session = Depends(get_db)) -> dict:
    """Real pipeline progress. No percentages, no invented stages."""
    from ..models import AnalysisJob

    job = session.get(AnalysisJob, job_id)
    if job is None:
        raise not_found("job_not_found", "That analysis does not exist.")
    return q.job_progress(job)


@router.post("/analyses/{job_id}/cancel", status_code=status.HTTP_202_ACCEPTED)
async def cancel_analysis(job_id: str, session: Session = Depends(get_db)) -> dict:
    """Request cancellation. A running job stops at its next stage boundary."""
    from ..models import AnalysisJob

    job = session.get(AnalysisJob, job_id)
    if job is None:
        raise not_found("job_not_found", "That analysis does not exist.")
    if job.status in q.TERMINAL_STATES:
        raise conflict(
            "job_already_finished",
            f"This analysis already finished with status {job.status}.",
        )
    q.request_cancel(session, job_id)
    return q.job_progress(job)


@router.get("/analyses/{job_id}/manifest")
async def get_analysis_manifest(job_id: str, session: Session = Depends(get_db)) -> dict:
    """The canonical evidence manifest for a finished analysis."""
    from ..models import AnalysisJob

    job = session.get(AnalysisJob, job_id)
    if job is None:
        raise not_found("job_not_found", "That analysis does not exist.")
    if job.status != "succeeded" or not job.case_id:
        raise conflict(
            "analysis_not_finished",
            "The evidence manifest is available once analysis has succeeded.",
        )

    from sqlalchemy import select

    from ..models import Case, CaseRevision

    case = session.get(Case, job.case_id)
    if case is None:
        raise not_found("case_not_found", "That case does not exist.")
    revision = session.scalar(
        select(CaseRevision).where(
            CaseRevision.case_id == case.id,
            CaseRevision.revision_number == case.current_revision,
        )
    )
    if revision is None:
        raise not_found("revision_not_found", "That revision does not exist.")

    return {
        "case_id": case.id,
        "revision_number": revision.revision_number,
        "manifest_hash": revision.manifest_hash,
        "manifest": revision.manifest or {},
        "verdict": revision.verdict,
        "confidence": revision.confidence,
        "direction": revision.direction,
        "summary": revision.summary,
        "rationale": revision.rationale,
        "tx_hash": revision.tx_hash,
    }