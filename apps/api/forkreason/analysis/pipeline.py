"""Analysis pipeline orchestration.

Eight real stages, each one observable and each one honest about what it did.
The frontend renders these stage states directly; there is no synthetic
percentage anywhere (constitution VI.25, spec FR-I-007).

The pipeline is a pure function of two `RepoProfile`s plus configuration. Given
the same pinned commits it produces byte-identical output, which is what makes
the manifest hash meaningful.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from ..domain import (
    AnalysisCancelledError,
    AnalysisOutcome,
    AnalysisTimeoutError,
    Evidence,
    RepoProfile,
)
from ..ids import case_id_for
from ..models import PIPELINE_STAGES
from .alternatives import ExplanationInputs, evaluate_explanations, select_verdict
from ..domain import UpstreamCandidate
from .chronology import (
    UpstreamSignal,
    chronological_order,
    find_shared_upstream_candidates,
    repo_timeline,
)
from .dna import (
    architecture_dna,
    bug_dna,
    code_dna,
    history_dna,
    language_dna,
    test_dna,
)
from .manifest import build_consensus_digest, build_manifest, manifest_hash
from .scoring import EvidenceBuilder, count_by_strength

StageReporter = Callable[[str, str], None]


@dataclass(slots=True)
class PipelineConfig:
    max_evidence_items: int = 120
    excerpt_limit: int = 600
    digest_limit: int = 12000
    timeout_seconds: int = 600
    upstream_candidate_limit: int = 8


@dataclass(slots=True)
class PipelineResult:
    outcome: AnalysisOutcome
    manifest: dict[str, Any]
    manifest_hash: str
    consensus_digest: str
    case_id: str
    evidence_counts: dict[str, int]
    dropped_weak_evidence: int
    elapsed_seconds: float


def _noop_reporter(stage: str, state: str) -> None:
    return None


def run_pipeline(
    origin: RepoProfile,
    target: RepoProfile,
    config: PipelineConfig | None = None,
    upstream_pool: tuple[RepoProfile, ...] = (),
    report: StageReporter | None = None,
    *,
    cancel_check: Callable[[], bool] | None = None,
    deadline: float | None = None,
) -> PipelineResult:
    cfg = config or PipelineConfig()
    report = report or _noop_reporter
    started = time.monotonic()

    def checkpoint() -> None:
        if cancel_check is not None and cancel_check():
            raise AnalysisCancelledError("analysis_cancelled", "Analysis was cancelled.")
        if deadline is not None and time.monotonic() > deadline:
            raise AnalysisTimeoutError(
                "analysis_timeout",
                "Analysis exceeded its wall-clock budget.",
            )

    builder = EvidenceBuilder(limit=cfg.max_evidence_items)
    conflicting: list[Evidence] = []

    # -- Stage 1: repository snapshots -----------------------------------
    report(PIPELINE_STAGES[0], "working")
    checkpoint()
    if not origin.files or not target.files:
        raise AnalysisCancelledError(
            "empty_snapshot",
            "One repository produced no analyzable files.",
        )
    report(PIPELINE_STAGES[0], "complete")

    # -- Stage 2: commit history -----------------------------------------
    report(PIPELINE_STAGES[1], "working")
    checkpoint()
    chronology, chronology_detail = chronological_order(origin, target)
    origin_timeline = repo_timeline(origin)
    target_timeline = repo_timeline(target)
    report(PIPELINE_STAGES[1], "complete")

    # -- Stage 3: structural fingerprints --------------------------------
    report(PIPELINE_STAGES[2], "working")
    checkpoint()
    code_dna(origin, target, builder, cfg.excerpt_limit)
    architecture_dna(origin, target, builder, cfg.excerpt_limit)
    report(PIPELINE_STAGES[2], "complete")

    # -- Stage 4: historical signals --------------------------------------
    report(PIPELINE_STAGES[3], "working")
    checkpoint()
    history_dna(origin, target, builder, cfg.excerpt_limit)
    bug_dna(origin, target, builder, cfg.excerpt_limit)
    test_dna(origin, target, builder, cfg.excerpt_limit)
    language_dna(origin, target, builder, cfg.excerpt_limit)
    report(PIPELINE_STAGES[3], "complete")

    # A target that predates the origin cannot be derived from it. Anything the
    # similarity layers produced is re-labelled as conflicting rather than
    # deleted: the user must see what argues against the timeline.
    if chronology == "TARGET_PREDATES_ORIGIN" or any(
        item.is_counter_signal for item in builder.ranked()):
        for item in builder.ranked():
            if item.evidence_type == "target_predates_origin":
                continue
            if item.is_counter_signal:
                # The counter-signal itself is the explanation, not a similarity
                # finding to be re-labelled.
                continue
            conflicting.append(
                Evidence(
                    id=item.id,
                    dna_layer=item.dna_layer,
                    evidence_type=item.evidence_type,
                    strength=item.strength,
                    score=item.score,
                    # The original rationale describes what was observed. A
                    # contradicting item must also say *why* it is being
                    # discounted, or the report shows evidence that appears to
                    # support the verdict while the verdict went the other way.
                    rationale=(
                        "Observed, but in tension with the commit timeline, "
                        "which places the target's first commit before the "
                        f"origin's. {item.rationale}"
                    ),
                    origin_ref=item.origin_ref,
                    target_ref=item.target_ref,
                    excerpt=item.excerpt,
                )
            )

    # -- Stage 5: shared upstream -----------------------------------------
    report(PIPELINE_STAGES[4], "working")
    checkpoint()
    upstream = find_shared_upstream_candidates(
        origin, target, upstream_pool, limit=cfg.upstream_candidate_limit
    )
    shared_upstream = upstream[0].repo if upstream else None
    upstream_score = upstream[0].score if upstream else 0.0
    if shared_upstream:
        builder.add(
            Evidence(
                id="upstream-candidate-" + shared_upstream,
                dna_layer="HISTORY",
                evidence_type="shared_upstream_candidate",
                strength="HIGH" if upstream_score >= 0.66 else "MEDIUM",
                score=upstream_score,
                rationale=(
                    f"{shared_upstream} is a plausible common ancestor of both "
                    "repositories."
                ),
                origin_ref={"repo": origin.full_name, "commit": origin.commit_sha},
                target_ref={"repo": target.full_name, "commit": target.commit_sha},
                excerpt=", ".join(upstream[0].reasons[:6]),
            )
        )
    report(PIPELINE_STAGES[4], "complete")

    # -- Stage 6: alternative explanations -------------------------------
    report(PIPELINE_STAGES[5], "working")
    checkpoint()
    ranked = builder.ranked()
    explanations = evaluate_explanations(
        ExplanationInputs(
            origin=origin,
            target=target,
            evidence=tuple(ranked),
            conflicting=tuple(conflicting),
            chronology=chronology,
            chronology_detail=chronology_detail,
            shared_upstream=shared_upstream,
            upstream_score=upstream_score,
            total_files_origin=len(origin.files),
            total_files_target=len(target.files),
        )
    )
    report(PIPELINE_STAGES[5], "complete")

    # -- Decision ---------------------------------------------------------
    verdict, confidence, direction, independent_plausibility = select_verdict(
        explanations,
        evidence=tuple(ranked),
        chronology=chronology,
        shared_upstream=shared_upstream,
        origin=origin,
        target=target,
    )
    summary = _summary_for(verdict, origin, target, chronology, shared_upstream, ranked)

    # Evidence that argues against the selected verdict is preserved and shown
    # (constitution II.8). Anything already relabelled as a timeline tension is
    # left alone; re-appending the original would duplicate it and reintroduce
    # an unexplained copy that appears to support the opposite conclusion.
    already_flagged = {item.id for item in conflicting}

    def add_as_conflicting(item: Evidence, why: str) -> None:
        if item.id in already_flagged:
            return
        conflicting.append(
            Evidence(
                id=item.id,
                dna_layer=item.dna_layer,
                evidence_type=item.evidence_type,
                strength=item.strength,
                score=item.score,
                rationale=f"Argues against the {verdict} verdict: {why} {item.rationale}",
                origin_ref=item.origin_ref,
                target_ref=item.target_ref,
                excerpt=item.excerpt,
            )
        )
        already_flagged.add(item.id)

    if verdict in {"INDEPENDENT", "INSUFFICIENT_EVIDENCE"}:
        for item in ranked:
            if item.score >= 0.5:
                add_as_conflicting(
                    item, "substantial similarity was observed but the evidence did not establish lineage."
                )
                break
    elif verdict == "SHARED_UPSTREAM":
        for item in ranked:
            if item.dna_layer == "BUG" and item.score >= 0.4:
                add_as_conflicting(
                    item,
                    "a shared defect signature points more directly at derivation "
                    "than at common ancestry.",
                )
                break

    case_id = case_id_for(
        origin.full_name, origin.commit_sha, target.full_name, target.commit_sha
    )
    manifest = build_manifest(
        case_id=case_id,
        origin=origin,
        target=target,
        verdict=verdict,
        confidence=confidence,
        direction=direction,
        shared_upstream=shared_upstream,
        independent_origin_plausibility=independent_plausibility,
        evidence=tuple(ranked),
        conflicting=tuple(conflicting),
        explanations=tuple(explanations),
        upstream_candidates=tuple(
            {
                "repo": s.repo,
                "score": s.score,
                "reasons": list(s.reasons),
                "created_before_target": s.created_before_target,
            }
            for s in upstream
        ),
        chronology=chronology,
        chronology_detail=chronology_detail,
        summary=summary,
    )
    digest = build_consensus_digest(manifest, cfg.digest_limit)

    # -- Stage 7: evidence manifest --------------------------------------
    report(PIPELINE_STAGES[6], "working")
    checkpoint()
    digest_hash = manifest_hash(manifest)
    report(PIPELINE_STAGES[6], "complete")

    # -- Stage 8: consensus preparation ----------------------------------
    report(PIPELINE_STAGES[7], "working")
    checkpoint()
    if not digest:
        raise AnalysisCancelledError(
            "empty_digest", "No bounded evidence digest could be produced."
        )
    report(PIPELINE_STAGES[7], "complete")

    outcome = AnalysisOutcome(
        verdict=verdict,
        confidence=confidence,
        direction=direction,
        summary=summary,
        evidence=tuple(ranked),
        conflicting=tuple(conflicting),
        explanations=tuple(explanations),
        upstream_candidates=tuple(
            UpstreamCandidate(
                full_name=s.repo,
                commit_sha="",
                score=s.score,
                evidence_refs=tuple(s.reasons),
                created_before_target=s.created_before_target,
            )
            for s in upstream[: cfg.upstream_candidate_limit]
        ),
        shared_upstream=shared_upstream,
        independent_origin_plausibility=independent_plausibility,
        origin_timeline=tuple(origin_timeline),
        target_timeline=tuple(target_timeline),
    )

    return PipelineResult(
        outcome=outcome,
        manifest=manifest,
        manifest_hash=digest_hash,
        consensus_digest=digest,
        case_id=case_id,
        evidence_counts=count_by_strength(ranked),
        dropped_weak_evidence=builder.dropped_weak,
        elapsed_seconds=round(time.monotonic() - started, 3),
    )


def _summary_for(
    verdict: str,
    origin: RepoProfile,
    target: RepoProfile,
    chronology: str,
    shared_upstream: str | None,
    evidence: list[Evidence],
) -> str:
    strong = [e for e in evidence if e.strength == "HIGH"]
    conflicting = [e for e in evidence if e.dna_layer in {"HISTORY", "BUG"} and e.score < 0.3]
    detail = f"{len(strong)} strong signal(s)"
    if conflicting:
        detail += f", {len(conflicting)} weaker historical signal(s)"
    a = origin.full_name
    b = target.full_name
    match verdict:
        case "LIKELY_DERIVED":
            return (
                f"{b} shows strong evidence of deriving from {a}: "
                f"{detail}. Similarity is supported by chronology, not merely "
                "by matching code."
            )
        case "HEAVILY_DERIVED":
            return (
                f"{b} shares lineage with {a} but has since diverged "
                f"substantially: {detail}. The relationship is real but the "
                "current code differs considerably."
            )
        case "SHARED_UPSTREAM":
            return (
                f"Both {a} and {b} appear to descend from {shared_upstream or 'a common upstream'}. "
                f"The shared signals are better explained by common ancestry "
                "than by direct derivation."
            )
        case "DECLARED_FORK":
            return (
                f"{b} declares {a} as its upstream. This is a recorded, "
                "legitimate fork relationship."
            )
        case "INDEPENDENT":
            return (
                f"{a} and {b} show similarity consistent with implementing the "
                f"same specification independently: {detail}. No shared history "
                "was found."
            )
        case _:
            return (
                f"ForkReason could not establish a lineage relationship between "
                f"{a} and {b} from the available evidence. {detail}. More "
                "history, or repositories with substantive commits, would "
                "likely be required."
            )