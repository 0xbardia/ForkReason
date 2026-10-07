"""Verify finalized GenLayer writes and atomically project their revisions."""

from __future__ import annotations

import datetime as dt
import json
import logging
import re
import subprocess
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from .chain_payloads import build_submit_case_args
from .config import get_settings
from .domain import CONFIDENCES, DIRECTIONS, DNA_LAYERS, VERDICTS
from .models import (
    AlternativeExplanation, Case, CaseRevision, ChainTransaction, Challenge,
    EvidenceItem, EvidenceRelation,
)

log = logging.getLogger(__name__)
PENDING = {"submitted", "consensus_pending"}
TX_ID = re.compile(r"^0x[0-9a-f]{64}$")


def observe_chain_write(
    tx_id: str, network: str, rpc_url: str, contract: str, chain_case_id: str,
    revision_number: int,
) -> dict[str, Any]:
    """Read the transaction and finalized contract state using genlayer-js."""
    root = Path(__file__).resolve().parents[3]
    script = root / "apps" / "web" / "scripts" / "inspect-chain-write.mjs"
    request = {
        "tx_id": tx_id,
        "network": network,
        "rpc_url": rpc_url,
        "contract": contract,
        "chain_case_id": chain_case_id,
        "revision_number": revision_number,
    }
    result = subprocess.run(
        ["node", str(script)], input=json.dumps(request),
        text=True, capture_output=True, timeout=35, cwd=root, check=False,
    )
    if result.returncode:
        raise RuntimeError(
            "GenLayer transaction observation failed: " + (result.stderr or "").strip()[-160:]
        )
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError("GenLayer reader returned invalid JSON") from exc


def reconcile_transaction(session: Session, row: ChainTransaction) -> str:
    """Poll one persisted transaction. Chain state, never the browser, is authority."""
    settings = get_settings()
    if row.status not in PENDING:
        return row.status
    if (
        row.network != settings.genlayer_network
        or not settings.genlayer_contract_address
        or not re.fullmatch(r"0x[0-9a-f]{40}", settings.genlayer_contract_address, re.IGNORECASE)
    ):
        row.status = "rejected"
        return row.status
    case = session.get(Case, row.case_id) if row.case_id else None
    if case is None:
        row.status = "rejected"
        return row.status
    revisions = {
        revision.revision_number: revision
        for revision in session.scalars(
            select(CaseRevision).where(CaseRevision.case_id == case.id)
        ).all()
    }
    if row.kind == "registration":
        base = revisions.get(0)
        expected_revision = 1
    elif row.kind == "challenge":
        challenge_id = (row.payload_summary or {}).get("challenge_id")
        challenge = session.get(Challenge, challenge_id) if challenge_id else None
        base = revisions.get(challenge.base_revision) if challenge else None
        expected_revision = challenge.base_revision + 1 if challenge else -1
    else:
        row.status = "rejected"
        return row.status
    if base is None:
        row.status = "rejected"
        return row.status
    chain_case_id = revisions.get(1).manifest_hash if 1 in revisions else base.manifest_hash
    if row.kind == "registration":
        chain_case_id = base.manifest_hash
    observation = observe_chain_write(
        row.id, row.network, settings.genlayer_rpc_url,
        settings.genlayer_contract_address or "", chain_case_id, expected_revision,
    )
    failure = observation.get("error") if isinstance(observation, dict) else None
    if isinstance(failure, dict):
        # The RPC could not be asked. That says nothing about the transaction.
        if failure.get("rate_limited"):
            row.observed_at = dt.datetime.now(dt.timezone.utc) + RATE_LIMIT_BACKOFF - POLL_INTERVAL
            return row.status
        raise RuntimeError("GenLayer RPC error: " + str(failure.get("message", ""))[:160])
    status = reconcile_observed_write(
        session, row, observation,
        expected_network=settings.genlayer_network,
        expected_contract=settings.genlayer_contract_address or "",
    )
    errors = observation.get("read_errors") or []
    if status in PENDING and errors:
        log.warning("chain state read failed: %s", errors[0])
        if any("rate limit" in str(error).lower() for error in errors):
            # The RPC meters contract reads per hour; wait instead of spending the budget.
            row.observed_at = dt.datetime.now(dt.timezone.utc) + RATE_LIMIT_BACKOFF - POLL_INTERVAL
    return status


