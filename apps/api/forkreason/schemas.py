"""Pydantic transport schemas.

Separate from the ORM models: an HTTP payload must not be able to set a
database column that has no business being set by a request (constitution
VI.24). Write payloads are strictly allowlisted.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from .domain import BANNED_TERMS, CONFIDENCES, VERDICTS


def _reject_banned(text: str, field: str) -> str:
    """Guard the product's language boundary at the edge.

    ForkReason must never emit an accusatory or legal conclusion (constitution
    I.1). This is enforced where external input is accepted, so user-supplied
    text cannot introduce banned vocabulary into a stored report.
    """
    lowered = text.lower()
    for term in BANNED_TERMS:
        if term in lowered:
            raise ValueError(
                f"{field} must not use accusatory or legal-conclusion language."
            )
    return text


class SubmitCasePayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    case_id: str = Field(min_length=8, max_length=64, pattern=r"^[0-9a-f]+$")
    revision_number: int = Field(ge=1, le=10_000)


class RecordRevisionPayload(BaseModel):
    """Recorded after a wallet-signed transaction reaches finality."""

    model_config = ConfigDict(extra="forbid")

    case_id: str = Field(min_length=8, max_length=64, pattern=r"^[0-9a-f]+$")
    revision_number: int = Field(ge=1, le=10_000)
    tx_hash: str = Field(min_length=16, max_length=80, pattern=r"^[0-9a-fA-Fx]+$")
    network: str = Field(min_length=2, max_length=32)
    status: str = Field(default="submitted", max_length=32)


class VerdictOut(BaseModel):
    verdict: str
    confidence: str
    direction: str | None = None


def validate_verdict(verdict: str, confidence: str, direction: str | None) -> None:
    """Assert a triple is inside the supported set.

    Used by tests and by any path that accepts a verdict from outside the
    deterministic pipeline (for example a chain mirror).
    """
    if verdict not in VERDICTS:
        raise ValueError(f"unsupported verdict: {verdict}")
    if confidence not in CONFIDENCES:
        raise ValueError(f"unsupported confidence: {confidence}")
    if direction is not None and direction not in {"ORIGIN_TO_TARGET", "TARGET_TO_ORIGIN", "NONE"}:
        raise ValueError(f"unsupported direction: {direction}")