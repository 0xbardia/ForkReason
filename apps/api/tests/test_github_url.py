"""Tests for GitHub repository input validation (spec FR-A-002)."""

from __future__ import annotations

import pytest

from forkreason.repos.github_url import (
    InvalidRepositoryInput,
    api_repo_path,
    validate_commit,
    validate_repo_input,
)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("vercel/next.js", "vercel/next.js"),
        ("  vercel/next.js  ", "vercel/next.js"),
        ("https://github.com/vercel/next.js", "vercel/next.js"),
        ("https://github.com/vercel/next.js/", "vercel/next.js"),
        ("github.com/vercel/next.js", "vercel/next.js"),
        ("www.github.com/vercel/next.js", "vercel/next.js"),
        ("https://github.com/vercel/next.js.git", "vercel/next.js"),
        ("https://github.com/vercel/next.js/tree/canary", "vercel/next.js"),
        ("https://github.com/vercel/next.js/blob/main/README.md", "vercel/next.js"),
        ("https://github.com/vercel/next.js/tree/9f1b2c3d4e5f", "vercel/next.js"),
        ("https://github.com/vercel/next.js?tab=readme#top", "vercel/next.js"),
        ("a-b/repo.name-1", "a-b/repo.name-1"),
        ("o/r", "o/r"),
    ],
)
def test_accepts_valid_shapes(raw: str, expected: str) -> None:
    assert validate_repo_input(raw).full_name == expected


def test_http_scheme_is_rejected() -> None:
    """V1 accepts https only. Upgrading http silently would be surprising."""
    with pytest.raises(InvalidRepositoryInput) as excinfo:
        validate_repo_input("http://github.com/vercel/next.js")
    assert excinfo.value.code == "unsupported_scheme"


def test_github_owner_rules_are_enforced() -> None:
    """GitHub owners are alphanumerics and hyphens only."""
    with pytest.raises(InvalidRepositoryInput):
        validate_repo_input("a_b/repo")
    with pytest.raises(InvalidRepositoryInput):
        validate_repo_input("a.b/repo")


def test_pip_style_spec_is_not_a_github_repo() -> None:
    """'owner/name@version' is not a GitHub repository reference."""
    with pytest.raises(InvalidRepositoryInput):
        validate_repo_input("genlayerlabs/genlayer-py@v0.18")


@pytest.mark.parametrize(
    ("raw", "code"),
    [
        ("", "invalid_repository_input"),
        ("justowner", "unrecognized_repository"),
        ("https://gitlab.com/a/b", "unsupported_host"),
        ("https://evil.com/a/b", "unsupported_host"),
        ("https://github.com.evil.com/a/b", "unsupported_host"),
        ("javascript:alert(1)", "unsupported_scheme"),
        ("file:///etc/passwd", "unsupported_scheme"),
        ("git@github.com:a/b", "unsupported_scheme"),
        ("https://user:pass@github.com/a/b", "credentials_in_url"),
        ("https://github.com/a b/c", "forbidden_characters"),
        ("https://github.com/-a-/b", "invalid_owner"),
        ("https://github.com/a/b;rm -rf /", "forbidden_characters"),
        ("https://github.com/a/$(whoami)", "forbidden_characters"),
        ("https://github.com/a/b|cat", "forbidden_characters"),
        ("https://github.com/a/b`id`", "forbidden_characters"),
        ("../etc/passwd", "unrecognized_repository"),
        # A 300-char input is within MAX_INPUT_LENGTH but its repo segment is
        # not, so this exercises the per-segment bound rather than the total.
        ("a/" + "x" * 200, "invalid_repo_name"),
        ("x" * 400 + "/y", "input_too_long"),
        ("https://github.com/a/b/issues/1", "unsupported_path"),
    ],
)
def test_rejects_unsafe_shapes(raw: str, code: str) -> None:
    """Every rejected input maps to a stable, specific error code."""
    with pytest.raises(InvalidRepositoryInput) as excinfo:
        validate_repo_input(raw)
    assert excinfo.value.code == code
    assert excinfo.value.reason  # never an empty user-facing reason


def test_rejects_shell_metacharacters_in_owner() -> None:
    """A subprocess argument built from user input must never be injectable."""
    for payload in ["a;id", "a|id", "a&&id", "a`id`", "a$(id)", "a id", "a\tb"]:
        with pytest.raises(InvalidRepositoryInput):
            validate_repo_input(f"https://github.com/{payload}/b")


