"""Search and chain-index endpoints."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from ..db import get_db
from ..errors import not_found
from ..models import Case, CaseRevision, ChainTransaction

log = logging.getLogger(__name__)

router = APIRouter(tags=["search"])

MAX_QUERY_LENGTH = 120
MAX_PAGE_SIZE = 50


@router.get("/search")
async def search(
    q: str = Query(default="", max_length=MAX_QUERY_LENGTH),
    verdict: str | None = Query(default=None, max_length=32),
    limit: int = Query(default=20, ge=1, le=MAX_PAGE_SIZE),
    offset: int = Query(default=0, ge=0),
    session: Session = Depends(get_db),
) -> dict:
    """Search public cases by repository name, verdict, or case id.

    Bounded and parameterised throughout: no string interpolation into SQL, and
    the query term is length-capped so it cannot be used as a denial-of-service
    lever (spec FR-M-001 SQL injection).
    """
    term = q.strip()
    stmt = select(Case)
    count_stmt = select(func.count()).select_from(Case)

    if term:
        like = f"%{term}%"
        condition = or_(
            Case.origin_full_name.ilike(like),
            Case.target_full_name.ilike(like),
            Case.id.ilike(like),
        )
        if verdict:
            condition = condition & (Case.current_revision == CaseRevision.revision_number)
        stmt = stmt.where(condition)
        count_stmt = count_stmt.where(condition)

    total = session.scalar(count_stmt) or 0

    rows = session.scalars(
        stmt.order_by(Case.created_at.desc()).limit(limit).offset(offset)
    ).all()

    items = []
    for case in rows:
        revision = session.scalar(
            select(CaseRevision).where(
                CaseRevision.case_id == case.id,
                CaseRevision.revision_number == case.current_revision,
            )
        )
        if verdict and (revision is None or revision.verdict != verdict.upper()):
            continue
        items.append(
            {
                "id": case.id,
                "origin_repo": case.origin_full_name,
                "target_repo": case.target_full_name,
                "verdict": revision.verdict if revision else None,
                "confidence": revision.confidence if revision else None,
                "direction": revision.direction if revision else None,
                "revision": case.current_revision,
                "lifecycle": case.lifecycle,
                "created_at": case.created_at.isoformat() if case.created_at else None,
            }
        )

    return {
        "query": term,
        "verdict_filter": verdict.upper() if verdict else None,
        "total": int(total),
        "limit": limit,
        "offset": offset,
        "has_more": offset + limit < int(total),
        "items": items,
    }


# Chain read endpoints live with search because both are read-only views over
# indexed state; the write-preparation endpoints are in routes/chain.py.
chain_read_router = APIRouter(tags=["chain"])


@chain_read_router.get("/chain/status")
async def chain_status(session: Session = Depends(get_db)) -> dict:
    """Indexed chain activity. The database mirrors chain state; it is not the
    authority (constitution V.21)."""
    from ..config import get_settings

    settings = get_settings()
    total = session.scalar(select(func.count()).select_from(ChainTransaction)) or 0
    recent = session.scalars(
        select(ChainTransaction).order_by(ChainTransaction.observed_at.desc()).limit(10)
    ).all()
    return {
        "network": settings.genlayer_network,
        "rpc_url": settings.genlayer_rpc_url,
        "contract_address": settings.genlayer_contract_address,
        "deployed": bool(settings.genlayer_contract_address),
        "indexed_transactions": int(total),
        "recent": [
            {
                "tx_hash": tx.id,
                "case_id": tx.case_id,
                "kind": tx.kind,
                "status": tx.status,
                "observed_at": tx.observed_at.isoformat() if tx.observed_at else None,
            }
            for tx in recent
        ],
    }


@chain_read_router.get("/chain/transactions/{tx_hash}")
async def get_transaction(tx_hash: str, session: Session = Depends(get_db)) -> dict:
    row = session.get(ChainTransaction, tx_hash[:80])
    if row is None:
        raise not_found("transaction_not_found", "That transaction is not indexed.")
    return {
        "tx_hash": row.id,
        "case_id": row.case_id,
        "kind": row.kind,
        "network": row.network,
        "status": row.status,
        "observed_at": row.observed_at.isoformat() if row.observed_at else None,
        "note": (
            "This is an index entry for a chain transaction. Verify finality "
            "against the GenLayer network, which is authoritative."
        ),
    }