def reconcile_observed_write(
    session: Session,
    row: ChainTransaction,
    observed: dict[str, Any],
    *,
    expected_network: str,
    expected_contract: str,
) -> str:
    """Idempotently append a chain-verified revision and advance the Case pointer."""
    if row.status not in PENDING:
        return row.status
    if (
        not TX_ID.fullmatch(row.id)
        or not re.fullmatch(r"0x[0-9a-f]{40}", expected_contract, re.IGNORECASE)
        or not expected_network
        or row.network != expected_network
        or not isinstance(observed, dict)
    ):
        row.status = "rejected"
        return row.status
    case = session.scalar(select(Case).where(Case.id == row.case_id).with_for_update())
    if case is None:
        row.status = "rejected"
        return row.status
    tx = observed.get("transaction") or {}
    observed_tx_id = tx.get("tx_id") if isinstance(tx, dict) else None
    if not isinstance(observed_tx_id, str) or observed_tx_id.lower() != row.id:
        row.status = "rejected"
        return row.status
    tx_status = str(tx.get("status", "")).upper()
    if tx_status == "NOT_FOUND":
        # A hash the wallet has just returned may not be visible on the RPC yet.
        # Only a hash that is still unknown after the grace window is rejected.
        if _within_grace(row):
            row.status = "submitted"
            return row.status
        row.status = "rejected"
        _set_challenge_status(session, row, "failed")
        return row.status
    if (
        not re.fullmatch(r"0x[0-9a-f]{40}", str(tx.get("from", "")), re.IGNORECASE)
        or str(tx.get("to", "")).lower() != expected_contract.lower()
    ):
        row.status = "rejected"
        return row.status

    revisions = {
        revision.revision_number: revision
        for revision in session.scalars(
            select(CaseRevision).where(CaseRevision.case_id == case.id)
        ).all()
    }
    if row.kind == "registration":
        base = revisions.get(0)
        challenge = None
        expected_revision = 1
        try:
            expected_args = list(build_submit_case_args(case, base, _registration_digest(case, base))) if base else []
        except ValueError:
            expected_args = []
        method = "submit_case"
    elif row.kind == "challenge":
        challenge_id = (row.payload_summary or {}).get("challenge_id")
        challenge = session.get(Challenge, challenge_id) if challenge_id else None
        base = revisions.get(challenge.base_revision) if challenge else None
        expected_revision = challenge.base_revision + 1 if challenge else -1
        expected_args = [
            revisions.get(1).manifest_hash if revisions.get(1) else "",
            challenge.base_revision,
            challenge.rationale,
            challenge.evidence_digest,
        ] if challenge and revisions.get(1) else []
        method = "challenge_case"
    else:
        row.status = "rejected"
        return row.status
    if base is None or (row.kind == "challenge" and challenge is None):
        row.status = "rejected"
        return row.status

    call = tx.get("call") or {}
    if not isinstance(call, dict) or call.get("method") != method or call.get("args") != expected_args:
        row.status = "rejected"
        return row.status

    if tx_status == "UNDETERMINED":
        row.status = "undetermined"
        _set_challenge_status(session, row, "undetermined")
        return row.status
    if tx_status in {"CANCELED", "VALIDATORS_TIMEOUT", "LEADER_TIMEOUT"}:
        row.status = "failed"
        _set_challenge_status(session, row, "failed")
        return row.status
    if tx_status not in {"ACCEPTED", "FINALIZED"}:
        row.status = "consensus_pending"
        return row.status
    if tx.get("execution_success") is not True:
        row.status = "failed"
        _set_challenge_status(session, row, "failed")
        return row.status

    chain_case = observed.get("case") or {}
    chain_revision = observed.get("revision") or {}
    if not isinstance(chain_case, dict) or not chain_case or not isinstance(chain_revision, dict) or not chain_revision:
        row.status = "consensus_pending"
        return row.status
    if (
        chain_case.get("case_id") != (revisions.get(1).manifest_hash if revisions.get(1) else base.manifest_hash)
        or _as_int(chain_case.get("current_revision")) != expected_revision
        or chain_revision.get("case_id") != chain_case.get("case_id")
        or _as_int(chain_revision.get("revision_number")) != expected_revision
        or chain_revision.get("is_current") is not True
    ):
        row.status = "rejected"
        return row.status

    if row.kind == "registration":
        if (
            case.current_revision != 0
            or chain_case.get("lifecycle") != "RESOLVED"
            or not _chain_case_matches(chain_case, case, base)
        ):
            row.status = "rejected"
            return row.status
        if not tx.get("from") or str(chain_case.get("submitter", "")).lower() != str(tx["from"]).lower():
            row.status = "rejected"
            return row.status
        if chain_revision.get("manifest_hash") != base.manifest_hash:
            row.status = "rejected"
            return row.status
    else:
        chain_challenge = observed.get("challenge") or {}
        initial = revisions.get(1)
        if (
            initial is None
            or not _chain_case_matches(chain_case, case, initial)
            or chain_case.get("lifecycle") != "CHALLENGED"
            or case.current_revision != challenge.base_revision
            or chain_challenge.get("case_id") != chain_case.get("case_id")
            or _as_int(chain_challenge.get("base_revision")) != challenge.base_revision
            or chain_challenge.get("rationale") != challenge.rationale
            or chain_challenge.get("status") != "RECORDED"
            or chain_challenge.get("manifest_hash") != chain_revision.get("manifest_hash")
            or chain_revision.get("manifest_hash") == base.manifest_hash
            or not tx.get("from")
            or str(chain_challenge.get("submitter", "")).lower() != str(tx["from"]).lower()
        ):
            row.status = "rejected"
            return row.status

    # A stale observation can never move the Case pointer backwards.
    existing = revisions.get(expected_revision)
    if existing:
        if existing.tx_hash == row.id:
            row.status = "accepted"
            return row.status
        row.status = "rejected"
        return row.status
    if case.current_revision != expected_revision - 1:
        row.status = "rejected"
        return row.status

    try:
        verdict = str(chain_revision["verdict"])
        confidence = str(chain_revision["confidence"])
        direction = str(chain_revision["direction"])
        classes = chain_revision["evidence_classes"]
        manifest_hash = str(chain_revision["manifest_hash"])
        rationale = str(chain_revision["rationale"])
        if verdict not in VERDICTS or confidence not in CONFIDENCES or direction not in DIRECTIONS:
            raise ValueError("unsupported chain verdict fields")
        if not isinstance(classes, list) or any(item not in DNA_LAYERS for item in classes):
            raise ValueError("invalid chain evidence classes")
        if not re.fullmatch(r"[0-9a-fA-F]{1,128}", manifest_hash) or len(rationale) > 2000:
            raise ValueError("malformed chain revision")
        shared_upstream = chain_revision.get("shared_upstream") or None
        independent = chain_revision.get("independent_origin_plausibility")
        if shared_upstream is not None and (not isinstance(shared_upstream, str) or len(shared_upstream) > 240):
            raise ValueError("malformed shared upstream")
        if independent not in CONFIDENCES:
            raise ValueError("malformed independent-origin confidence")
    except (KeyError, TypeError, ValueError):
        row.status = "rejected"
        return row.status

    summary: dict[str, Any] = {"layers": sorted(set(classes)), "evidence_classes": classes}
    manifest: dict[str, Any] = {}
    if row.kind == "registration":
        manifest = base.manifest
        summary.update(base.summary or {})
        summary["chain_evidence_classes"] = classes
        _copy_analysis_evidence(session, case.id)
    else:
        summary.update({
            "challenged_by": challenge.submitter,
            "challenge_rationale": challenge.rationale,
            "challenge_evidence": challenge.evidence_refs,
            "evidence_digest": challenge.evidence_digest,
        })
        manifest = {
            "chain_case_id": chain_case["case_id"],
            "challenge_id": f"{chain_case['case_id']}#{expected_revision}",
            "base_revision": challenge.base_revision,
        }
    revision = CaseRevision(
        id=f"{case.id}-{expected_revision}", case_id=case.id,
        revision_number=expected_revision, verdict=verdict, confidence=confidence,
        direction=None if direction == "NONE" else direction,
        shared_upstream=shared_upstream,
        independent_origin_plausibility=independent,
        manifest_hash=manifest_hash, manifest=manifest, rationale=rationale,
        summary=summary, tx_hash=row.id, network=expected_network,
    )
    session.add(revision)
    case.current_revision = expected_revision
    case.manifest_hash = manifest_hash
    case.lifecycle = "challenged" if row.kind == "challenge" else "resolved"
    row.status = "accepted"
    if challenge:
        challenge.resulting_revision = expected_revision
        challenge.submitter = str(chain_challenge["submitter"])
        challenge.status = "recorded"
    elif row.kind == "registration":
        case.submitter = str(chain_case["submitter"])
    session.flush()
    return row.status


