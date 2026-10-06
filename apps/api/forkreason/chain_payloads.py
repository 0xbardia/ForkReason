"""Canonical ABI payloads for ForkReasonRegistry writes."""

from __future__ import annotations

import re
from typing import NamedTuple

from .ids import case_id_for, content_hash
from .models import Case, CaseRevision


class SubmitCaseArgs(NamedTuple):
    origin_repo: str
    origin_commit: str
    target_repo: str
    target_commit: str
    manifest_hash: str
    evidence_digest: str


def build_submit_case_args(
    case: Case, revision: CaseRevision, evidence_digest: str
) -> SubmitCaseArgs:
    """Map one provisional analyzed case to the six-string contract ABI."""
    if revision.case_id != case.id or revision.revision_number != 0:
        raise ValueError("initial registration requires this case's provisional revision 0")
    if revision.manifest_hash != case.manifest_hash or content_hash(revision.manifest) != revision.manifest_hash:
        raise ValueError("case manifest identity does not match the analyzed record")
    manifest = revision.manifest
    origin = manifest.get("origin") if isinstance(manifest, dict) else None
    target = manifest.get("target") if isinstance(manifest, dict) else None
    if not isinstance(origin, dict) or not isinstance(target, dict):
        raise ValueError("canonical manifest is missing pinned repositories")

    args = SubmitCaseArgs(
        case.origin_full_name,
        case.origin_commit,
        case.target_full_name,
        case.target_commit,
        revision.manifest_hash,
        evidence_digest,
    )
    if (origin.get("full_name"), origin.get("commit"), target.get("full_name"), target.get("commit")) != (
        args.origin_repo, args.origin_commit, args.target_repo, args.target_commit
    ):
        raise ValueError("pinned repositories do not match the analyzed case")
    if case_id_for(args.origin_repo, args.origin_commit, args.target_repo, args.target_commit) != case.id:
        raise ValueError("case identifier does not match the pinned repository commits")
    if not args.origin_repo or len(args.origin_repo) > 240:
        raise ValueError("origin_repo must be 1 to 240 characters")
    if not args.target_repo or len(args.target_repo) > 240:
        raise ValueError("target_repo must be 1 to 240 characters")
    for name, value in (("origin_commit", args.origin_commit), ("target_commit", args.target_commit)):
        if not value or len(value) > 64 or not re.fullmatch(r"[0-9a-fA-F]+", value):
            raise ValueError(f"{name} must be non-empty hexadecimal up to 64 characters")
    if not re.fullmatch(r"[0-9a-fA-F]{1,128}", args.manifest_hash):
        raise ValueError("manifest_hash must be non-empty hexadecimal up to 128 characters")
    if not evidence_digest or len(evidence_digest) > 6000:
        raise ValueError("evidence_digest must be 1 to 6000 characters")
    if args.origin_repo == args.target_repo and args.origin_commit == args.target_commit:
        raise ValueError("origin and target must differ")
    return args
