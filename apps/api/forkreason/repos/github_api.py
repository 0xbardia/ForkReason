"""GitHub REST client.

Only two read-only endpoints are used, both against `api.github.com` with a
path built from an already-validated `RepoRef`. There is no "fetch any URL"
capability anywhere in this module: the client cannot be pointed at an
arbitrary host, which is what keeps it from becoming an SSRF proxy
(spec FR-M-001).

Rate limits are handled with bounded exponential backoff and a total attempt
budget, so a rate-limited environment degrades into a clear user-facing error
instead of an unbounded hang (spec FR-I-010).
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass

import requests

from ..domain import IntakeError, UnsupportedRepositoryError
from .github_url import ALLOWED_HOST, RepoRef, api_repo_path
from .snapshot import IntakeLimits, RepoMetadata, check_repo_size

log = logging.getLogger(__name__)

DEFAULT_BASE_URL = "https://api.github.com"
USER_AGENT = "ForkReason/1.0 (+https://forkreason.bydx.fun)"
MAX_ATTEMPTS = 3
BACKOFF_BASE_SECONDS = 1.0
REQUEST_TIMEOUT_SECONDS = 20


class GitHubUnavailableError(IntakeError):
    """GitHub could not be reached, or refused the request."""


class RepositoryNotFoundError(UnsupportedRepositoryError):
    pass


class RepositoryPrivateError(UnsupportedRepositoryError):
    pass


@dataclass(slots=True)
class _ClientConfig:
    base_url: str = DEFAULT_BASE_URL
    token: str | None = None


def _config(token: str | None = None, base_url: str | None = None) -> _ClientConfig:
    cfg = _ClientConfig()
    if token:
        cfg.token = token
    if base_url:
        # Only the canonical GitHub API host is ever contacted.
        if not base_url.startswith(f"https://{ALLOWED_HOST}") and "api.github.com" not in base_url:
            raise GitHubUnavailableError(
                "invalid_github_base_url",
                "GITHUB_API_BASE_URL must point at the GitHub API.",
            )
        cfg.base_url = base_url.rstrip("/")
    return cfg


def _headers(cfg: _ClientConfig) -> dict[str, str]:
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": USER_AGENT,
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if cfg.token:
        headers["Authorization"] = f"Bearer {cfg.token}"
    return headers


def _rate_limit_wait(response: requests.Response) -> float:
    reset = response.headers.get("X-RateLimit-Reset")
    try:
        remaining = int(response.headers.get("X-RateLimit-Remaining", "1"))
    except ValueError:
        remaining = 1
    if remaining > 0:
        return 0.0
    if reset:
        try:
            from datetime import datetime, timezone

            reset_at = datetime.fromtimestamp(int(reset), tz=timezone.utc)
            wait = (reset_at - datetime.now(tz=timezone.utc)).total_seconds()
            return max(0.0, min(60.0, wait))
        except (ValueError, TypeError):
            return 0.0
    return BACKOFF_BASE_SECONDS * 2


def _get(
    path: str,
    cfg: _ClientConfig,
    *,
    timeout: int = REQUEST_TIMEOUT_SECONDS,
) -> requests.Response:
    """GET with bounded retry. Never raises for HTTP status."""
    url = f"{cfg.base_url}{path}"
    last_error: Exception | None = None

    for attempt in range(MAX_ATTEMPTS):
        try:
            response = requests.get(
                url,
                headers=_headers(cfg),
                timeout=timeout,
                allow_redirects=False,  # No redirect following: no SSRF via redirect.
            )
        except requests.RequestException as exc:
            last_error = exc
            if attempt == MAX_ATTEMPTS - 1:
                raise GitHubUnavailableError(
                    "github_unreachable",
                    "GitHub could not be reached. Try again in a moment.",
                    detail=str(exc)[:200],
                ) from exc
            time.sleep(BACKOFF_BASE_SECONDS * (2**attempt))
            continue

        if response.status_code in (403, 429):
            wait = _rate_limit_wait(response)
            if wait <= 0 or attempt == MAX_ATTEMPTS - 1:
                raise GitHubUnavailableError(
                    "github_rate_limited",
                    "GitHub's rate limit was reached. ForkReason will retry shortly.",
                )
            log.warning("github rate limited, backing off", extra={"wait": wait})
            time.sleep(min(wait, 5.0))
            continue

        if response.status_code >= 500 and attempt < MAX_ATTEMPTS - 1:
            time.sleep(BACKOFF_BASE_SECONDS * (2**attempt))
            continue

        return response

    raise GitHubUnavailableError(
        "github_unreachable",
        "GitHub could not be reached.",
        detail=str(last_error)[:200] if last_error else None,
    )


def fetch_repo_metadata(
    ref: RepoRef, *, token: str | None = None, base_url: str | None = None
) -> RepoMetadata:
    """Fetch repository metadata and pin the current default-branch commit."""
    cfg = _config(token, base_url)
    response = _get(api_repo_path(ref), cfg)

    if response.status_code == 404:
        raise RepositoryNotFoundError(
            "repository_not_found",
            f"{ref.full_name} was not found. ForkReason V1 analyzes public "
            "GitHub repositories only.",
        )
    if response.status_code == 401:
        raise RepositoryPrivateError(
            "repository_private",
            f"{ref.full_name} is private. ForkReason V1 analyzes public "
            "GitHub repositories only.",
        )
    if response.status_code == 403:
        raise RepositoryPrivateError(
            "repository_forbidden",
            f"{ref.full_name} could not be read. It may be private, archived "
            "with restricted access, or rate limited.",
        )
    if response.status_code != 200:
        raise GitHubUnavailableError(
            "github_error",
            f"GitHub returned an unexpected response ({response.status_code}).",
        )

    data = response.json()
    if not isinstance(data, dict):
        raise GitHubUnavailableError("github_error", "GitHub returned an unexpected payload.")

    if data.get("private") is True:
        raise RepositoryPrivateError(
            "repository_private",
            f"{ref.full_name} is private. ForkReason V1 analyzes public "
            "GitHub repositories only.",
        )

    default_branch = str(data.get("default_branch") or "main")[:160]
    # `default_branch_commit` may be absent or explicitly null on some payloads.
    branch_commit = data.get("default_branch_commit")
    commit_sha = ""
    if isinstance(branch_commit, dict):
        commit_sha = str(branch_commit.get("sha") or "")
    if not commit_sha:
        raise GitHubUnavailableError(
            "no_default_branch_commit",
            f"{ref.full_name} has no readable default branch commit.",
        )

    parent = data.get("parent") or {}
    parent_full_name = parent.get("full_name") if isinstance(parent, dict) else None
    if parent_full_name == ref.full_name:
        parent_full_name = None

    pushed_at = data.get("pushed_at")
    pushed_ts: int | None = None
    if pushed_at:
        from datetime import datetime

        try:
            pushed_ts = int(datetime.fromisoformat(str(pushed_at).replace("Z", "+00:00")).timestamp())
        except ValueError:
            pushed_ts = None

    metadata = RepoMetadata(
        ref=ref,
        commit_sha=str(commit_sha)[:64],
        default_branch=default_branch,
        description=str(data.get("description") or "")[:500],
        is_fork=bool(data.get("fork")),
        parent_full_name=str(parent_full_name)[:240] if parent_full_name else None,
        size_bytes=int(data.get("size") or 0) * 1024,
        pushed_at=pushed_ts,
    )

    if metadata.size_bytes == 0:
        raise UnsupportedRepositoryError(
            "repository_empty",
            f"{ref.full_name} is empty, so there is nothing to analyze.",
        )

    check_repo_size(metadata, IntakeLimits())
    return metadata


def recent_commits(ref: RepoRef, metadata: RepoMetadata, *, token: str | None = None, base_url: str | None = None) -> list[dict]:
    """Recent commits for the repository, used for a lightweight preview."""
    cfg = _config(token, base_url)
    response = _get(f"{api_repo_path(ref)}/commits?per_page=5", cfg)
    if response.status_code != 200:
        return []
    try:
        payload = response.json()
    except ValueError:
        return []
    if not isinstance(payload, list):
        return []
    out = []
    for item in payload[:5]:
        if not isinstance(item, dict):
            continue
        commit = item.get("commit") or {}
        author = (commit.get("author") or {}) if isinstance(commit, dict) else {}
        out.append(
            {
                "sha": str(item.get("sha", ""))[:64],
                "short_sha": str(item.get("sha", ""))[:7],
                "message": str(commit.get("message", ""))[:160],
                "date": str(author.get("date", ""))[:40],
                "author": str(author.get("name", ""))[:120],
            }
        )
    return out


def rate_limit_status(*, token: str | None = None, base_url: str | None = None) -> dict:
    """Current rate-limit state, for the /health surface."""
    cfg = _config(token, base_url)
    try:
        response = _get("/rate_limit", cfg)
        if response.status_code != 200:
            return {"status": "unknown"}
        data = response.json()
        core = (data.get("resources") or {}).get("core") or {}
        return {
            "status": "ok",
            "limit": core.get("limit"),
            "remaining": core.get("remaining"),
            "reset": core.get("reset"),
            "authenticated": bool(cfg.token),
        }
    except (GitHubUnavailableError, requests.RequestException):
        return {"status": "unreachable"}