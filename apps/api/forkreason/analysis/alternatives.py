"""Alternative explanation analysis.

ForkReason's credibility rests on this file. A plagiarism detector asks "how
similar are these?" and reports the number. A lineage tool must ask "what else
could explain what I am seeing?" and answer that question honestly, including
when the answer is boring.

Every explanation in `EXPLANATION_KINDS` is scored on every analysis, whether
or not it is likely. An explanation that is never evaluated cannot be reported
as considered (spec FR-C-001).
"""

from __future__ import annotations

from dataclasses import dataclass

from .scoring import strength_for_score, weighted_case_score
from ..domain import AlternativeExplanation, Confidence, Evidence, RepoProfile

# Sentinels and thresholds. These are calibration-free: they decide which
# explanation wins, not how confident anyone is in a probability sense.
DERIVATION_FLOOR = 0.42
INDEPENDENT_FLOOR = 0.45
DECLARED_FORK_FLOOR = 0.60


@dataclass(frozen=True, slots=True)
class ExplanationInputs:
    origin: RepoProfile
    target: RepoProfile
    evidence: tuple[Evidence, ...]
    conflicting: tuple[Evidence, ...]
    chronology: str
    chronology_detail: dict
    shared_upstream: str | None
    upstream_score: float
    total_files_origin: int
    total_files_target: int


def _score_layer(evidence: tuple[Evidence, ...], layer: str) -> float:
    return weighted_case_score([e for e in evidence if e.dna_layer == layer])


def _has(evidence: tuple[Evidence, ...], layer: str, *types: str) -> bool:
    return any(
        e.dna_layer == layer and (not types or e.evidence_type in types)
        for e in evidence
    )


