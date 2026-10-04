"""Persistence for snapshots, cases, revisions and evidence.

Deliberately a thin module of functions rather than a repository-abstraction
layer: there is exactly one implementation and one consumer for each operation,
so an interface would add indirection without adding a boundary worth testing
(constitution VI.23).

The chain boundary matters here. `Case` stores a *pointer* to the current
revision number; verdict state lives only in append-only `CaseRevision` rows,
and `ChainTransaction` records what was observed on chain. The database indexes
chain state; it is never allowed to become the authority over it (constitution
V.21).
"""

from __future__ import annotations

import datetime as dt
import json
import logging
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..analysis.pipeline import PipelineResult
from ..domain import AnalysisOutcome, Evidence
from ..models import (
    AlternativeExplanation,
    Case,
    CaseRevision,
    ChainTransaction,
    Challenge,
    EvidenceItem,
    EvidenceRelation,
    RepositorySnapshot,
)
from ..repos.snapshot import RepoProfile

log = logging.getLogger(__name__)


def utcnow() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


class ProfileStore:
    """Reads pinned snapshots and writes analysis results."""

    def __init__(self, snapshot_dir: str | Path) -> None:
        self.snapshot_dir = Path(snapshot_dir)

    # --- snapshots -------------------------------------------------------

    def find_snapshot(
        self, session: Session, full_name: str, commit_sha: str
    ) -> RepositorySnapshot | None:
        """Find an already-recorded snapshot for this pinned commit.

        The primary key is a hash, but the table also constrains
        (full_name, commit_sha). Those can disagree — the same pinned commit may
        already be recorded under a different id. Callers that re-derive a
        snapshot's on-disk location from its id must consult this first, or they
        will look in a directory that was never created.
        """
        return session.execute(
            select(RepositorySnapshot).where(
                RepositorySnapshot.full_name == full_name[:240],
                RepositorySnapshot.commit_sha == commit_sha[:64],
            )
        ).scalar_one_or_none()

    def upsert_snapshot(self, session: Session, snapshot_id: str, profile: RepoProfile, *, truncated: bool) -> RepositorySnapshot:
        """Record a pinned snapshot. Idempotent on (full_name, commit)."""
        row = session.get(RepositorySnapshot, snapshot_id)
        if row is None:
            row = self.find_snapshot(session, profile.full_name, profile.commit_sha)
        if row is not None:
            # A row written before `repo_created_at` existed can still be
            # completed from the metadata we just fetched. Leaving it NULL would
            # silently drop every chronology claim about that repository, because
            # the bounded commit log cannot stand in for a creation time.
            if row.repo_created_at is None and profile.first_commit_at is not None:
                row.repo_created_at = dt.datetime.fromtimestamp(
                    profile.first_commit_at, tz=dt.timezone.utc
                )
                session.flush()
            return row

        first = min((c.timestamp for c in profile.commits), default=None)
        pushed = (
            dt.datetime.fromtimestamp(first, tz=dt.timezone.utc) if first is not None else None
        )
        row = RepositorySnapshot(
            id=snapshot_id,
            owner=profile.full_name.split("/", 1)[0][:100],
            name=profile.full_name.split("/", 1)[-1][:120],
            full_name=profile.full_name[:240],
            commit_sha=profile.commit_sha[:64],
            default_branch="main",
            description=(profile.description or "")[:2000],
            is_fork=bool(profile.is_fork),
            parent_full_name=(profile.parent_full_name or None),
            pushed_at=pushed,
            repo_created_at=(
                dt.datetime.fromtimestamp(
                    profile.first_commit_at, tz=dt.timezone.utc
                )
                if profile.first_commit_at is not None
                else None
            ),
            size_bytes=sum(f.size for f in profile.files),
            file_count=len(profile.files),
            truncated=bool(truncated),
        )
        session.add(row)
        session.flush()
        return row

    def load_profile(self, session: Session, snapshot_id: str) -> RepoProfile | None:
        """Rehydrate a profile from the on-disk pinned tree.

        The database stores the inventory for indexing; the authoritative bytes
        are the extracted tree at the pinned commit. Re-reading them is cheap
        and guarantees we never analyze stale cached text.
        """
        from ..repos.snapshot import build_profile
        from ..repos.github_url import validate_repo_input
        from ..analysis.manifest import MANIFEST_CREATED_BY  # noqa: F401  (import check)
        from ..config import get_settings

        row = session.get(RepositorySnapshot, snapshot_id)
        if row is None:
            return None

        tree = self.snapshot_dir / row.owner / f"{row.name}__{snapshot_id[:16]}"
        if not tree.is_dir():
            return None

        settings = get_settings()
        from ..repos.snapshot import IntakeLimits

        limits = IntakeLimits(
            max_repo_mb=settings.analysis_max_repo_mb,
            max_file_mb=settings.analysis_max_file_mb,
            max_files=settings.analysis_max_files,
            max_commits=settings.analysis_max_commits,
        )
        profile, _ = build_profile(
            _metadata_from_row(row), tree, list(row_commits(session, row.id)), limits
        )
        return profile

    # --- cases -----------------------------------------------------------

    def persist_case(self, session: Session, job_id: str, result: PipelineResult) -> Case:
        """Write the case, its first revision, and all evidence.

        Called inside the worker's transaction, so a crash before commit leaves
        the job retryable and no partial case visible.
        """
        outcome = result.outcome
        case = session.scalar(
            select(Case).where(Case.id == result.case_id)
        )
        if case is None:
            # The pinned commits are what make a finding reproducible, so they
            # are taken from the canonical manifest rather than left blank.
            # Anyone with the same two commits must be able to recompute the
            # manifest hash; a case with no commit recorded cannot be checked.
            manifest = result.manifest or {}
            origin_ref = manifest.get("origin") or {}
            target_ref = manifest.get("target") or {}

            case = Case(
                id=result.case_id,
                job_id=job_id,
                origin_full_name=outcome_origin(result),
                target_full_name=outcome_target(result),
                origin_commit=(origin_ref.get("commit") or "")[:64],
                target_commit=(target_ref.get("commit") or "")[:64],
                manifest_hash=result.manifest_hash,
                current_revision=0,
                lifecycle="resolved",
            )
            session.add(case)
            session.flush()

        self._write_revision(session, case, number=1, outcome=outcome, result=result, submitter=None)
        case.current_revision = max(case.current_revision, 1)
        case.manifest_hash = result.manifest_hash
        case.lifecycle = "resolved"
        session.flush()
        return case

    def _write_revision(
        self,
        session: Session,
        case: Case,
        *,
        number: int,
        outcome: AnalysisOutcome,
        result: PipelineResult | None,
        submitter: str | None,
        tx_hash: str | None = None,
    ) -> CaseRevision:
        """Append an immutable revision. Never updates an existing one."""
        existing = session.scalar(
            select(CaseRevision).where(
                CaseRevision.case_id == case.id,
                CaseRevision.revision_number == number,
            )
        )
        if existing is not None:
            return existing

        revision = CaseRevision(
            id=f"{case.id}-{number}",
            case_id=case.id,
            revision_number=number,
            verdict=outcome.verdict,
            confidence=outcome.confidence,
            direction=outcome.direction,
            shared_upstream=(outcome.shared_upstream or None),
            independent_origin_plausibility=outcome.independent_origin_plausibility,
            manifest_hash=(result.manifest_hash if result else case.manifest_hash),
            manifest=(result.manifest if result else {}),
            rationale=outcome.summary[:2000],
            summary={
                "evidence_count": len(outcome.evidence),
                "conflicting_count": len(outcome.conflicting),
                "explanations": [
                    {"kind": x.kind, "support": x.support, "score": x.score}
                    for x in outcome.explanations
                ],
                "layers": sorted({e.dna_layer for e in outcome.evidence}),
                "origin_timeline": list(outcome.origin_timeline),
                "target_timeline": list(outcome.target_timeline),
                "shared_upstream": outcome.shared_upstream,
            },
            tx_hash=tx_hash,
        )
        session.add(revision)

        for item in outcome.evidence:
            session.add(_evidence_row(case.id, number, item))
        for item in outcome.conflicting:
            session.add(_evidence_row(case.id, number, item, conflicting=True))
        for explanation in outcome.explanations:
            session.add(
                AlternativeExplanation(
                    id=f"{case.id}-{number}-{explanation.kind}",
                    case_id=case.id,
                    revision_number=number,
                    kind=explanation.kind,
                    support=explanation.support,
                    score=explanation.score,
                    rationale=explanation.rationale[:2000],
                    evidence_refs=list(explanation.evidence_refs),
                    is_selected=(explanation.kind == outcome.explanations[0].kind)
                    if outcome.explanations
                    else False,
                )
            )
        for candidate in outcome.upstream_candidates:
            session.add(
                EvidenceRelation(
                    id=f"{case.id}-{number}-upstream-{candidate.full_name.replace('/', '-')}",
                    case_id=case.id,
                    subject_kind="repository",
                    subject_ref=case.origin_full_name,
                    relation="candidate_upstream",
                    object_kind="repository",
                    object_ref=candidate.full_name,
                    weight=candidate.score,
                )
            )

        # Relation edges from evidence to the repositories it came from.
        for item in outcome.evidence[:40]:
            session.add(
                EvidenceRelation(
                    id=f"{item.id}-origin",
                    case_id=case.id,
                    subject_kind="evidence",
                    subject_ref=item.id,
                    relation="observed_in",
                    object_kind="repository",
                    object_ref=str(item.origin_ref.get("repo", "")),
                    weight=item.score,
                )
            )
            session.add(
                EvidenceRelation(
                    id=f"{item.id}-target",
                    case_id=case.id,
                    subject_kind="evidence",
                    subject_ref=item.id,
                    relation="observed_in",
                    object_kind="repository",
                    object_ref=str(item.target_ref.get("repo", "")),
                    weight=item.score,
                )
            )
        session.flush()
        return revision

    def append_revision_from_challenge(
        self,
        session: Session,
        case: Case,
        *,
        challenge: Challenge,
        outcome: AnalysisOutcome,
        manifest_hash: str,
        tx_hash: str | None,
    ) -> CaseRevision:
        """Append revision N+1 after a challenge. Revision N is untouched."""
        number = case.current_revision + 1
        revision = CaseRevision(
            id=f"{case.id}-{number}",
            case_id=case.id,
            revision_number=number,
            verdict=outcome.verdict,
            confidence=outcome.confidence,
            direction=outcome.direction,
            shared_upstream=(outcome.shared_upstream or None),
            independent_origin_plausibility=outcome.independent_origin_plausibility,
            manifest_hash=manifest_hash,
            rationale=outcome.summary[:2000],
            summary={
                "evidence_count": len(outcome.evidence),
                "challenged_by": challenge.submitter,
                "challenge_rationale": challenge.rationale[:500],
                "layers": sorted({e.dna_layer for e in outcome.evidence}),
            },
            tx_hash=tx_hash,
        )
        session.add(revision)
        for item in outcome.evidence:
            session.add(_evidence_row(case.id, number, item))
        case.current_revision = number
        case.manifest_hash = manifest_hash
        case.lifecycle = "challenged"
        challenge.resulting_revision = number
        challenge.status = "recorded"
        session.flush()
        return revision

    # --- chain -----------------------------------------------------------

    def record_chain_transaction(
        self,
        session: Session,
        *,
        tx_hash: str,
        case_id: str | None,
        kind: str,
        network: str,
        status: str,
        payload_summary: dict | None = None,
    ) -> ChainTransaction:
        """Mirror a chain transaction for indexing. Never the authority."""
        row = session.get(ChainTransaction, tx_hash[:80])
        if row is not None:
            row.status = status
            session.flush()
            return row
        row = ChainTransaction(
            id=tx_hash[:80],
            case_id=case_id,
            kind=kind,
            network=network,
            status=status,
            payload_summary=payload_summary or {},
        )
        session.add(row)
        session.flush()
        return row


