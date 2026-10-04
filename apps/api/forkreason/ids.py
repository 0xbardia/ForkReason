"""Deterministic identifiers and canonical hashing.

Two properties matter here and are load-bearing for the whole product:

1. Analysis is reproducible. The same pinned commits and the same code produce
   the same evidence IDs and the same manifest hash (spec FR-B-011, FR-D-004).
2. Evidence IDs are content-addressed. An evidence item's ID is derived from
   its content, so the same finding across two runs is the same ID, and a
   changed finding gets a new ID rather than silently mutating in place.

Python's `json.dumps` is not canonical JSON for hashing purposes across
implementations (float repr, key ordering, unicode escaping), so we implement
canonicalization explicitly here.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
from typing import Any

_ID_SALT = "forkreason/v1"


def _coerce(value: Any) -> Any:
    """Normalize a value into a form that serializes identically every time."""
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        # Quantize to 6 decimals so 0.1+0.2 and 0.3 hash identically.
        rounded = round(value, 6)
        # Collapse -0.0 to 0.0, which otherwise serializes differently.
        return 0.0 if rounded == 0 else rounded
    if isinstance(value, dt.datetime):
        return value.astimezone(dt.timezone.utc).isoformat().replace("+00:00", "Z")
    if isinstance(value, dt.date):
        return value.isoformat()
    if isinstance(value, (set, frozenset)):
        return sorted(_coerce(v) for v in value)
    if isinstance(value, (list, tuple)):
        return [_coerce(v) for v in value]
    if isinstance(value, dict):
        return {str(k): _coerce(v) for k, v in sorted(value.items(), key=lambda kv: str(kv[0]))}
    if hasattr(value, "to_dict"):
        return _coerce(value.to_dict())
    if hasattr(value, "__dataclass_fields__"):
        import dataclasses

        return _coerce(dataclasses.asdict(value))
    return str(value)


def canonical_json(value: Any) -> str:
    """Serialize to canonical JSON: sorted keys, no insignificant whitespace.

    Canonicalization is what makes the manifest hash meaningful, so it must be
    total: the same logical content always serializes identically, regardless of
    the order in which collections were assembled. List order therefore has to
    be normalized too — for manifest-bearing payloads, lists are *sets of
    findings* whose order is an artifact of analysis, not meaning.
    """
    return json.dumps(
        _coerce_canonical(value),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    )


# Keys whose values are ordered sets of findings rather than meaningful
# sequences. Sorting these makes the hash independent of collection order.
_CANONICAL_SORTED_LISTS = frozenset(
    {
        "evidence",
        "conflicting_evidence",
        "alternative_explanations",
        "common_upstream_candidates",
        "evidence_classes",
        "evidence_refs",
        "reasons",
        "layers",
        "candidates",
    }
)


def _coerce_canonical(value: Any) -> Any:
    """Like `_coerce`, but sorts the collections whose order carries no meaning."""
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        rounded = round(value, 6)
        return 0.0 if rounded == 0 else rounded
    if isinstance(value, dt.datetime):
        return value.astimezone(dt.timezone.utc).isoformat().replace("+00:00", "Z")
    if isinstance(value, dt.date):
        return value.isoformat()
    if isinstance(value, (set, frozenset)):
        return sorted(_coerce_canonical(v) for v in value)
    if isinstance(value, (list, tuple)):
        items = [_coerce_canonical(v) for v in value]
        return _sort_by_key(items)
    if isinstance(value, dict):
        out = {}
        for key, item in sorted(value.items(), key=lambda kv: str(kv[0])):
            canonical = _coerce_canonical(item)
            if key in _CANONICAL_SORTED_LISTS and isinstance(canonical, list):
                canonical = _sort_by_key(canonical)
            out[str(key)] = canonical
        return out
    if hasattr(value, "to_dict"):
        return _coerce_canonical(value.to_dict())
    if hasattr(value, "__dataclass_fields__"):
        import dataclasses

        return _coerce_canonical(dataclasses.asdict(value))
    return str(value)


def _sort_by_key(items: list[Any]) -> list[Any]:
    """Deterministic order for a collection of findings.

    Sorted by canonical JSON so any mix of dicts and scalars is orderable and
    stable across runs and Python versions.
    """
    return sorted(items, key=lambda x: json.dumps(x, sort_keys=True, ensure_ascii=True))


def content_hash(value: Any) -> str:
    """SHA-256 over canonical JSON, domain-separated."""
    payload = f"{_ID_SALT}\n{canonical_json(value)}".encode()
    return hashlib.sha256(payload).hexdigest()


def short_hash(value: Any, length: int = 16) -> str:
    return content_hash(value)[:length]


def evidence_id(
    *,
    dna_layer: str,
    evidence_type: str,
    origin_ref: dict[str, Any],
    target_ref: dict[str, Any],
    excerpt: str | None = None,
) -> str:
    """Content-addressed evidence identifier.

    Deliberately excludes `rationale` and `score`: an item's identity is what it
    points at, not how we described or weighted it. Re-scoring therefore keeps
    the same ID, while a different source gets a different one.
    """
    return short_hash(
        {
            "kind": "evidence",
            "dna_layer": dna_layer,
            "evidence_type": evidence_type,
            "origin": _provenance_key(origin_ref),
            "target": _provenance_key(target_ref),
            "excerpt": excerpt or "",
        },
        length=24,
    )


def _provenance_key(ref: dict[str, Any]) -> dict[str, Any]:
    return {
        "repo": ref.get("repo"),
        "commit": ref.get("commit"),
        "path": ref.get("path"),
    }


def case_id_for(origin_full_name: str, origin_commit: str, target_full_name: str, target_commit: str) -> str:
    """Stable case identity: same pinned pair always yields the same case."""
    return short_hash(
        {
            "kind": "case",
            "origin": {"repo": origin_full_name, "commit": origin_commit},
            "target": {"repo": target_full_name, "commit": target_commit},
        },
        length=32,
    )


def idempotency_key_for(origin_full_name: str, origin_commit: str, target_full_name: str, target_commit: str) -> str:
    return content_hash(
        {
            "kind": "job",
            "origin": f"{origin_full_name}@{origin_commit}",
            "target": f"{target_full_name}@{target_commit}",
        }
    )


def snapshot_id_for(full_name: str, commit_sha: str) -> str:
    return short_hash({"kind": "snapshot", "repo": full_name, "commit": commit_sha}, length=32)


def bounded_excerpt(text: str | None, limit: int) -> str | None:
    """Clip an excerpt to a bound, marking that clipping happened."""
    if text is None:
        return None
    if len(text) <= limit:
        return text
    return text[:limit] + " …[truncated]"
