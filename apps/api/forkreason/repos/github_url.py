"""GitHub repository input parsing and validation.

This module is the first gate every user-supplied string passes through, so it
is written to fail closed and to return structured reasons rather than raising
bare errors (spec FR-A-002, FR-M-001 SSRF).

Threat model:
  * Only ``github.com`` over ``https`` is accepted. No other host, no scheme
    smuggling (``javascript:``, ``file:``, ``git@``), no userinfo.
  * The owner and repository name are validated against a conservative
    character set *before* they ever reach a subprocess argument or an API
    path. Shell metacharacters are rejected outright rather than escaped,
    because escaping invites a future caller to forget.
  * Length is bounded before parsing so a 10 MB "URL" cannot be parsed at all.
  * Any character that a parser might silently rewrite (control characters,
    whitespace, tabs, newlines) is rejected before parsing. ``urlsplit`` strips
    ASCII tabs and newlines per WHATWG, so ``"a\\nb"`` would otherwise become
    ``"ab"`` and silently analyze a different repository than the user named.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import urlsplit

MAX_INPUT_LENGTH = 300
MAX_OWNER_LENGTH = 39
MAX_REPO_LENGTH = 100
COMMIT_RE = re.compile(r"^[0-9a-f]{7,40}$")

# GitHub's own rules: owners are alphanumerics and hyphens; repo names may also
# contain dots, underscores and hyphens.
_OWNER_RE = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?$")
_REPO_RE = re.compile(r"^[A-Za-z0-9_.-]{1,100}$")

# Control characters and shell metacharacters. These can never legitimately
# appear inside a repository reference. Query ('?') and fragment ('#') are
# excluded here and stripped before this scan, because GitHub URLs legitimately
# carry them.
_FORBIDDEN_CHARS_RE = re.compile(r"[\x00-\x20\x7f;&|`$(){}<>'\"\\*![\]^~]")
_SCHEME_LIKE_RE = re.compile(r"^[A-Za-z][A-Za-z0-9+.\-]*:")
_SSH_SCP_RE = re.compile(r"^[A-Za-z0-9_.\-]+@[A-Za-z0-9_.\-]+:")

ALLOWED_HOST = "github.com"
ALLOWED_SCHEME = "https"


@dataclass(frozen=True, slots=True)
class RepoRef:
    """A validated, canonical reference to a public GitHub repository."""

    owner: str
    name: str

    @property
    def full_name(self) -> str:
        return f"{self.owner}/{self.name}"

    @property
    def canonical_url(self) -> str:
        return f"{ALLOWED_SCHEME}://{ALLOWED_HOST}/{self.owner}/{self.name}"

    def __str__(self) -> str:  # pragma: no cover - trivial
        return self.full_name


class InvalidRepositoryInput(ValueError):
    """Rejected user input, with a reason safe to show a user."""

    def __init__(self, reason: str, code: str = "invalid_repository_input"):
        super().__init__(reason)
        self.reason = reason
        self.code = code


def _fail(reason: str, code: str = "invalid_repository_input") -> None:
    raise InvalidRepositoryInput(reason, code)


def _require_supported_protocol(value: str) -> None:
    """Reject any reference that is not an https GitHub URL or a bare path.

    Pure regex on the raw string — deliberately performs no parsing, so it can
    run before ``urlsplit`` gets a chance to normalize the input.
    """
    scheme_match = _SCHEME_LIKE_RE.match(value)
    if scheme_match and scheme_match.group(0)[:-1].lower() != ALLOWED_SCHEME:
        _fail(
            f"Only {ALLOWED_SCHEME}://github.com/... URLs are accepted.",
            "unsupported_scheme",
        )
    # scp-style SSH reference, e.g. "git@github.com:owner/repo". Not a URL.
    if _SSH_SCP_RE.match(value):
        _fail(
            "SSH repository references are not supported. Use "
            f"{ALLOWED_SCHEME}://{ALLOWED_HOST}/owner/repo or owner/repo.",
            "unsupported_scheme",
        )


def _require_github_https(value: str) -> str:
    """Reduce any accepted reference shape to a bare path, enforcing protocol.

    Returns the path portion (no leading or trailing slash). Raises with the
    most specific code available: an unsupported protocol is reported by
    :func:`_require_supported_protocol` before we get here, so this function
    only has to enforce the host.
    """
    if "://" in value:
        parts = urlsplit(value)
        if parts.username or parts.password or "@" in (parts.netloc or ""):
            _fail("Credentials in the URL are not accepted.", "credentials_in_url")
        host = (parts.hostname or "").lower()
        if host != ALLOWED_HOST:
            _fail(
                f"Only {ALLOWED_HOST} repositories are supported in V1.",
                "unsupported_host",
            )
        return parts.path

    lowered = value.lower()
    for prefix in (f"{ALLOWED_HOST}/", f"www.{ALLOWED_HOST}/"):
        if lowered.startswith(prefix):
            return value[len(prefix) :]

    return value


def validate_repo_input(raw: str) -> RepoRef:
    """Parse user input into a validated RepoRef.

    Accepts ``owner/repo``, ``github.com/owner/repo``, and full
    ``https://github.com/owner/repo`` URLs with optional tree/blob refs,
    trailing slashes, and query/fragment noise.

    Written as a linear pipeline so the check order is obvious: normalize the
    reference's *shape* (protocol, host) first so the user gets a precise
    reason, then bound it, then scan for forbidden characters, and only then
    validate the two identity segments.
    """
    if not isinstance(raw, str):
        _fail("Repository must be text.")
    value = raw.strip()
    if not value:
        _fail("Repository is required.")
    if len(value) > MAX_INPUT_LENGTH:
        _fail(
            f"Repository reference is too long (limit {MAX_INPUT_LENGTH} characters).",
            "input_too_long",
        )

    # 1. Protocol check, on the raw string, with no parsing. This runs first so a
    #    pasted "javascript:..." or "git@github.com:..." is reported as the wrong
    #    protocol rather than as stray punctuation.
    _require_supported_protocol(value)

    # 2. Forbidden-character scan, still on the raw string. urlsplit strips ASCII
    #    tabs and newlines per WHATWG, so 'a<nl>b' would otherwise be silently
    #    rewritten to 'ab' and we would analyze a different repository than the
    #    user named. Query and fragment are excluded because a pasted GitHub URL
    #    legitimately carries them.
    if _FORBIDDEN_CHARS_RE.search(value.split("#", 1)[0].split("?", 1)[0]):
        _fail(
            "Repository reference contains characters that are not allowed.",
            "forbidden_characters",
        )

    # 3. Host enforcement and shape reduction; only now is parsing safe.
    candidate = _require_github_https(value)
    candidate = candidate.split("#", 1)[0].split("?", 1)[0].strip("/")

    if not candidate or candidate.startswith(".") or "/." in candidate or ".." in candidate:
        _fail(
            "Use owner/repo, for example vercel/next.js.",
            "unrecognized_repository",
        )

    segments = [s for s in candidate.split("/") if s]
    if len(segments) < 2:
        _fail(
            "Use owner/repo, for example vercel/next.js.",
            "unrecognized_repository",
        )

    owner, name = segments[0], segments[1]

    # Trailing path segments are refs (tree/branch, blob/commit, commit/sha);
    # they are valid but ignored here because commit pinning happens later.
    if len(segments) > 2:
        marker = segments[2].lower()
        if (
            marker not in {"tree", "blob", "commit", "commits", "-"}
            and not COMMIT_RE.match(segments[-1])
        ):
            _fail(
                "Only repository references and tree/blob/commit paths are accepted.",
                "unsupported_path",
            )

    if len(owner) > MAX_OWNER_LENGTH:
        _fail(
            f"Owner name is too long (limit {MAX_OWNER_LENGTH} characters).",
            "invalid_owner",
        )
    if len(name) > MAX_REPO_LENGTH:
        _fail(
            f"Repository name is too long (limit {MAX_REPO_LENGTH} characters).",
            "invalid_repo_name",
        )
    if not _OWNER_RE.match(owner):
        _fail(
            "Repository owner must be 1-39 characters of letters, digits or "
            "hyphens.",
            "invalid_owner",
        )
    if not _REPO_RE.match(name):
        _fail(
            "Repository name must be letters, digits, dots, underscores or hyphens.",
            "invalid_repo_name",
        )
    if name in {".", ".."}:
        _fail("Repository name is not valid.", "invalid_repo_name")

    return RepoRef(owner=owner, name=name.removesuffix(".git"))


def validate_commit(value: str | None) -> str | None:
    """Validate a commit SHA, if one was supplied."""
    if value is None:
        return None
    candidate = value.strip().lower()
    if not candidate:
        return None
    if not COMMIT_RE.match(candidate):
        _fail("Commit must be a hexadecimal git object id.", "invalid_commit")
    return candidate


def api_repo_path(ref: RepoRef) -> str:
    """Path fragment for the GitHub REST API. Safe because ref is validated."""
    return f"/repos/{ref.owner}/{ref.name}"


def is_safe_repo_arg(value: str) -> bool:
    """Belt-and-braces check used immediately before any subprocess call."""
    return bool(_OWNER_RE.match(value)) and not _FORBIDDEN_CHARS_RE.search(value)