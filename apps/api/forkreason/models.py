"""SQLAlchemy ORM models.

Single module by design: the schema is small, the relationships are dense, and
splitting it across a package would add indirection without adding clarity
(constitution VI.23).

Invariants enforced here rather than in application code:
  * CaseRevision rows are append-only; nothing updates an existing revision.
  * (case_id, revision_number) is unique, so a revision can never be rewritten.
  * Current authoritative verdict state lives on Case as a pointer to a
    revision number, never as mutable verdict fields (constitution V.21).
"""

from __future__ import annotations

import datetime as dt
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utcnow() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


class Base(DeclarativeBase):
    type_annotation_map = {dict[str, Any]: JSON, list[Any]: JSON}


class RepositorySnapshot(Base):
    """An immutable, pinned view of one repository at one commit."""

    __tablename__ = "repository_snapshots"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    owner: Mapped[str] = mapped_column(String(100), nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    full_name: Mapped[str] = mapped_column(String(240), nullable=False)
    commit_sha: Mapped[str] = mapped_column(String(64), nullable=False)
    default_branch: Mapped[str] = mapped_column(String(160), default="main")
    description: Mapped[str | None] = mapped_column(Text)
    is_fork: Mapped[bool] = mapped_column(Boolean, default=False)
    parent_full_name: Mapped[str | None] = mapped_column(String(240))
    pushed_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    size_bytes: Mapped[int] = mapped_column(BigInteger, default=0)
    file_count: Mapped[int] = mapped_column(Integer, default=0)
    truncated: Mapped[bool] = mapped_column(Boolean, default=False)
    snapshot_path: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    __table_args__ = (
        UniqueConstraint("full_name", "commit_sha", name="uq_snapshot_repo_commit"),
        Index("ix_snapshot_full_name", "full_name"),
    )


class AnalysisJob(Base):
    """A durable unit of forensic work."""

    __tablename__ = "analysis_jobs"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    status: Mapped[str] = mapped_column(String(32), default="queued", index=True)
    stage: Mapped[str] = mapped_column(String(48), default="queued")
    stage_states: Mapped[dict[str, Any]] = mapped_column(
        JSON, default=lambda: _initial_stage_states()
    )
    origin_snapshot_id: Mapped[str] = mapped_column(
        ForeignKey("repository_snapshots.id"), nullable=False
    )
    target_snapshot_id: Mapped[str] = mapped_column(
        ForeignKey("repository_snapshots.id"), nullable=False
    )
    origin_full_name: Mapped[str] = mapped_column(String(240), nullable=False)
    target_full_name: Mapped[str] = mapped_column(String(240), nullable=False)
    origin_commit: Mapped[str] = mapped_column(String(64), nullable=False)
    target_commit: Mapped[str] = mapped_column(String(64), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(128), unique=True)
    case_id: Mapped[str | None] = mapped_column(String(64))
    error_code: Mapped[str | None] = mapped_column(String(64))
    error_message: Mapped[str | None] = mapped_column(Text)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    lease_expires_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    cancel_requested: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    started_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (Index("ix_jobs_status_created", "status", "created_at"),)


PIPELINE_STAGES: tuple[str, ...] = (
    "repository_snapshots",
    "commit_history",
    "structural_fingerprints",
    "historical_signals",
    "shared_upstream",
    "alternative_explanations",
    "evidence_manifest",
    "consensus_preparation",
)


def _initial_stage_states() -> dict[str, Any]:
    return {stage: "pending" for stage in PIPELINE_STAGES}


class Case(Base):
    """A lineage case. Verdict truth is a pointer to an immutable revision."""

    __tablename__ = "cases"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    job_id: Mapped[str | None] = mapped_column(ForeignKey("analysis_jobs.id"))
    origin_full_name: Mapped[str] = mapped_column(String(240), nullable=False)
    target_full_name: Mapped[str] = mapped_column(String(240), nullable=False)
    origin_commit: Mapped[str] = mapped_column(String(64), nullable=False)
    target_commit: Mapped[str] = mapped_column(String(64), nullable=False)
    manifest_hash: Mapped[str] = mapped_column(String(80), nullable=False)
    current_revision: Mapped[int] = mapped_column(Integer, default=0)
    lifecycle: Mapped[str] = mapped_column(String(32), default="resolved")
    submitter: Mapped[str | None] = mapped_column(String(128))
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=utcnow
    )

    revisions: Mapped[list["CaseRevision"]] = relationship(
        back_populates="case", cascade="all, delete-orphan", order_by="CaseRevision.revision_number"
    )


