"""Repository validation endpoint.

Runs before any wallet connection: knowing whether a repository is analyzable
must not require anything from the user.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter
from pydantic import BaseModel, Field

from ..config import get_settings
from ..domain import IntakeError
from ..repos.github_api import fetch_repo_metadata, recent_commits
from ..repos.github_url import validate_repo_input
from ..errors import bad_request

log = logging.getLogger(__name__)

router = APIRouter(tags=["repositories"])


class ValidateRequest(BaseModel):
    origin: str = Field(min_length=1, max_length=300)
    target: str = Field(min_length=1, max_length=300)


class RepositorySummary(BaseModel):
    full_name: str
    canonical_url: str
    commit: str
    default_branch: str
    description: str
    is_fork: bool
    parent: str | None = None
    pushed_at: int | None = None
    size_bytes: int
    recent_commits: list[dict] = []
    analyzable: bool = True
    note: str | None = None


class ValidateResponse(BaseModel):
    origin: RepositorySummary
    target: RepositorySummary
    warnings: list[str] = []


@router.post("/repositories/validate", response_model=ValidateResponse)
async def validate_repositories(payload: ValidateRequest) -> ValidateResponse:
    """Validate both repositories and pin the exact commit to be analyzed."""
    settings = get_settings()
    warnings: list[str] = []

    origin_ref = validate_repo_input(payload.origin)
    target_ref = validate_repo_input(payload.target)

    if origin_ref.full_name == target_ref.full_name:
        raise bad_request(
            "identical_repositories",
            "Choose two different repositories to compare.",
        )

    summaries: list[RepositorySummary] = []
    for ref in (origin_ref, target_ref):
        try:
            metadata = fetch_repo_metadata(
                ref, token=settings.github_token, base_url=settings.github_api_base_url
            )
        except IntakeError as exc:
            raise bad_request(exc.code, exc.message) from exc

        try:
            commits = recent_commits(
                ref, metadata, token=settings.github_token,
                base_url=settings.github_api_base_url,
            )
        except IntakeError as exc:
            # Commit history is advisory here, not fatal: a rate limit or a
            # transient GitHub error should surface as a readable 4xx with the
            # repository's details already resolved, not an opaque 500. This
            # call sits outside the metadata try/except above, so without it
            # its IntakeError escaped the handler entirely.
            raise bad_request(exc.code, exc.message) from exc
        if not commits:
            warnings.append(
                f"{ref.full_name}: commit history could not be read. Lineage "
                "conclusions will be limited."
            )
        summaries.append(
            RepositorySummary(
                full_name=metadata.ref.full_name,
                canonical_url=metadata.ref.canonical_url,
                commit=metadata.commit_sha,
                default_branch=metadata.default_branch,
                description=metadata.description,
                is_fork=metadata.is_fork,
                parent=metadata.parent_full_name,
                pushed_at=metadata.pushed_at,
                size_bytes=metadata.size_bytes,
                recent_commits=commits,
                analyzable=True,
                note=None,
            )
        )

    if summaries[0].is_fork and summaries[0].parent == summaries[1].full_name:
        warnings.append(
            f"{summaries[0].full_name} declares {summaries[1].full_name} as its "
            "upstream. Expect DECLARED_FORK rather than a derivation finding."
        )
    if summaries[1].is_fork and summaries[1].parent == summaries[0].full_name:
        warnings.append(
            f"{summaries[1].full_name} declares {summaries[0].full_name} as its "
            "upstream. Expect DECLARED_FORK rather than a derivation finding."
        )

    return ValidateResponse(origin=summaries[0], target=summaries[1], warnings=warnings)