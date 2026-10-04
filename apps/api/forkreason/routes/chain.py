"""Chain-related endpoints.

ForkReason's chain boundary lives here: this module reads chain state and
prepares payloads. It never signs a user transaction, and there is no
`PRIVATE_KEY` anywhere in the backend (spec FR-K-004).
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..db import get_db
from ..errors import bad_request, not_found
from ..models import Case, CaseRevision
from ..schemas import SubmitCasePayload

log = logging.getLogger(__name__)

router = APIRouter(tags=["chain"])


@router.get("/chain/contract")
async def contract_info() -> dict:
    """Where the registry lives, and what it is for.

    Reports honestly when the contract is not yet deployed, rather than
    presenting an unconfigured deployment as live.
    """
    settings = get_settings()
    address = settings.genlayer_contract_address
    return {
        "name": "ForkReasonRegistry",
        "network": settings.genlayer_network,
        "rpc_url": settings.genlayer_rpc_url,
        "address": address,
        "deployed": bool(address),
        "source_sha256": _contract_source_sha256(),
        "read_methods": [
            "get_case",
            "get_case_count",
            "get_latest_revision",
            "get_revision",
            "get_revision_count",
            "get_challenge",
            "get_challenge_count",
            "get_cases_page",
            "get_dna_layers",
            "get_valid_verdicts",
            "get_valid_confidences",
        ],
        "write_methods": ["submit_case", "challenge_case"],
        "note": (
            "Every state-changing action is signed by the user's own browser "
            "wallet. The ForkReason server holds no key that can act for a user."
        ),
        # A deployment that happened, with the evidence for it. Kept separate
        # from `deployed`, which means "this server can target a contract".
        "release_deployment": {
            "network": "GenLayer Studio (studionet)",
            "file": "forkreason_registry_upload.py",
            "address_display": "0xb3...d07b",
            "tx": (
                "0x4c5c6d72bcae900d4b3a08dcb0131d292b9bf77d72d4a91375bac95381c6518b"
            ),
            "consensus": "Reached consensus",
            "state": "FINALIZED",
            "verified_read": "get_case_count returned 0 (Accepted)",
            "note": (
                "Deployed and read on Studio. The address above is shown "
                "truncated as Studio displays it; the full address is not "
                "wired into this deployment, so writes remain refused here "
                "rather than being sent to an address this server cannot "
                "verify."
            ),
        },
    }


@router.post("/chain/submit-preparation")
async def prepare_submission(payload: SubmitCasePayload, session: Session = Depends(get_db)) -> dict:
    """Prepare the arguments for registering a resolved case on chain.

    The backend resolves nothing here: it looks up the already-committed
    revision and hands the wallet exactly what needs signing.
    """
    settings = get_settings()
    if not settings.genlayer_contract_address:
        raise bad_request(
            "contract_not_configured",
            "ForkReason's GenLayer contract is not configured on this deployment.",
        )

    case = session.get(Case, payload.case_id)
    if case is None:
        raise not_found("case_not_found", "That case does not exist.")

    revision = session.scalar(
        select(CaseRevision).where(
            CaseRevision.case_id == case.id,
            CaseRevision.revision_number == payload.revision_number,
        )
    )
    if revision is None:
        raise not_found("revision_not_found", "That revision does not exist.")

    digest = _digest_for(case, revision)

    return {
        "case_id": case.id,
        "revision_number": revision.revision_number,
        "verdict": revision.verdict,
        "confidence": revision.confidence,
        "manifest_hash": revision.manifest_hash,
        "evidence_digest": digest,
        "chain": {
            "network": settings.genlayer_network,
            "rpc_url": settings.genlayer_rpc_url,
            "contract_address": settings.genlayer_contract_address,
        },
        "write": {
            "contract": "ForkReasonRegistry",
            "method": "submit_case",
            "args": [
                case.origin_full_name,
                revision.manifest_hash,
                digest,
            ],
            "requires_wallet_signature": True,
        },
        "next_step": (
            "Review the transaction in your wallet and sign. ForkReason will "
            "index the resulting transaction hash."
        ),
    }


def _digest_for(case: Case, revision: CaseRevision) -> str:
    from ..ids import bounded_excerpt

    summary = revision.summary or {}
    lines = [
        f"case: {case.id}",
        f"revision: {revision.revision_number}",
        f"origin: {case.origin_full_name} @ {case.origin_commit[:12]}",
        f"target: {case.target_full_name} @ {case.target_commit[:12]}",
        f"deterministic verdict: {revision.verdict} / {revision.confidence}",
        f"direction: {revision.direction}",
        f"shared_upstream: {revision.shared_upstream or 'none'}",
        f"evidence classes: {', '.join(summary.get('layers', []))}",
        f"evidence count: {summary.get('evidence_count', 0)}",
        f"conflicting count: {summary.get('conflicting_count', 0)}",
    ]
    return bounded_excerpt("\n".join(lines), get_settings().max_manifest_digest_chars) or ""


def _contract_source_sha256() -> str | None:
    """Hash of the exact contract source, so a deployed address is traceable."""
    import hashlib
    from pathlib import Path

    path = Path(__file__).resolve().parents[3] / "contracts" / "forkreason_registry.py"
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return None