def evaluate_explanations(inp: ExplanationInputs) -> list[AlternativeExplanation]:
    """Score every explanation. Highest support wins; ties break conservatively."""
    evidence = inp.evidence
    out: list[AlternativeExplanation] = []

    # --- 1. Target derived from origin -----------------------------------
    # Requires BOTH a compatible timeline AND substantive, multi-layer evidence.
    # Chronology alone is never enough: any two unrelated projects have a
    # compatible timeline, and "the second one started later" is not a finding.
    chronology_supports = inp.chronology in {"TARGET_AFTER_ORIGIN_MATURED", "OVERLAPPING"} or (
        inp.chronology == "ORIGIN_PREDATES_TARGET"
        and _has(evidence, "HISTORY", "target_created_after_origin_matured")
    )
    bug_support = _score_layer(evidence, "BUG")
    history_support = _score_layer(evidence, "HISTORY")
    code_support = _score_layer(evidence, "CODE")
    test_support = _score_layer(evidence, "TEST")
    arch_support = _score_layer(evidence, "ARCHITECTURE")
    language_support = _score_layer(evidence, "LANGUAGE")

    layers_present = {e.dna_layer for e in evidence if e.score >= 0.3}
    multi_layer = len(layers_present) >= 2

    # Subtractive signals that actually discriminate lineage from similarity.
    # A derivation claim requires at least one of them.
    discriminative = (
        bug_support >= 0.20
        or test_support >= 0.25
        or language_support >= 0.25
        or (code_support >= 0.45 and arch_support >= 0.35)
    )

    derivation = 0.0
    if chronology_supports:
        # Permissive only. A small contribution that cannot carry a verdict.
        derivation += 0.14
    if inp.chronology == "TARGET_AFTER_ORIGIN_MATURED":
        derivation += 0.06
    derivation += 0.40 * bug_support
    derivation += 0.18 * history_support
    derivation += 0.16 * code_support
    derivation += 0.14 * test_support
    derivation += 0.10 * arch_support
    derivation += 0.08 * language_support
    if multi_layer:
        derivation += 0.08

    if not chronology_supports:
        # A derivation claim that contradicts the commit timeline is not a
        # weak claim, it is a wrong one.
        derivation = min(derivation, 0.15)
    elif not discriminative:
        # Compatible timeline, nothing that distinguishes derivation from
        # coincidence. This is the "two unrelated projects, one is newer" case.
        derivation = min(derivation, 0.30)
    derivation = max(0.0, min(0.98, derivation))

    out.append(
        AlternativeExplanation(
            kind="TARGET_DERIVED_FROM_ORIGIN",
            support=strength_for_score(derivation),
            score=derivation,
            rationale=_derivation_rationale(inp, layers_present),
            evidence_refs=tuple(
                e.id for e in evidence if e.dna_layer in {"BUG", "HISTORY"}
            )[:8],
        )
    )

    # --- 2. Shared upstream ----------------------------------------------
    shared = 0.0
    if inp.shared_upstream:
        shared = max(0.55, inp.upstream_score)
        if _has(evidence, "HISTORY", "target_created_after_origin_matured"):
            shared += 0.08
        # A strong code signal *without* a distinguishing historical signal is
        # exactly the shared-upstream signature, so code evidence supports it.
        shared += 0.18 * code_support if bug_support < 0.3 else 0.0
    elif _has(evidence, "ARCHITECTURE", "shared_module_boundaries"):
        shared = 0.34 + 0.2 * _score_layer(evidence, "ARCHITECTURE")
    shared = max(0.0, min(0.95, shared))
    out.append(
        AlternativeExplanation(
            kind="SHARED_UPSTREAM",
            support=strength_for_score(shared),
            score=shared,
            rationale=(
                f"Both repositories descend from {inp.shared_upstream}."
                if inp.shared_upstream
                else "No common ancestor was identified; architecture evidence "
                "alone could reflect a shared specification."
            ),
            evidence_refs=tuple(
                e.id for e in evidence if e.dna_layer == "ARCHITECTURE"
            )[:8],
        )
    )

    # --- 3. Independent implementation of the same specification ----------
    independent = 0.0
    if not chronology_supports:
        independent += 0.35
    if code_support > 0 and bug_support < 0.25:
        # Code matches but no distinctive defects: a specification, not a copy.
        independent += 0.28
    if not _has(evidence, "LANGUAGE", "shared_documentation_phrases"):
        independent += 0.18
    if not _has(evidence, "TEST", "shared_distinctive_test_names"):
        independent += 0.12
    if inp.chronology == "TARGET_PREDATES_ORIGIN":
        independent += 0.22
    independent = max(0.0, min(0.95, independent))
    out.append(
        AlternativeExplanation(
            kind="INDEPENDENT_SAME_SPEC",
            support=strength_for_score(independent),
            score=independent,
            rationale=(
                "Similarity is consistent with two projects implementing the same "
                "specification or framework pattern, with no shared history."
            ),
            evidence_refs=tuple(e.id for e in evidence if e.dna_layer == "CODE")[:8],
        )
    )

    # --- 4. Insufficient history -----------------------------------------
    insufficient = 0.0
    if inp.chronology == "UNKNOWN":
        insufficient += 0.6
    if len(evidence) == 0:
        insufficient += 0.3
    if len(evidence) <= 2:
        insufficient += 0.22
    if inp.total_files_origin < 8 or inp.total_files_target < 8:
        insufficient += 0.18
    if not any(
        e.score >= 0.5 and e.dna_layer in {"BUG", "HISTORY"} for e in evidence
    ):
        insufficient += 0.16
    insufficient = max(0.0, min(0.9, insufficient))
    out.append(
        AlternativeExplanation(
            kind="INSUFFICIENT_HISTORY",
            support=strength_for_score(insufficient),
            score=insufficient,
            rationale=(
                "Available history and evidence do not support a lineage "
                "conclusion either way."
            ),
            evidence_refs=(),
        )
    )

    # --- 5. Declared fork -------------------------------------------------
    declared = 0.0
    if inp.origin.parent_full_name == inp.target.full_name or (
        inp.target.parent_full_name == inp.origin.full_name
    ):
        declared = 0.95
    elif inp.shared_upstream and (inp.origin.is_fork or inp.target.is_fork):
        declared = max(declared, 0.62 + 0.2 * inp.upstream_score)
    out.append(
        AlternativeExplanation(
            kind="DECLARED_FORK",
            support=strength_for_score(declared),
            score=declared,
            rationale=(
                "One repository declares the other as its upstream, which is a "
                "legitimate, recorded fork relationship."
            ),
            evidence_refs=(),
        )
    )

    # --- 6. Post-derivation divergence -------------------------------------
    # This explanation presupposes an actual relationship, and it presupposes a
    # *directional* one: divergence after derivation still requires the target
    # to be the later project. When the target predates the origin, nothing can
    # have been derived from it in the origin→target direction, so this
    # explanation is inadmissible regardless of how similar the code is.
    divergence = 0.0
    code_sim = _score_layer(evidence, "CODE")
    arch_sim = _score_layer(evidence, "ARCHITECTURE")
    relatedness = max(
        _score_layer(evidence, layer)
        for layer in ("CODE", "ARCHITECTURE", "BUG", "TEST", "LANGUAGE", "HISTORY")
    ) if evidence else 0.0
    if relatedness >= 0.35 and inp.chronology != "TARGET_PREDATES_ORIGIN":
        divergence += 0.40
        if code_sim < 0.5 and arch_sim < 0.5:
            divergence += 0.20
        if bug_support > 0.3:
            divergence += 0.20
        if _has(evidence, "HISTORY", "target_created_after_origin_matured"):
            divergence += 0.08
    divergence = max(0.0, min(0.9, divergence))
    out.append(
        AlternativeExplanation(
            kind="POST_DERIVATION_DIVERGENCE",
            support=strength_for_score(divergence),
            score=divergence,
            rationale=(
                "Shared structure persists but implementation has diverged "
                "substantially, consistent with derivation followed by heavy "
                "independent change."
            ),
            evidence_refs=tuple(e.id for e in evidence)[:6],
        )
    )

    # Conceding weight: unresolved contradictions weaken the leading claim.
    if inp.conflicting:
        penalty = min(0.2, 0.07 * len(inp.conflicting))
        for item in out:
            if item.kind in {"TARGET_DERIVED_FROM_ORIGIN", "SHARED_UPSTREAM"}:
                object.__setattr__(
                    item, "score", max(0.0, item.score - penalty)
                )

    # Divergence presupposes a supported directional derivation. Similarity
    # cannot stand in for that missing evidence, including after counter-
    # evidence has reduced the derivation score.
    derived = next((item for item in out if item.kind == "TARGET_DERIVED_FROM_ORIGIN"), None)
    divergence = next((item for item in out if item.kind == "POST_DERIVATION_DIVERGENCE"), None)
    if derived is None or divergence is None or derived.score < DERIVATION_FLOOR:
        if divergence is not None:
            object.__setattr__(divergence, "score", 0.0)

    out.sort(key=lambda a: (-a.score, a.kind))
    return out


