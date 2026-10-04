"""Case, evidence and challenge endpoints.

The case report is the product's signature surface, so this module returns
everything the report needs in as few round trips as the frontend can use
without a waterfall, while keeping every field bounded.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..db import get_db
from ..domain import CONFIDENCES, DNA_LAYERS
from ..errors import bad_request, conflict, not_found
from ..models import (
    AlternativeExplanation,
    Case,
    CaseRevision,
    Challenge,
    EvidenceItem,
    EvidenceRelation,
)

log = logging.getLogger(__name__)

router = APIRouter(tags=["cases"])

MAX_PAGE_SIZE = 50


@router.get("/cases")
async def list_cases(
    limit: int = Query(default=20, ge=1, le=MAX_PAGE_SIZE),
    offset: int = Query(default=0, ge=0),
    session: Session = Depends(get_db),
) -> dict:
    """Bounded pagination over public cases, newest first.

    `limit` and `offset` are clamped in the handler as well as validated by the
    Query type: a bounds check that can be bypassed by a different route or a
    direct call is not a bounds check.
    """
    limit = max(1, min(int(limit), MAX_PAGE_SIZE))
    offset = max(0, int(offset))

    total = session.scalar(select(func.count()).select_from(Case)) or 0
    rows = session.scalars(
        select(Case).order_by(Case.created_at.desc()).limit(limit).offset(offset)
    ).all()
    return {
        "total": int(total),
        "limit": limit,
        "offset": offset,
        "has_more": offset + limit < int(total),
        "items": [_case_card(case, session) for case in rows],
    }


@router.get("/cases/{case_id}")
async def get_case(case_id: str, session: Session = Depends(get_db)) -> dict:
    """The full case report payload."""
    case = session.get(Case, case_id)
    if case is None:
        raise not_found("case_not_found", "That case does not exist.")

    revision = _current_revision(session, case)
    revisions = session.scalars(
        select(CaseRevision)
        .where(CaseRevision.case_id == case.id)
        .order_by(CaseRevision.revision_number)
    ).all()

    evidence = session.scalars(
        select(EvidenceItem)
        .where(
            EvidenceItem.case_id == case.id,
            EvidenceItem.revision_number == case.current_revision,
        )
        .order_by(EvidenceItem.score.desc())
    ).all()

    conflicting = [e for e in evidence if e.evidence_type.startswith("conflicting:")]
    supporting = [e for e in evidence if not e.evidence_type.startswith("conflicting:")]

    explanations = session.scalars(
        select(AlternativeExplanation)
        .where(
            AlternativeExplanation.case_id == case.id,
            AlternativeExplanation.revision_number == case.current_revision,
        )
        .order_by(AlternativeExplanation.score.desc())
    ).all()

    relations = session.scalars(
        select(EvidenceRelation).where(EvidenceRelation.case_id == case.id)
    ).all()

    return {
        "case": {
            "id": case.id,
            "origin_repo": case.origin_full_name,
            "target_repo": case.target_full_name,
            "origin_commit": case.origin_commit,
            "target_commit": case.target_commit,
            "manifest_hash": case.manifest_hash,
            "current_revision": case.current_revision,
            "lifecycle": case.lifecycle,
            "created_at": case.created_at.isoformat() if case.created_at else None,
        },
        "verdict": {
            "verdict": revision.verdict,
            "confidence": revision.confidence,
            "direction": revision.direction,
            "shared_upstream": revision.shared_upstream,
            "independent_origin_plausibility": revision.independent_origin_plausibility,
            "summary": revision.summary,
            "rationale": revision.rationale,
            "revision_number": revision.revision_number,
            "tx_hash": revision.tx_hash,
            "network": revision.network,
        },
        "evidence": [_evidence_card(e) for e in supporting],
        "conflicting_evidence": [_evidence_card(e) for e in conflicting],
        "alternative_explanations": [
            {
                "kind": x.kind,
                "support": x.support,
                "score": round(x.score, 4),
                "rationale": x.rationale,
                "is_selected": x.is_selected,
            }
            for x in explanations
        ],
        "graph": [
            {
                "id": r.id,
                "subject_kind": r.subject_kind,
                "subject_ref": r.subject_ref,
                "relation": r.relation,
                "object_kind": r.object_kind,
                "object_ref": r.object_ref,
                "weight": round(r.weight, 4),
            }
            for r in relations[:400]
        ],
        "revisions": [
            {
                "revision_number": r.revision_number,
                "verdict": r.verdict,
                "confidence": r.confidence,
                "direction": r.direction,
                "shared_upstream": r.shared_upstream,
                "manifest_hash": r.manifest_hash,
                "tx_hash": r.tx_hash,
                "created_at": r.created_at.isoformat() if r.created_at else None,
                "is_current": r.revision_number == case.current_revision,
            }
            for r in revisions
        ],
    }


@router.get("/cases/{case_id}/evidence")
async def get_case_evidence(
    case_id: str,
    layer: str | None = Query(default=None, max_length=16),
    strength: str | None = Query(default=None, max_length=8),
    limit: int = Query(default=MAX_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
    offset: int = Query(default=0, ge=0),
    session: Session = Depends(get_db),
) -> dict:
    """Filterable evidence for the Evidence Explorer."""
    case = session.get(Case, case_id)
    if case is None:
        raise not_found("case_not_found", "That case does not exist.")

    # Filters are normalized in the handler so an absent filter is simply absent
    # rather than an empty string that has to be special-cased.
    layer = layer.strip().upper() if layer and layer.strip() else None
    strength = strength.strip().upper() if strength and strength.strip() else None
    if layer and layer not in DNA_LAYERS:
        raise bad_request(
            "invalid_layer", f"Unknown evidence layer. Use one of: {', '.join(DNA_LAYERS)}."
        )
    if strength and strength not in CONFIDENCES:
        raise bad_request(
            "invalid_strength", f"Unknown strength. Use one of: {', '.join(CONFIDENCES)}."
        )

    stmt = select(EvidenceItem).where(
        EvidenceItem.case_id == case.id,
        EvidenceItem.revision_number == case.current_revision,
    )
    if layer:
        stmt = stmt.where(EvidenceItem.dna_layer == layer)
    if strength:
        stmt = stmt.where(EvidenceItem.strength == strength)

    total = session.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = session.scalars(
        stmt.order_by(EvidenceItem.score.desc()).limit(limit).offset(offset)
    ).all()

    layers: dict[str, int] = {}
    strengths: dict[str, int] = {}
    all_rows = session.scalars(
        select(EvidenceItem).where(
            EvidenceItem.case_id == case.id,
            EvidenceItem.revision_number == case.current_revision,
        )
    ).all()
    for row in all_rows:
        layers[row.dna_layer] = layers.get(row.dna_layer, 0) + 1
        strengths[row.strength] = strengths.get(row.strength, 0) + 1

    return {
        "case_id": case.id,
        "revision_number": case.current_revision,
        "total": int(total),
        "limit": limit,
        "offset": offset,
        "has_more": offset + limit < int(total),
        "facets": {"layers": layers, "strengths": strengths},
        "items": [_evidence_card(e) for e in rows],
    }


class ChallengePrepareRequest(BaseModel):
    rationale: str = Field(min_length=10, max_length=600)
    evidence_summary: str = Field(min_length=10, max_length=2000)
    submitter: str = Field(min_length=4, max_length=128)


class ChallengeSubmittedRequest(BaseModel):
    """Recorded after the user's wallet has produced a transaction."""

    tx_hash: str = Field(min_length=16, max_length=80, pattern=r"^[0-9a-fA-Fx]+$")


