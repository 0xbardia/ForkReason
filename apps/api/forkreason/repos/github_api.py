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
from urllib.parse import urlsplit

import requests

from ..domain import IntakeError, UnsupportedRepositoryError
from .github_url import ALLOWED_HOST, RepoRef, api_repo_path, validate_repo_input
from .snapshot import IntakeLimits, RepoMetadata, check_repo_size

log = logging.getLogger(__name__)

DEFAULT_BASE_URL = "https://api.github.com"
# GitHub's own API host. A 301 rename may only be resolved against these two.
ALLOWED_API_HOST = "api.github.com"
# A repository can be renamed more than once; the hop count is bounded so a
# redirect cycle between two renamed repositories terminates.
MAX_RENAME_HOPS = 3
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


def _canonical_from_redirect(ref: RepoRef, response) -> RepoRef | None:
    """Resolve a GitHub 301 rename to a canonical `owner/name`.

    Redirects are never followed automatically — that is exactly what would let
    a hostile repository steer a request off the API host. Instead the canonical
    name is read from the `Location` header, which GitHub only sets to its own
    API host, and is put through the same validation as any user-supplied name.
    Anything that does not parse as `owner/name` on an expected host is
    rejected rather than followed.
    """

    location = (response.headers.get("Location") or "").strip()
    if not location:
        return None

    try:
        parsed = urlsplit(location)
    except ValueError:
        return None

    if parsed.scheme not in ("http", "https"):
        return None
    if parsed.netloc.lower() not in (ALLOWED_API_HOST, ALLOWED_HOST):
        return None

    parts = [p for p in parsed.path.split("/") if p]
    # The canonical API form is /repos/<owner>/<name>. A bare
    # /repositories/<id> is an ID, not a name, and must not be mistaken for
    # owner/name.
    if len(parts) >= 3 and parts[0] == "repos":
        parts = parts[1:3]
    if len(parts) != 2:
        return None
    if parts[0] == "repositories" or parts[1].isdigit():
        return None

    try:
        return validate_repo_input(f"{parts[0]}/{parts[1]}")
    except Exception:
        return None


def _resolve_by_repository_id(ref: RepoRef, response, cfg: _ClientConfig) -> RepoRef | None:
    """Resolve a transferred repository via its numeric GitHub id.

    A transfer answers 301 with `Location: .../repositories/<id>`. The id is the
    only canonical reference in that header; the real `owner/name` lives in the
    body of that endpoint. The path is rebuilt from the validated host and a
    digits-only id, so no attacker-supplied host or path can be smuggled in, and
    the resulting `full_name` is put through normal validation.
    """

    location = (response.headers.get("Location") or "").strip()
    if not location:
        return None

    try:
        parsed = urlsplit(location)
    except ValueError:
        return None

    if parsed.scheme not in ("http", "https"):
        return None
    if parsed.netloc.lower() != ALLOWED_API_HOST:
        return None

    parts = [p for p in parsed.path.split("/") if p]
    if len(parts) != 2 or parts[0] != "repositories" or not parts[1].isdigit():
        return None

    # Reconstructed from the validated host and a digits-only id.
    response = _get(f"/{parts[0]}/{parts[1]}", cfg)
    if response.status_code != 200:
        return None

    try:
        data = response.json()
    except ValueError:
        return None
    if not isinstance(data, dict):
        return None

    full_name = data.get("full_name")
    if not isinstance(full_name, str) or full_name.count("/") != 1:
        return None

    try:
        return validate_repo_input(full_name)
    except Exception:
        return None


def fetch_repo_metadata(
    ref: RepoRef, *, token: str | None = None, base_url: str | None = None
) -> RepoMetadata:
    """Fetch repository metadata and pin the current default-branch commit."""
    cfg = _config(token, base_url)
    response = _get(api_repo_path(ref), cfg)

    # GitHub answers 301 when a repository was renamed or transferred. Two
    # shapes occur:
    #
    #   * a rename, where Location is /repos/<owner>/<name> and the name is
    #     readable from the header;
    #   * a transfer, where Location is /repositories/<id> and the canonical
    #     name only exists in that endpoint's response body.
    #
    # `allow_redirects` stays False throughout: following a redirect blindly is
    # what would let a hostile repository steer a request off the API host. The
    # hop count is bounded so a cycle between two renamed repositories
    # terminates rather than spins.
    for _ in range(MAX_RENAME_HOPS):
        if response.status_code != 301:
            break

        canonical = _canonical_from_redirect(ref, response)
        if canonical is not None:
            ref = canonical
            response = _get(api_repo_path(ref), cfg)
            continue

        transferred = _resolve_by_repository_id(ref, response, cfg)
        if transferred is None:
            raise RepositoryNotFoundError(
                "repository_not_found",
                f"{ref.full_name} could not be resolved after a rename or transfer.",
            )
        ref = transferred
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

    # The repository payload does NOT include `default_branch_commit` — that
    # field only appears on search and event payloads. Verified against the live
    # API: /repos/{owner}/{repo} returns `default_branch` and nothing about its
    # HEAD, so the commit must be resolved with a second request. A repository
    # whose default branch is empty or unreadable surfaces as a clear error
    # rather than an invented commit.
    branch_commit = data.get("default_branch_commit")
    commit_sha = ""
    if isinstance(branch_commit, dict):
        commit_sha = str(branch_commit.get("sha") or "")
    if not commit_sha:
        commit_sha = _resolve_default_branch_commit(ref, default_branch, cfg)

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


def _resolve_default_branch_commit(
    ref: RepoRef, default_branch: str, cfg: _ClientConfig
) -> str:
    """Resolve the immutable commit at a repository's default branch HEAD."""
    response = _get(f"{api_repo_path(ref)}/commits/{default_branch}", cfg)
    if response.status_code != 200:
        return ""
    try:
        payload = response.json()
    except ValueError:
        return ""
    if not isinstance(payload, dict):
        return ""
    return str(payload.get("sha") or "")[:64]


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