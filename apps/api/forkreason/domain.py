"""Domain types for the forensic pipeline.

These are plain dataclasses, not ORM objects and not Pydantic models: the
pipeline is pure computation over immutable inputs, and it must stay
testable without a database or an HTTP layer (constitution VI.23).
"""

from __future__ import annotations

import dataclasses
from typing import Any, Literal

Verdict = Literal[
    "INDEPENDENT",
    "SHARED_UPSTREAM",
    "DECLARED_FORK",
    "LIKELY_DERIVED",
    "HEAVILY_DERIVED",
    "INSUFFICIENT_EVIDENCE",
]

Confidence = Literal["LOW", "MEDIUM", "HIGH"]

Direction = Literal["ORIGIN_TO_TARGET", "TARGET_TO_ORIGIN", "NONE"]

DnaLayer = Literal[
    "CODE", "ARCHITECTURE", "HISTORY", "BUG", "TEST", "LANGUAGE"
]

VERDICTS: frozenset[str] = frozenset(
    {
        "INDEPENDENT",
        "SHARED_UPSTREAM",
        "DECLARED_FORK",
        "LIKELY_DERIVED",
        "HEAVILY_DERIVED",
        "INSUFFICIENT_EVIDENCE",
    }
)
CONFIDENCES: frozenset[str] = frozenset({"LOW", "MEDIUM", "HIGH"})
DIRECTIONS: frozenset[str] = frozenset(
    {"ORIGIN_TO_TARGET", "TARGET_TO_ORIGIN", "NONE"}
)
DNA_LAYERS: frozenset[str] = frozenset(
    {"CODE", "ARCHITECTURE", "HISTORY", "BUG", "TEST", "LANGUAGE"}
)

# Explanation kinds that must always be evaluated (spec FR-C-001).
EXPLANATION_KINDS: tuple[str, ...] = (
    "TARGET_DERIVED_FROM_ORIGIN",
    "SHARED_UPSTREAM",
    "INDEPENDENT_SAME_SPEC",
    "INSUFFICIENT_HISTORY",
    "DECLARED_FORK",
    "POST_DERIVATION_DIVERGENCE",
)

# Terms the product must never emit (constitution I.1). Enforced by test.
BANNED_TERMS: tuple[str, ...] = (
    "stolen",
    "illegal",
    "copyright infringement",
    "infringement",
    "plagiarized",
    "plagiarism",
    "theft",
    "thief",
)


@dataclasses.dataclass(frozen=True, slots=True)
class FileEntry:
    """One analyzed file from a snapshot."""

    path: str
    size: int
    sha256: str
    language: str
    text: str | None
    truncated: bool = False


@dataclasses.dataclass(frozen=True, slots=True)
class CommitEntry:
    """One commit from a snapshot's history."""

    sha: str
    timestamp: int
    author: str
    message: str


@dataclasses.dataclass(frozen=True, slots=True)
class RepoProfile:
    """Everything the pipeline needs about one side of a comparison."""

    full_name: str
    commit_sha: str
    files: tuple[FileEntry, ...]
    commits: tuple[CommitEntry, ...]
    description: str = ""
    is_fork: bool = False
    parent_full_name: str | None = None
    # The repository's true creation timestamp, from the hosting provider rather
    # than from the commit log we read. `commits` is capped by
    # ANALYSIS_MAX_COMMITS and so holds only the most recent history: a
    # repository with 20,000 commits reports the first commit it falls inside
    # that window, not its actual first commit. Any chronology reasoning that
    # depends on "which repository came first" must use this field instead, or it
    # will confidently compare two arbitrary recent commits and call it history.
    first_commit_at: int | None = None

    def file_by_path(self, path: str) -> FileEntry | None:
        for f in self.files:
            if f.path == path:
                return f
        return None


@dataclasses.dataclass(frozen=True, slots=True)
class Evidence:
    """One evidence finding with full provenance."""

    id: str
    dna_layer: DnaLayer
    evidence_type: str
    strength: Confidence
    score: float
    rationale: str
    origin_ref: dict[str, Any]
    target_ref: dict[str, Any]
    excerpt: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "dna_layer": self.dna_layer,
            "evidence_type": self.evidence_type,
            "strength": self.strength,
            "score": round(self.score, 4),
            "rationale": self.rationale,
            "origin_ref": self.origin_ref,
            "target_ref": self.target_ref,
            "excerpt": self.excerpt,
        }


@dataclasses.dataclass(frozen=True, slots=True)
class AlternativeExplanation:
    """A competing explanation with an evidence-derived support level."""

    kind: str
    support: Confidence
    score: float
    rationale: str
    evidence_refs: tuple[str, ...] = ()


@dataclasses.dataclass(frozen=True, slots=True)
class UpstreamCandidate:
    full_name: str
    commit_sha: str
    score: float
    evidence_refs: tuple[str, ...] = ()
    created_before_target: bool = False


@dataclasses.dataclass(frozen=True, slots=True)
class AnalysisOutcome:
    """The pipeline's deterministic verdict before consensus."""

    verdict: Verdict
    confidence: Confidence
    direction: Direction
    summary: str
    evidence: tuple[Evidence, ...]
    conflicting: tuple[Evidence, ...]
    explanations: tuple[AlternativeExplanation, ...]
    upstream_candidates: tuple[UpstreamCandidate, ...]
    shared_upstream: str | None
    independent_origin_plausibility: Confidence
    origin_timeline: tuple[dict[str, Any], ...]
    target_timeline: tuple[dict[str, Any], ...]


class AnalysisError(Exception):
    """Raised when analysis cannot complete. Carries a stable error code."""

    def __init__(self, code: str, message: str, *, detail: str | None = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.detail = detail


class IntakeError(AnalysisError):
    """Repository could not be safely ingested."""


class UnsupportedRepositoryError(IntakeError):
    """Repository is outside what V1 accepts (private, non-GitHub, too large)."""


class AnalysisTimeoutError(AnalysisError):
    """Analysis exceeded its wall-clock budget."""


class AnalysisCancelledError(AnalysisError):
    """Cancellation was requested for this job."""


def strength_for_score(score: float) -> Confidence:
    """Map a bounded 0..1 evidence score to a confidence bucket.

    Buckets only. ForkReason has no calibration methodology, so a number is
    never surfaced to users (constitution I.5).
    """
    if score >= 0.66:
        return "HIGH"
    if score >= 0.38:
        return "MEDIUM"
    return "LOW"