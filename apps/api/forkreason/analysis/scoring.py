"""Evidence scoring and ranking.

The single most important rule in this file: **weak signals stay weak**
(constitution II.7). A match on a token that appears in half of all Python
projects is not evidence of derivation, no matter how precisely it matches.

Scores are bounded in [0, 1] and are an internal ranking aid. Users never see a
number — only a LOW/MEDIUM/HIGH bucket, because ForkReason has no calibration
methodology (constitution I.5).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, Sequence

from ..domain import Confidence, Evidence, strength_for_score

# Minimum similarity before we will even consider emitting evidence. Below this
# a pair is simply unrelated and a fabricated "weak signal" would be noise.
MIN_EMIT_THRESHOLD = 0.12

# A ceiling applied to any evidence derived only from common tokens. This is the
# mechanical guarantee that boilerplate cannot become strong lineage evidence.
COMMON_ONLY_CEILING = 0.33

# Weight per DNA layer when computing the overall case score. Bug and History
# DNA are weighted highest because they are the layers that actually
# discriminate lineage from similarity.
LAYER_WEIGHTS: dict[str, float] = {
    "BUG": 1.00,
    "HISTORY": 0.90,
    "CODE": 0.65,
    "ARCHITECTURE": 0.55,
    "TEST": 0.50,
    "LANGUAGE": 0.40,
}

STRENGTH_ORDER: dict[str, int] = {"LOW": 1, "MEDIUM": 2, "HIGH": 3}


@dataclass(slots=True)
class EvidenceBuilder:
    """Accumulates candidate evidence, then emits only what survives ranking."""

    limit: int
    items: list[Evidence] = field(default_factory=list)
    dropped_weak: int = 0

    def add(self, evidence: Evidence) -> None:
        if evidence.score < MIN_EMIT_THRESHOLD:
            self.dropped_weak += 1
            return
        if len(self.items) >= self.limit:
            return
        self.items.append(evidence)

    def ranked(self) -> list[Evidence]:
        return sorted(
            self.items,
            key=lambda e: (-e.score, e.dna_layer, e.evidence_type, e.id),
        )

    def top(self, n: int) -> list[Evidence]:
        return self.ranked()[:n]

    def __len__(self) -> int:
        return len(self.items)


def cap_by_commonality(score: float, *, common_only: bool) -> float:
    """Hard ceiling for evidence that rests only on boilerplate matches."""
    if not common_only:
        return score
    return min(score, COMMON_ONLY_CEILING)


def lift(base: float, evidence_weight: float, cap: float = 1.0) -> float:
    """Shift a similarity score by an evidence weight, staying in [0, cap].

    Similarity alone never produces lineage; similarity plus historical
    evidence does. This is the arithmetic that encodes that.
    """
    boosted = base * (1.0 + evidence_weight)
    return max(0.0, min(cap, boosted))


def strength(score: float) -> Confidence:
    return strength_for_score(score)


def weighted_case_score(evidence: Iterable[Evidence]) -> float:
    """Aggregate evidence into a bounded case-level support score.

    Uses a saturating sum rather than a mean: three independent strong signals
    should count for more than one signal repeated, but ten weak signals must
    not add up to certainty.
    """
    total = 0.0
    for item in evidence:
        weight = LAYER_WEIGHTS.get(item.dna_layer, 0.5)
        total += item.score * weight
    # Saturating: approaches 1.0 but never reaches it from evidence alone.
    return max(0.0, min(0.99, 1.0 - pow(2.718281828, -total)))


def count_by_strength(evidence: Sequence[Evidence]) -> dict[str, int]:
    counts = {"HIGH": 0, "MEDIUM": 0, "LOW": 0}
    for item in evidence:
        counts[item.strength] = counts.get(item.strength, 0) + 1
    return counts