def test_rejects_characters_a_parser_would_rewrite() -> None:
    """urlsplit strips ASCII tabs/newlines, which would silently change the repo.

    'a<newline>b' must be rejected, never normalized to 'ab'.
    """
    for payload in ["a%2Fb", "a\\b", "a\x00b", "a\nb", "a\rb", "a\tb"]:
        with pytest.raises(InvalidRepositoryInput):
            validate_repo_input(f"https://github.com/{payload}/b")


def test_newline_input_is_never_silently_normalized() -> None:
    with pytest.raises(InvalidRepositoryInput):
        validate_repo_input("https://github.com/v\nercel/next.js")


def test_non_string_input_is_rejected() -> None:
    for payload in [None, 123, [], {}]:
        with pytest.raises(InvalidRepositoryInput):
            validate_repo_input(payload)  # type: ignore[arg-type]


def test_api_repo_path_is_validated() -> None:
    ref = validate_repo_input("vercel/next.js")
    assert api_repo_path(ref) == "/repos/vercel/next.js"


def test_canonical_url_round_trips() -> None:
    ref = validate_repo_input("https://github.com/vercel/next.js/tree/main/x")
    assert validate_repo_input(ref.canonical_url).full_name == ref.full_name


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("9f1b2c3", "9f1b2c3"),
        ("9F1B2C3D4E5F6A7B", "9f1b2c3d4e5f6a7b"),
        ("", None),
        ("   ", None),
        (None, None),
    ],
)
def test_validate_commit(raw: str | None, expected: str | None) -> None:
    assert validate_commit(raw) == expected


@pytest.mark.parametrize("bad", ["zzzzzzz", "9f1b2c3;id", "../etc", "a" * 41, "9f1b2c3 4"])
def test_validate_commit_rejects_garbage(bad: str) -> None:
    with pytest.raises(InvalidRepositoryInput):
        validate_commit(bad)


def test_unsupported_path_marker_is_rejected() -> None:
    with pytest.raises(InvalidRepositoryInput):
        validate_repo_input("https://github.com/a/b/issues/1")


def test_every_rejection_carries_a_specific_code_and_reason() -> None:
    """No rejection may fall back to the generic code or an empty reason.

    Callers branch on `.code`, and users see `.reason`, so a missing code would
    silently degrade error handling and a missing reason would show a blank
    message. Assert both across a broad corpus of hostile input.
    """
    corpus = [
        "", " ", "\n", "x", "/", "//", "///", ".", "..", "../../etc/passwd",
        "a", "a/", "https://", "https://github.com", "https://github.com/",
        "github.com", "www.github.com", "http://x", "ftp://github.com/a/b",
        "ssh://git@github.com/a/b", "git@github.com:a/b", "git@github.com:",
        "javascript:alert(1)", "data:text/html,<script>", "file:///etc/passwd",
        "https://github.com:443@evil.com/a/b", "https://user@github.com/a/b",
        "https://github.com/a/b;", "https://github.com/a/b&&id",
        "https://github.com/-/-", "https://github.com/../..",
        "https://github.com/a/./b",
        "https://github.com/" + "a" * 60 + "/b",
        "https://github.com/a/" + "b" * 200,
        "\x00", "a\x00b", "a\nb", "a\tb", "a b", "a\\b", "a|b", "a&b",
    ]
    # These are deliberately *not* in the rejection corpus: the query/fragment
    # is stripped before the character scan, so script text in a fragment is
    # discarded rather than analyzed, and a leading slash is tolerated.
    accepted = [
        "/a/b",
        "https://github.com/a/b?x=<script>",
        "https://github.com/a/b#<script>",
        "https://github.com/a/b/tree/",
    ]
    for raw in accepted:
        assert validate_repo_input(raw).full_name == "a/b", raw

    for raw in corpus:
        with pytest.raises(InvalidRepositoryInput) as excinfo:
            validate_repo_input(raw)
        err = excinfo.value
        assert err.code, f"no error code for {raw!r}"
        assert err.reason.strip(), f"empty reason for {raw!r}"
        # Non-empty input must always resolve to a specific code so callers can
        # branch on it. Empty input keeps the generic code by design.
        if raw.strip():
            assert err.code != "invalid_repository_input", f"generic code for {raw!r}"
        # Reason must never echo raw input back (no reflection into UI/logs).
        assert "\n" not in err.reason and "\x00" not in err.reason