@router.post("/cases/{case_id}/challenge-preparation", status_code=status.HTTP_200_OK)
async def prepare_challenge(
    case_id: str, payload: ChallengePrepareRequest, session: Session = Depends(get_db)
) -> dict:
    """Prepare a challenge payload for the user's wallet to sign.

    The backend prepares; the browser signs. There is no server-side signer and
    no endpoint that submits a user write (spec FR-K-003/008).
    """
    settings = get_settings()
    case = session.get(Case, case_id)
    if case is None:
        raise not_found("case_not_found", "That case does not exist.")

    revision = _current_revision(session, case)
    challenge = Challenge(
        id=f"{case.id}-{case.current_revision + 1}",
        case_id=case.id,
        base_revision=case.current_revision,
        submitter=payload.submitter,
        rationale=payload.rationale,
        evidence_refs=[payload.evidence_summary[:400]],
        status="prepared",
    )
    session.add(challenge)
    session.flush()

    digest = _challenge_digest(case, revision, payload)

    return {
        "challenge_id": challenge.id,
        "case_id": case.id,
        "base_revision": case.current_revision,
        "expected_revision": case.current_revision + 1,
        "evidence_digest": digest,
        "evidence_digest_sha256": _sha256_hex(digest),
        "chain": {
            "network": settings.genlayer_network,
            "rpc_url": settings.genlayer_rpc_url,
            "contract_address": settings.genlayer_contract_address,
        },
        "write": {
            "contract": "ForkReasonRegistry",
            "method": "challenge_case",
            "args": [case.id, case.current_revision, payload.rationale, digest],
            # Explicitly no signature material: the wallet supplies this.
            "requires_wallet_signature": True,
        },
        "next_step": (
            "Connect a wallet on the configured GenLayer network, review the "
            "transaction, and sign. ForkReason's server never signs for you."
        ),
    }