class CaseRevision(Base):
    """One immutable lineage decision. Never updated, never deleted by the app."""

    __tablename__ = "case_revisions"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    case_id: Mapped[str] = mapped_column(ForeignKey("cases.id"), nullable=False)
    revision_number: Mapped[int] = mapped_column(Integer, nullable=False)
    verdict: Mapped[str] = mapped_column(String(32), nullable=False)
    confidence: Mapped[str] = mapped_column(String(16), nullable=False)
    direction: Mapped[str | None] = mapped_column(String(16))
    shared_upstream: Mapped[str | None] = mapped_column(String(240))
    independent_origin_plausibility: Mapped[str | None] = mapped_column(String(16))
    manifest_hash: Mapped[str] = mapped_column(String(80), nullable=False)
    rationale: Mapped[str | None] = mapped_column(Text)
    summary: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    tx_hash: Mapped[str | None] = mapped_column(String(80))
    network: Mapped[str | None] = mapped_column(String(32))
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    case: Mapped[Case] = relationship(back_populates="revisions")

    __table_args__ = (
        UniqueConstraint("case_id", "revision_number", name="uq_case_revision"),
        Index("ix_revisions_case", "case_id"),
    )


class EvidenceItem(Base):
    """One evidence finding, bound to a pinned commit and a bounded excerpt."""

    __tablename__ = "evidence_items"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    case_id: Mapped[str] = mapped_column(ForeignKey("cases.id"), nullable=False)
    revision_number: Mapped[int] = mapped_column(Integer, default=1)
    dna_layer: Mapped[str] = mapped_column(String(24), nullable=False)
    evidence_type: Mapped[str] = mapped_column(String(64), nullable=False)
    strength: Mapped[str] = mapped_column(String(16), nullable=False)
    score: Mapped[float] = mapped_column(Float, default=0.0)
    rationale: Mapped[str] = mapped_column(Text, default="")
    origin_source: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    target_source: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    excerpt: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    __table_args__ = (
        Index("ix_evidence_case_rev", "case_id", "revision_number"),
        Index("ix_evidence_layer", "dna_layer"),
    )


class EvidenceRelation(Base):
    """A typed link between evidence items, repositories, or upstream candidates."""

    __tablename__ = "evidence_relations"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    case_id: Mapped[str] = mapped_column(ForeignKey("cases.id"), nullable=False)
    subject_kind: Mapped[str] = mapped_column(String(32))
    subject_ref: Mapped[str] = mapped_column(String(240))
    relation: Mapped[str] = mapped_column(String(32))
    object_kind: Mapped[str] = mapped_column(String(32))
    object_ref: Mapped[str] = mapped_column(String(240))
    weight: Mapped[float] = mapped_column(Float, default=1.0)

    __table_args__ = (Index("ix_relations_case", "case_id"),)


class AlternativeExplanation(Base):
    """A competing explanation for observed similarity, with support score."""

    __tablename__ = "alternative_explanations"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    case_id: Mapped[str] = mapped_column(ForeignKey("cases.id"), nullable=False)
    revision_number: Mapped[int] = mapped_column(Integer, default=1)
    kind: Mapped[str] = mapped_column(String(48), nullable=False)
    support: Mapped[str] = mapped_column(String(16), default="LOW")
    score: Mapped[float] = mapped_column(Float, default=0.0)
    rationale: Mapped[str] = mapped_column(Text, default="")
    evidence_refs: Mapped[list[Any]] = mapped_column(JSON, default=list)
    is_selected: Mapped[bool] = mapped_column(Boolean, default=False)

    __table_args__ = (Index("ix_alt_case_rev", "case_id", "revision_number"),)


class Challenge(Base):
    """New evidence submitted against a resolved revision."""

    __tablename__ = "challenges"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    case_id: Mapped[str] = mapped_column(ForeignKey("cases.id"), nullable=False)
    base_revision: Mapped[int] = mapped_column(Integer, nullable=False)
    submitter: Mapped[str] = mapped_column(String(128), nullable=False)
    rationale: Mapped[str] = mapped_column(Text, default="")
    evidence_refs: Mapped[list[Any]] = mapped_column(JSON, default=list)
    status: Mapped[str] = mapped_column(String(32), default="prepared")
    resulting_revision: Mapped[int | None] = mapped_column(Integer)
    tx_hash: Mapped[str | None] = mapped_column(String(80))
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    __table_args__ = (Index("ix_challenges_case", "case_id"),)


class ChainTransaction(Base):
    """Mirror of a GenLayer transaction. Index only — never the authority."""

    __tablename__ = "chain_transactions"

    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    case_id: Mapped[str | None] = mapped_column(String(64), index=True)
    kind: Mapped[str] = mapped_column(String(32))
    network: Mapped[str] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(32))
    block_number: Mapped[int | None] = mapped_column(Integer)
    payload_summary: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    observed_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )