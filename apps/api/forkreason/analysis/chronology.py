"""Chronology analysis and shared-upstream discovery.

These are the two places where ForkReason is not just measuring similarity —
they are the places where it reasons about *when* things happened and about
*what both repositories might have come from*.

All rules here are deterministic and live in code, never in model prose
(constitution II.10, FR-H.009).
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from typing import Sequence

from ..domain import RepoProfile

# Signals too common to ever indicate a shared ancestor.
_UPSTREAM_STOPWORDS: frozenset[str] = frozenset(
    {
        "src", "lib", "app", "core", "main", "index", "init", "test", "tests",
        "util", "utils", "helper", "helpers", "common", "base", "api", "web",
        "client", "server", "config", "docs", "doc", "example", "examples",
        "build", "dist", "bin", "data", "model", "models", "view", "views",
        "component", "components", "service", "services", "type", "types",
    }
)


def _ts(value: int) -> str:
    return dt.datetime.fromtimestamp(value, tz=dt.timezone.utc).isoformat()


def repo_timeline(profile: RepoProfile, limit: int = 40) -> list[dict]:
    """Real commit markers for the Lineage Timeline view."""
    if not profile.commits:
        return []
    ordered = sorted(profile.commits, key=lambda c: c.timestamp)
    markers = []
    for commit in ordered[:limit]:
        markers.append(
            {
                "sha": commit.sha,
                "short_sha": commit.sha[:7],
                "timestamp": commit.timestamp,
                "date": _ts(commit.timestamp),
                "author": commit.author,
                "message": commit.message[:160],
            }
        )
    return markers


def chronological_order(
    origin: RepoProfile, target: RepoProfile
) -> tuple[str, dict]:
    """Classify which repository came first.

    Returns a direction label plus the supporting facts. A target that predates
    the origin is decisive evidence against origin→target derivation, and this
    is checked before any similarity signal is allowed to speak.
    """
    o_first = min((c.timestamp for c in origin.commits), default=None)
    o_last = max((c.timestamp for c in origin.commits), default=None)
    t_first = min((c.timestamp for c in target.commits), default=None)
    t_last = max((c.timestamp for c in target.commits), default=None)

    if o_first is None or o_last is None or t_first is None or t_last is None:
        return "UNKNOWN", {
            "reason": "One or both repositories have no usable commit history.",
        }

    if t_first < o_first:
        return "TARGET_PREDATES_ORIGIN", {
            "origin_first": _ts(o_first),
            "target_first": _ts(t_first),
            "margin_days": abs(t_first - o_first) // 86400,
        }

    if t_first >= o_last:
        return "TARGET_AFTER_ORIGIN_MATURED", {
            "origin_first": _ts(o_first),
            "origin_last": _ts(o_last),
            "target_first": _ts(t_first),
            "margin_days": (t_first - o_last) // 86400,
        }

    return "OVERLAPPING", {
        "origin_first": _ts(o_first),
        "origin_last": _ts(o_last),
        "target_first": _ts(t_first),
        "target_last": _ts(t_last),
    }


@dataclass(frozen=True, slots=True)
class UpstreamSignal:
    repo: str
    score: float
    reasons: tuple[str, ...]
    created_before_target: bool


def _module_tokens(profile: RepoProfile) -> dict[str, float]:
    """Distinctive path-component tokens with counts.

    Paths alone are a weak signal: a fork that renamed its modules (which is
    normal and expected) shares no path tokens with its parent even though it
    shares most of its implementation. So path tokens are combined with
    distinctive *content* tokens, weighted lower because content similarity is
    the more likely explanation and therefore weaker standalone evidence of a
    specific shared ancestor.
    """
    counts: dict[str, float] = {}

    def add(token: str, weight: float) -> None:
        if token and token not in _UPSTREAM_STOPWORDS and len(token) >= 4:
            counts[token] = counts.get(token, 0) + weight

    for f in profile.files:
        parts = f.path.replace("\\", "/").split("/")
        for part in parts[:-1]:
            for tok in part.replace("-", "_").replace("_", "").lower().split():
                add(tok, 1.0)
        stem = parts[-1].rsplit(".", 1)[0]
        for tok in stem.replace("-", "_").replace("_", "").lower().split():
            add(tok, 1.0)

        # Content: distinctive identifiers and rare constants shared across all
        # three projects are what actually identify a common ancestor after a
        # rename. Weight 1.5 matches a path-token hit so that content alone can
        # qualify, but a single incidental word still cannot.
        if f.text is not None:
            from .fingerprint import normalized_tokens, rarity

            seen: set[str] = set()
            for tok in normalized_tokens(f.text):
                if rarity(tok) >= 0.5 and tok not in seen:
                    seen.add(tok)
                    add(tok, 1.5)

    return counts


def find_shared_upstream_candidates(
    origin: RepoProfile,
    target: RepoProfile,
    extra_candidates: Sequence[RepoProfile] = (),
    limit: int = 8,
) -> list[UpstreamSignal]:
    """Rank plausible common ancestors.

    GitHub itself tells us the strongest signal available: when both
    repositories declare the same `parent_full_name`, that is a declared fork
    relationship and outranks any heuristic similarity.

    Beyond that, a candidate must be a plausible ancestor of *both* sides, so
    it must predate whichever repository came later. A "common ancestor" that
    appeared after one of the participants is not an ancestor at all.
    """
    later_first = max(
        [
            ts
            for ts in (
                min((c.timestamp for c in origin.commits), default=None),
                min((c.timestamp for c in target.commits), default=None),
            )
            if ts is not None
        ],
        default=None,
    )

    out: list[UpstreamSignal] = []
    seen: set[str] = set()

    # 1. Declared fork parents — the strongest available signal.
    for profile in (origin, target):
        parent = profile.parent_full_name
        if parent and parent not in seen:
            seen.add(parent)
            out.append(
                UpstreamSignal(
                    repo=parent,
                    score=0.95,
                    reasons=("declared_upstream_parent",),
                    created_before_target=True,
                )
            )

    # 2. Heuristic candidates from any additional repositories supplied.
    o_tokens = _module_tokens(origin)
    t_tokens = _module_tokens(target)
    # A token must be substantially present on both sides to imply ancestry.
    # The >=1.5 threshold admits two content hits (0.5 each) or a path hit plus
    # content, and rejects a single incidental mention.
    shared_tokens = {
        tok for tok in (set(o_tokens) & set(t_tokens))
        if o_tokens[tok] >= 1.5 and t_tokens[tok] >= 1.5
    }

    for candidate in extra_candidates:
        c_tokens = _module_tokens(candidate)
        if not c_tokens:
            continue
        overlap = {t for t in shared_tokens if t in c_tokens}
        if not overlap:
            continue
        score = min(0.85, 0.25 + 0.12 * len(overlap))
        # Ancestry is decided by when the candidate *began*, not when its last
        # commit landed: a repository that kept receiving commits for years can
        # still be the ancestor of a fork taken early in that window.
        created_before = True
        if later_first is not None:
            candidate_first = min((c.timestamp for c in candidate.commits), default=None)
            created_before = candidate_first is None or candidate_first <= later_first
        out.append(
            UpstreamSignal(
                repo=candidate.full_name,
                score=score if created_before else score * 0.3,
                reasons=tuple(sorted(overlap)[:6]),
                created_before_target=created_before,
            )
        )

    out.sort(key=lambda s: (-s.score, s.repo))
    return out[:limit]