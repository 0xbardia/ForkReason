"""The canonical Evidence Manifest.

This is the artifact that crosses the trust boundary: the off-chain pipeline
produces it, hashes it, and the on-chain contract records that hash. Anyone
can recompute the hash from the same pinned commits and check it.

Canonicalization rules (spec FR-D-004):
  * JSON keys sorted, no insignificant whitespace, ASCII-escaped.
  * Floats quantized to 6 decimals so 0.1+0.2 and 0.3 hash identically.
  * Evidence items sorted by content-addressed ID, so collection order during
    analysis cannot change the hash.
  * Explanations and upstream candidates sorted by their stable keys.
  * Nothing is included that is not bounded — no file bodies, no full diffs.
"""

from __future__ import annotations

from typing import Any

from ..domain import (
    AlternativeExplanation,
    Confidence,
    Direction,
    Evidence,
    RepoProfile,
    Verdict,
)
from ..ids import canonical_json, content_hash

MANIFEST_SCHEMA_VERSION = "forkreason/evidence-manifest/v1"
MANIFEST_CREATED_BY = "forkreason-pipeline/1.0.0"

# Never put these in a manifest: they are unbounded and/or not evidence.
MAX_MANIFEST_EVIDENCE = 120
MAX_MANIFEST_EXPLANATIONS = 8
MAX_MANIFEST_UPSTREAM = 6


def build_manifest(
    *,
    case_id: str,
    origin: RepoProfile,
    target: RepoProfile,
    verdict: Verdict,
    confidence: Confidence,
    direction: Direction,
    shared_upstream: str | None,
    independent_origin_plausibility: Confidence,
    evidence: tuple[Evidence, ...],
    conflicting: tuple[Evidence, ...],
    explanations: tuple[AlternativeExplanation, ...],
    upstream_candidates: tuple[dict[str, Any], ...],
    chronology: str,
    chronology_detail: dict[str, Any],
    summary: str,
) -> dict[str, Any]:
    """Build the canonical, bounded manifest. Order of arguments is irrelevant."""
    ordered_evidence = sorted(evidence, key=lambda e: e.id)[:MAX_MANIFEST_EVIDENCE]  # type: ignore[index]
    ordered_conflicting = sorted(conflicting, key=lambda e: e.id)[:MAX_MANIFEST_EVIDENCE]

    return {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "created_by": MANIFEST_CREATED_BY,
        "case_id": case_id,
        "origin": _repo_ref(origin),
        "target": _repo_ref(target),
        "chronology": {"order": chronology, "detail": chronology_detail},
        "decision": {
            "verdict": verdict,
            "confidence": confidence,
            "direction": direction,
            "shared_upstream": shared_upstream or "",
            "independent_origin_plausibility": independent_origin_plausibility,
            "summary": summary,
        },
        "evidence": [e.to_dict() for e in ordered_evidence],
        "conflicting_evidence": [e.to_dict() for e in ordered_conflicting],
        "alternative_explanations": sorted(
            [
                {
                    "kind": x.kind,
                    "support": x.support,
                    "score": x.score,
                    "rationale": x.rationale,
                    "evidence_refs": sorted(x.evidence_refs),
                }
                for x in explanations[:MAX_MANIFEST_EXPLANATIONS]
            ],
            key=lambda x: x["kind"],
        ),
        "common_upstream_candidates": sorted(
            [
                {
                    "repo": c["repo"],
                    "score": float(c["score"]),
                    "reasons": sorted(c.get("reasons", [])),
                    "created_before_target": bool(c.get("created_before_target")),
                }
                for c in upstream_candidates[:MAX_MANIFEST_UPSTREAM]
            ],
            key=lambda x: x["repo"],
        ),
        "counts": {
            "evidence": len(ordered_evidence),
            "conflicting": len(ordered_conflicting),
            "origin_files": len(origin.files),
            "target_files": len(target.files),
            "origin_commits": len(origin.commits),
            "target_commits": len(target.commits),
        },
    }


def manifest_hash(manifest: dict[str, Any]) -> str:
    """SHA-256 over canonical JSON. The value bound on chain."""
    return content_hash(manifest)


def manifest_json(manifest: dict[str, Any]) -> str:
    return canonical_json(manifest)


def _repo_ref(profile: RepoProfile) -> dict[str, Any]:
    stamps = [c.timestamp for c in profile.commits]
    return {
        "full_name": profile.full_name,
        "commit": profile.commit_sha,
        "is_fork": bool(profile.is_fork),
        "parent": profile.parent_full_name or "",
        "first_commit_at": min(stamps) if stamps else 0,
        "last_commit_at": max(stamps) if stamps else 0,
        "file_count": len(profile.files),
        "commit_count": len(profile.commits),
    }


def build_consensus_digest(manifest: dict[str, Any], max_chars: int = 12000) -> str:
    """The bounded text digest sent to consensus.

    Contains only what the decision needs: chronology facts, the strongest
    evidence with short excerpts, and the competing explanations. Repository
    source is never included in full (constitution III.11, FR-H.003).
    """
    decision = manifest["decision"]
    chronology = manifest["chronology"]

    lines: list[str] = []
    lines.append("REPOSITORY A (origin): %s @ %s" % (
        manifest["origin"]["full_name"], manifest["origin"]["commit"][:12]))
    lines.append("REPOSITORY B (target): %s @ %s" % (
        manifest["target"]["full_name"], manifest["target"]["commit"][:12]))
    lines.append("CHRONOLOGY: %s" % chronology.get("order", "UNKNOWN"))
    for key, value in sorted((chronology.get("detail") or {}).items()):
        lines.append("  %s: %s" % (key, value))

    lines.append("")
    lines.append("EVIDENCE (strongest first):")
    for item in sorted(
        manifest["evidence"], key=lambda e: (-float(e["score"]), e["id"])
    )[:12]:
        excerpt = (item.get("excerpt") or "")[:200]
        lines.append(
            "  [%s] %s strength=%s score=%.2f"
            % (item["dna_layer"], item["evidence_type"], item["strength"],
               float(item["score"]))
        )
        lines.append("    why: %s" % item["rationale"][:220])
        if excerpt:
            lines.append("    observed: %s" % excerpt)

    if manifest["conflicting_evidence"]:
        lines.append("")
        lines.append("CONFLICTING EVIDENCE:")
        for item in manifest["conflicting_evidence"][:6]:
            lines.append(
                "  [%s] %s score=%.2f — %s"
                % (item["dna_layer"], item["evidence_type"],
                   float(item["score"]), item["rationale"][:180])
            )

    lines.append("")
    lines.append("COMPETING EXPLANATIONS:")
    for x in sorted(
        manifest["alternative_explanations"], key=lambda e: -float(e["score"])
    ):
        lines.append(
            "  %s support=%s score=%.2f"
            % (x["kind"], x["support"], float(x["score"]))
        )

    if manifest["common_upstream_candidates"]:
        lines.append("")
        lines.append("COMMON UPSTREAM CANDIDATES:")
        for c in manifest["common_upstream_candidates"][:4]:
            lines.append("  %s score=%.2f" % (c["repo"], float(c["score"])))

    digest = "\n".join(lines)
    if len(digest) > max_chars:
        digest = digest[: max_chars - 40] + "\n…[digest truncated at bound]"
    return digest