# --- helpers -------------------------------------------------------------


def _metadata_from_row(row: RepositorySnapshot):
    from ..repos.github_url import validate_repo_input
    from ..repos.snapshot import RepoMetadata

    ref = validate_repo_input(row.full_name)
    return RepoMetadata(
        ref=ref,
        commit_sha=row.commit_sha,
        default_branch=row.default_branch,
        description=row.description or "",
        is_fork=row.is_fork,
        parent_full_name=row.parent_full_name,
        size_bytes=row.size_bytes,
        pushed_at=int(row.pushed_at.timestamp()) if row.pushed_at else None,
        created_at=int(row.repo_created_at.timestamp()) if row.repo_created_at else None,
    )


def row_commits(session: Session, snapshot_id: str) -> list:
    """Commits recorded for a snapshot, oldest first."""
    from ..models import AnalysisJob  # noqa: F401

    row = session.get(RepositorySnapshot, snapshot_id)
    if row is None:
        return []
    # Commits are stored on disk alongside the tree; see cache_profile_metadata.
    meta = (
        Path(str(row.snapshot_path))
        if row.snapshot_path
        else None
    )
    if meta is None or not meta.is_file():
        return []
    try:
        data = json.loads(meta.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    from ..domain import CommitEntry

    return [
        CommitEntry(
            sha=c["sha"], timestamp=c["timestamp"], author=c["author"], message=c["message"]
        )
        for c in data.get("commits", [])
    ]


def _evidence_row(case_id: str, revision_number: int, item: Evidence, *, conflicting: bool = False) -> EvidenceItem:
    return EvidenceItem(
        id=f"{item.id}-{revision_number}" + ("-c" if conflicting else ""),
        case_id=case_id,
        revision_number=revision_number,
        dna_layer=item.dna_layer,
        evidence_type=item.evidence_type if not conflicting else f"conflicting:{item.evidence_type}",
        strength=item.strength,
        score=item.score,
        rationale=item.rationale[:2000],
        origin_source=item.origin_ref,
        target_source=item.target_ref,
        excerpt=(item.excerpt or "")[:2000],
    )


def outcome_origin(result: PipelineResult) -> str:
    return str(result.manifest["origin"]["full_name"])


def outcome_target(result: PipelineResult) -> str:
    return str(result.manifest["target"]["full_name"])