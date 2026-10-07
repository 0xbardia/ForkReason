"""Chain-related endpoints.

ForkReason's chain boundary lives here: this module reads chain state and
prepares payloads. It never signs a user transaction, and there is no
`PRIVATE_KEY` anywhere in the backend (spec FR-K-004).
"""

from __future__ import annotations

import datetime as dt
import logging
from typing import Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..db import get_db
from ..errors import bad_request, conflict, not_found
from ..models import Case, CaseRevision, ChainTransaction, Challenge
from ..schemas import SubmitCasePayload
from ..chain_payloads import build_submit_case_args

log = logging.getLogger(__name__)

MAX_UNVERIFIED_PER_CASE = 8

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
            "note": "Source hash and deployed address were verified against the release transaction.",
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
    if payload.revision_number != 0:
        raise bad_request("invalid_registration_revision", "Initial registration must use provisional analysis revision 0.")

    if case.current_revision != 0:
        raise conflict("case_already_registered", "This analyzed case already has an accepted chain revision.")
    pending = session.scalar(
        select(ChainTransaction.id).where(
            ChainTransaction.case_id == case.id,
            ChainTransaction.kind == "registration",
            ChainTransaction.status.in_(("consensus_pending", "accepted")),
        ).limit(1)
    )
    if pending:
        raise conflict("registration_pending", "A registration transaction is already being followed.")

    revision = session.scalar(
        select(CaseRevision).where(
            CaseRevision.case_id == case.id,
            CaseRevision.revision_number == 0,
        )
    )
    if revision is None:
        raise not_found("revision_not_found", "That revision does not exist.")

    digest = _digest_for(case, revision)
    try:
        args = build_submit_case_args(case, revision, digest)
    except ValueError as exc:
        raise bad_request("invalid_registration_data", str(exc)) from exc

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
            "args": list(args),
            "requires_wallet_signature": True,
        },
        "next_step": (
            "Review and sign with your connected wallet. The transaction hash "
            "is indexed immediately and the accepted revision is reconciled from GenLayer."
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
    return bounded_excerpt("\n".join(lines), min(6000, get_settings().max_manifest_digest_chars)) or ""


class ChainWriteSubmitted(BaseModel):
    case_id: str = Field(min_length=8, max_length=64, pattern=r"^[0-9a-f]+$")
    tx_hash: str = Field(pattern=r"^0x[0-9a-fA-F]{64}$")
    kind: Literal["registration", "challenge"]
    challenge_id: str | None = Field(default=None, max_length=128)


@router.post("/chain/transactions", status_code=202)
async def record_chain_write(payload: ChainWriteSubmitted, session: Session = Depends(get_db)) -> dict:
    """Persist the wallet-produced transaction id before consensus polling."""
    from ..jobs.profile_store import ProfileStore

    settings = get_settings()
    case = session.get(Case, payload.case_id)
    if case is None:
        raise not_found("case_not_found", "That case does not exist.")
    tx_hash = payload.tx_hash.lower()
    existing = session.get(ChainTransaction, tx_hash)
    if existing is not None:
        if existing.case_id != case.id or existing.kind != payload.kind:
            raise conflict("transaction_already_indexed", "That transaction belongs to a different write.")
        return {"tx_hash": tx_hash, "status": existing.status}

    # Unverified ids are cheap to claim and costly to check, so bound them.
    unverified = session.scalar(
        select(func.count()).select_from(ChainTransaction).where(
            ChainTransaction.case_id == case.id,
            ChainTransaction.status.in_(("submitted", "consensus_pending")),
        )
    )
    if (unverified or 0) >= MAX_UNVERIFIED_PER_CASE:
        raise conflict("too_many_pending_transactions", "This case already has several transactions awaiting verification.")

    summary: dict[str, str] = {"recorded_at": dt.datetime.now(dt.timezone.utc).isoformat()}
    if payload.kind == "registration":
        if payload.challenge_id is not None:
            raise bad_request("invalid_registration", "Initial registration cannot include a challenge id.")
        if case.current_revision != 0:
            raise conflict("case_already_registered", "This case already has an accepted chain revision.")
        pending = session.scalar(
            select(ChainTransaction.id).where(
                ChainTransaction.case_id == case.id,
                ChainTransaction.kind == "registration",
                ChainTransaction.status.in_(("consensus_pending", "accepted")),
            ).limit(1)
        )
        if pending:
            raise conflict("registration_pending", "Another registration transaction is already being followed.")
    else:
        if not payload.challenge_id:
            raise bad_request("challenge_required", "A challenge id is required.")
        challenge = session.get(Challenge, payload.challenge_id)
        if challenge is None or challenge.case_id != case.id:
            raise not_found("challenge_not_found", "That challenge does not exist.")
        if challenge.status not in {"prepared", "failed"}:
            if challenge.tx_hash == tx_hash:
                return {"tx_hash": tx_hash, "status": challenge.status}
            raise conflict("challenge_already_submitted", "This challenge already has a transaction.")
        if challenge.base_revision != case.current_revision:
            raise conflict("stale_challenge", "The Case changed after this challenge was prepared.")
        challenge.tx_hash = tx_hash
        challenge.status = "submitted"
        summary["challenge_id"] = challenge.id

    ProfileStore(settings.snapshot_dir).record_chain_transaction(
        session, tx_hash=tx_hash, case_id=case.id, kind=payload.kind,
        network=settings.genlayer_network, status="submitted", payload_summary=summary,
    )
    session.commit()
    return {"tx_hash": tx_hash, "status": "submitted"}


def _contract_source_sha256() -> str | None:
    """Hash of the exact contract source, so a deployed address is traceable."""
    import hashlib
    from pathlib import Path

    path = Path(__file__).resolve().parents[4] / "contracts" / "forkreason_registry.py"
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return None