def _derivation_rationale(inp: ExplanationInputs, layers: set[str]) -> str:
    bits = []
    if inp.chronology == "TARGET_AFTER_ORIGIN_MATURED" or _has(
        inp.evidence, "HISTORY", "target_created_after_origin_matured"
    ):
        bits.append("the target began after the origin matured")
    elif inp.chronology == "OVERLAPPING":
        bits.append("the two histories overlap in time")
    else:
        bits.append("the available timeline does not establish derivation")
    if "BUG" in layers:
        bits.append("shared historical defect signatures")
    if "HISTORY" in layers:
        bits.append("chronological implementation order")
    return (
        "Evidence for derivation: " + ", ".join(bits) + "."
        if bits
        else "No evidence supports a derivation relationship."
    )


def select_verdict(
    explanations: list[AlternativeExplanation],
    *,
    evidence: tuple[Evidence, ...],
    chronology: str,
    shared_upstream: str | None,
    origin: RepoProfile,
    target: RepoProfile,
) -> tuple[str, Confidence, str, Confidence]:
    """Choose the best-supported explanation and derive the contract verdict.

    Returns (verdict, confidence, direction, independent_origin_plausibility).

    When the best explanation does not clear its floor, the answer is
    INSUFFICIENT_EVIDENCE. That is the whole point of the product (constitution
    I.4): a boring, defensible result beats a forced one.
    """
    by_kind = {e.kind: e for e in explanations}
    best = explanations[0] if explanations else None

    def declared_fork() -> bool:
        return (
            origin.parent_full_name == target.full_name
            or target.parent_full_name == origin.full_name
        )

    independent_plausibility: Confidence = "LOW"

    if declared_fork():
        return "DECLARED_FORK", "HIGH", "NONE", "LOW"

    if best is None:
        return "INSUFFICIENT_EVIDENCE", "LOW", "NONE", "LOW"

    # A timeline that puts the target first rules out every origin→target
    # explanation, whatever the similarity scores say. This is the product's
    # central claim enforced at the point where a verdict is produced.
    if chronology == "TARGET_PREDATES_ORIGIN":
        independent = by_kind.get("INDEPENDENT_SAME_SPEC")
        if independent and independent.score >= INDEPENDENT_FLOOR:
            return "INDEPENDENT", independent.support, "NONE", "HIGH"
        return "INSUFFICIENT_EVIDENCE", "LOW", "NONE", "MEDIUM"

    insufficient = by_kind.get("INSUFFICIENT_HISTORY")
    if insufficient and insufficient.score >= 0.6 and best.score < DERIVATION_FLOOR:
        return "INSUFFICIENT_EVIDENCE", insufficient.support, "NONE", "LOW"

    if best.kind == "TARGET_DERIVED_FROM_ORIGIN" and best.score >= DERIVATION_FLOOR:
        independent = by_kind.get("INDEPENDENT_SAME_SPEC")
        independent_plausibility = independent.support if independent else "LOW"
        divergence = by_kind.get("POST_DERIVATION_DIVERGENCE")
        if divergence and divergence.score >= 0.6 and best.score < 0.7:
            return (
                "HEAVILY_DERIVED",
                best.support,
                "ORIGIN_TO_TARGET",
                independent_plausibility,
            )
        return (
            "LIKELY_DERIVED",
            best.support,
            "ORIGIN_TO_TARGET",
            independent_plausibility,
        )

    if best.kind == "SHARED_UPSTREAM" and best.score >= 0.5 and shared_upstream:
        return "SHARED_UPSTREAM", best.support, "NONE", "MEDIUM"

    if best.kind == "INDEPENDENT_SAME_SPEC" and best.score >= INDEPENDENT_FLOOR:
        return "INDEPENDENT", best.support, "NONE", "HIGH"

    if best.kind == "DECLARED_FORK" and best.score >= DECLARED_FORK_FLOOR:
        return "DECLARED_FORK", best.support, "NONE", "LOW"

    if best.kind == "POST_DERIVATION_DIVERGENCE" and best.score >= 0.6:
        return "HEAVILY_DERIVED", best.support, "ORIGIN_TO_TARGET", "MEDIUM"

    # Nothing cleared a floor. Say so.
    return "INSUFFICIENT_EVIDENCE", "LOW", "NONE", independent_plausibility