NOT_FOUND_GRACE = dt.timedelta(minutes=15)
POLL_INTERVAL = dt.timedelta(seconds=10)
RATE_LIMIT_BACKOFF = dt.timedelta(minutes=5)


def _within_grace(row: ChainTransaction) -> bool:
    try:
        recorded = dt.datetime.fromisoformat(str((row.payload_summary or {})["recorded_at"]))
    except (KeyError, ValueError):
        return False
    if recorded.tzinfo is None:
        recorded = recorded.replace(tzinfo=dt.timezone.utc)
    return dt.datetime.now(dt.timezone.utc) - recorded < NOT_FOUND_GRACE


def _registration_digest(case: Case, revision: CaseRevision) -> str:
    from .routes.chain import _digest_for

    return _digest_for(case, revision)


def _chain_case_matches(chain_case: dict[str, Any], case: Case, revision: CaseRevision) -> bool:
    return all(
        chain_case.get(chain_key) == expected
        for chain_key, expected in (
            ("origin_repo", case.origin_full_name), ("origin_commit", case.origin_commit),
            ("target_repo", case.target_full_name), ("target_commit", case.target_commit),
            ("manifest_hash", revision.manifest_hash),
        )
    )


def _copy_analysis_evidence(session: Session, case_id: str) -> None:
    rows = session.scalars(
        select(EvidenceItem).where(EvidenceItem.case_id == case_id, EvidenceItem.revision_number == 0)
    ).all()
    ref_ids: dict[str, str] = {}
    for item in rows:
        suffix = "-0-c" if item.id.endswith("-0-c") else "-0"
        new_id = item.id[:-len(suffix)] + suffix.replace("-0", "-1")
        ref_ids[item.id] = new_id
        if not item.evidence_type.startswith("conflicting:") and item.id.endswith("-0"):
            ref_ids[item.id[:-2]] = new_id
        session.add(EvidenceItem(
            id=new_id, case_id=item.case_id, revision_number=1, dna_layer=item.dna_layer,
            evidence_type=item.evidence_type, strength=item.strength, score=item.score,
            rationale=item.rationale, origin_source=item.origin_source,
            target_source=item.target_source, excerpt=item.excerpt,
        ))
    for explanation in session.scalars(
        select(AlternativeExplanation).where(
            AlternativeExplanation.case_id == case_id, AlternativeExplanation.revision_number == 0
        )
    ).all():
        new_id = explanation.id.replace("-0-", "-1-", 1)
        session.add(AlternativeExplanation(
            id=new_id, case_id=case_id, revision_number=1, kind=explanation.kind,
            support=explanation.support, score=explanation.score,
            rationale=explanation.rationale,
            evidence_refs=[ref_ids.get(ref, ref) for ref in explanation.evidence_refs],
            is_selected=explanation.is_selected,
        ))
    for relation in session.scalars(
        select(EvidenceRelation).where(EvidenceRelation.case_id == case_id)
    ).all():
        subject = ref_ids.get(relation.subject_ref)
        if subject:
            session.add(EvidenceRelation(
                id=f"{relation.id}-1", case_id=case_id, subject_kind=relation.subject_kind,
                subject_ref=subject, relation=relation.relation,
                object_kind=relation.object_kind, object_ref=relation.object_ref,
                weight=relation.weight,
            ))


def _set_challenge_status(session: Session, row: ChainTransaction, status: str) -> None:
    challenge_id = (row.payload_summary or {}).get("challenge_id")
    challenge = session.get(Challenge, challenge_id) if challenge_id else None
    if challenge:
        challenge.status = status


def _as_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