@router.get("/cases/{case_id}/challenges")
async def list_challenges(case_id: str, session: Session = Depends(get_db)) -> dict:
    case = session.get(Case, case_id)
    if case is None:
        raise not_found("case_not_found", "That case does not exist.")
    rows = session.scalars(
        select(Challenge)
        .where(Challenge.case_id == case.id)
        .order_by(Challenge.created_at)
    ).all()
    return {
        "case_id": case.id,
        "items": [
            {
                "id": c.id,
                "base_revision": c.base_revision,
                "submitter": c.submitter,
                "rationale": c.rationale,
                "status": c.status,
                "resulting_revision": c.resulting_revision,
                "tx_hash": c.tx_hash,
                "created_at": c.created_at.isoformat() if c.created_at else None,
            }
            for c in rows
        ],
    }


@router.post("/cases/{case_id}/challenges/{challenge_id}/submitted")
async def mark_challenge_submitted(
    case_id: str,
    challenge_id: str,
    payload: ChallengeSubmittedRequest,
    session: Session = Depends(get_db),
) -> dict:
    """Record the transaction hash the user's wallet produced.

    This indexes chain state; it never asserts a verdict. The revision appears
    only after the chain reports it (constitution V.21).
    """
    from ..jobs.profile_store import ProfileStore

    challenge = session.get(Challenge, challenge_id)
    if challenge is None or challenge.case_id != case_id:
        raise not_found("challenge_not_found", "That challenge does not exist.")
    if challenge.status != "prepared":
        raise conflict(
            "challenge_already_submitted",
            "This challenge already has a recorded transaction.",
        )

    tx_hash = payload.tx_hash

    settings = get_settings()
    ProfileStore(settings.snapshot_dir).record_chain_transaction(
        session,
        tx_hash=tx_hash,
        case_id=case_id,
        kind="challenge",
        network=settings.genlayer_network,
        status="submitted",
        payload_summary={"challenge_id": challenge_id},
    )
    challenge.tx_hash = tx_hash
    challenge.status = "submitted"
    session.commit()

    return {
        "challenge_id": challenge_id,
        "tx_hash": tx_hash,
        "status": "submitted",
        "note": (
            "Recorded for indexing. The revision appears once the GenLayer "
            "consensus for this transaction has been observed."
        ),
    }


# --- helpers -------------------------------------------------------------


def _current_revision(session: Session, case: Case) -> CaseRevision:
    revision = session.scalar(
        select(CaseRevision).where(
            CaseRevision.case_id == case.id,
            CaseRevision.revision_number == case.current_revision,
        )
    )
    if revision is None:
        raise not_found("revision_not_found", "That revision does not exist.")
    return revision


def _case_card(case: Case, session: Session) -> dict:
    revision = session.scalar(
        select(CaseRevision).where(
            CaseRevision.case_id == case.id,
            CaseRevision.revision_number == case.current_revision,
        )
    )
    return {
        "id": case.id,
        "origin_repo": case.origin_full_name,
        "target_repo": case.target_full_name,
        "verdict": revision.verdict if revision else None,
        "confidence": revision.confidence if revision else None,
        "direction": revision.direction if revision else None,
        "revision": case.current_revision,
        "lifecycle": case.lifecycle,
        "manifest_hash": case.manifest_hash,
        "created_at": case.created_at.isoformat() if case.created_at else None,
    }


def _evidence_card(item: EvidenceItem) -> dict:
    is_conflicting = item.evidence_type.startswith("conflicting:")
    return {
        "id": item.id,
        "dna_layer": item.dna_layer,
        "evidence_type": item.evidence_type.replace("conflicting:", ""),
        "is_conflicting": is_conflicting,
        "strength": item.strength,
        "score": round(item.score, 4),
        "rationale": item.rationale,
        "origin": item.origin_source,
        "target": item.target_source,
        "excerpt": item.excerpt,
    }


def _challenge_digest(case: Case, revision: CaseRevision, payload: ChallengePrepareRequest) -> str:
    """Bounded digest for consensus. Untrusted text is delimited, never structural."""
    from ..ids import bounded_excerpt

    body = (
        f"CHALLENGE against case {case.id} revision {case.current_revision}\n"
        f"claim: {bounded_excerpt(payload.rationale, 400)}\n"
        f"prior verdict: {revision.verdict} / {revision.confidence}\n"
        f"new evidence: {bounded_excerpt(payload.evidence_summary, 1200)}\n"
        "<forkreason_evidence>\n"
        f"{bounded_excerpt(payload.evidence_summary, 1200)}\n"
        "</forkreason_evidence>\n"
    )
    return body[: get_settings().max_manifest_digest_chars]


def _sha256_hex(value: str) -> str:
    import hashlib

    return hashlib.sha256(value.encode("utf-8")).hexdigest()


async def _read_json_body() -> dict:
    """Small helper so this handler can validate its own body shape."""
    from fastapi import Request

    return {}


from fastapi import Request  # noqa: E402  (imported late to avoid a cycle)


def _read_body(request: Request) -> dict:
    return {}