"""Regressions for real false positives found against live repositories.

Each test here was written after ForkReason returned a confident, wrong verdict
for two repositories that are not derived from one another. They pin the fix,
and they exist because a green suite that misses these would have shipped a
forensic tool that confidently lies.

The defects, and the production evidence that exposed them:

1. Two empty `__init__.py` files matched as `identical_content_renamed` at 0.90
   HIGH. `psf/requests` and `pallets/flask` were reported LIKELY_DERIVED / HIGH
   on the strength of byte-identity between two empty package markers.
2. `shared_distinctive_test_names` scored 0.90 HIGH for `test_basic`,
   `test_repr`, `test_equality`. Those are pytest convention, not authorship.
3. HTTP verbs and MIME types counted as "uncommon constants" — two web
   frameworks in one ecosystem share them by definition.

A fourth defect (a renamed repository failing with `snapshot_unavailable`)
lives in `test_api_integration.py` because it needs a database.
"""

from __future__ import annotations

import hashlib

from forkreason.analysis.dna import (
    _is_distinctive_test_name,
    _is_low_information,
    _is_uncommon_constant,
    code_dna,
)
from forkreason.analysis.dna import test_dna as analyze_test_dna
from forkreason.analysis.fingerprint import fingerprint_text
from forkreason.analysis.scoring import EvidenceBuilder
from forkreason.domain import CommitEntry, FileEntry, RepoProfile

DAY = 86400
BASE_TS = 1_600_000_000


def _fp(path: str, text: str) -> FileEntry:
    return FileEntry(
        path=path,
        size=len(text),
        sha256=hashlib.sha256(text.encode()).hexdigest(),
        language="python",
        text=text,
    )


def _profile(name: str, files: list[FileEntry]) -> RepoProfile:
    return RepoProfile(
        full_name=name,
        commit_sha=hashlib.sha256(name.encode()).hexdigest(),
        files=tuple(files),
        commits=(
            CommitEntry(
                sha="a" * 40,
                timestamp=BASE_TS,
                author="Dev <dev@example.com>",
                message="Initial commit",
            ),
            CommitEntry(
                sha="b" * 40,
                timestamp=BASE_TS + 30 * DAY,
                author="Dev <dev@example.com>",
                message="Work",
            ),
        ),
        description="",
        is_fork=False,
        parent_full_name=None,
    )


def _types(builder: EvidenceBuilder) -> set[str]:
    return {item.evidence_type for item in builder.items}


# --- 1. Empty and trivial files are not lineage evidence ------------------


def test_identical_empty_files_are_not_rename_evidence() -> None:
    """Two empty `__init__.py` files are a language convention.

    Byte-identity between them carries no lineage information whatsoever, yet it
    was scored 0.90 HIGH, which carried a real verdict on its own.
    """
    origin = _profile(
        "psf/requests",
        [_fp("requests/__init__.py", ""), _fp("tests/testserver/__init__.py", "")],
    )
    target = _profile(
        "pallets/flask",
        [
            _fp("flask/__init__.py", ""),
            _fp("tests/test_apps/blueprintapp/apps/__init__.py", ""),
        ],
    )

    builder = EvidenceBuilder(limit=20)
    code_dna(origin, target, builder, 600)

    assert "identical_content_renamed" not in _types(builder)


def test_rename_evidence_survives_for_a_substantive_file() -> None:
    """The fix must not weaken real rename detection."""
    body = (
        "def reconcile_orphaned_transactions(ledger, cursor):\n"
        "    pending = ledger.pending_after(cursor)\n"
        "    return [t for t in pending if t.owner is None]\n"
    )
    origin = _profile("acme/original", [_fp("ledger/sync.py", body)])
    target = _profile("acme/derived", [_fp("core/reconcile.py", body)])

    builder = EvidenceBuilder(limit=20)
    code_dna(origin, target, builder, 600)

    assert "identical_content_renamed" in _types(builder)


def test_low_information_classifier_bounds() -> None:
    """Package markers and stubs are low information; real modules are not."""
    assert _is_low_information(fingerprint_text("a/__init__.py", "")) is True
    assert _is_low_information(fingerprint_text("a/b.py", "x = 1\n")) is True
    assert (
        _is_low_information(
            fingerprint_text("a/b.py", "def reconcile(x):\n    return x + 1\n")
        )
        is False
    )


# --- 2. Conventional test names are not distinctive ----------------------


def test_conventional_pytest_names_are_not_distinctive() -> None:
    """`test_basic` says nothing about who wrote it.

    These names were scored as 0.90 HIGH evidence, which is how two unrelated
    frameworks ended up LIKELY_DERIVED.
    """
    conventional = [
        "test_basic",
        "test_repr",
        "test_equality",
        "test_file",
        "test_update",
        "test_default",
        "test_empty",
        "test_error",
        "test_simple",
    ]
    kept = [n for n in conventional if _is_distinctive_test_name(n)]
    assert kept == [], f"conventional test names treated as distinctive: {kept}"


def test_domain_bearing_test_names_stay_distinctive() -> None:
    """The fix must not weaken real test-name evidence."""
    distinctive = [
        "test_reconcile_orphaned_transactions",
        "test_parse_content_type_header",
        "test_checkpoint_magic_validation",
        "test_reject_stale_revision",
    ]
    dropped = [n for n in distinctive if not _is_distinctive_test_name(n)]
    assert dropped == [], f"distinctive test names were discarded: {dropped}"


def test_shared_pytest_conventions_do_not_appear_as_test_evidence() -> None:
    """End to end: two unrelated repos sharing only conventions stay quiet."""
    origin = _profile(
        "psf/requests",
        [
            _fp("tests/test_basic.py", "def test_basic():\n    assert True\n"),
            _fp("tests/test_repr.py", "def test_repr():\n    assert True\n"),
        ],
    )
    target = _profile(
        "pallets/flask",
        [
            _fp("tests/test_basic.py", "def test_basic():\n    assert True\n"),
            _fp("tests/test_repr.py", "def test_repr():\n    assert True\n"),
        ],
    )

    builder = EvidenceBuilder(limit=20)
    analyze_test_dna(origin, target, builder, 600)

    assert "shared_distinctive_test_names" not in _types(builder)


# --- 3. Protocol vocabulary is not a magic constant ----------------------


def test_http_and_protocol_vocabulary_is_not_an_uncommon_constant() -> None:
    """Two web frameworks share HTTP verbs by definition, not by derivation."""
    ecosystem = [
        "GET",
        "POST",
        "HEAD",
        "OPTIONS",
        "Content-Type",
        "Cookie",
        "utf-8",
        "localhost",
    ]
    kept = [v for v in ecosystem if _is_uncommon_constant(v)]
    assert kept == [], f"ecosystem vocabulary counted as evidence: {kept}"


def test_genuine_magic_constants_still_count() -> None:
    """The fix must not weaken real constant evidence."""
    real = [
        "0x5F3759DF",
        "CHECKPOINT_MAGIC",
        "--no-cache",
        "%s:%d",
        "application/vnd.github+json",
    ]
    dropped = [v for v in real if not _is_uncommon_constant(v)]
    assert dropped == [], f"genuine constants were discarded: {dropped}"

# --- 4. Chronology must not depend on which side the user typed first ----


def test_verdict_does_not_depend_on_argument_order() -> None:
    """Swapping origin and target must not change the direction claim.

    This is the defect that made ForkReason untrustworthy in a way no user
    could detect: `pallets/click` vs `fastapi/typer` returned LIKELY_DERIVED /
    HIGH in one direction and INDEPENDENT in the other. The cause was reading
    the earliest commit out of a log capped at ANALYSIS_MAX_COMMITS, so the two
    repositories' bounded windows started at different dates and chronology
    read meaning into the difference. Chronology now uses the provider's
    creation time and is symmetric.
    """
    from forkreason.analysis.dna import history_dna

    day = 86_400
    base = 1_600_000_000

    click = _profile("pallets/click", [_fp("click/core.py", "def run():\n    pass\n")])
    typer = _profile("fastapi/typer", [_fp("typer/main.py", "def main():\n    pass\n")])

    # Give click the earlier creation: the target cannot have come from it.
    object.__setattr__(click, "first_commit_at", base)
    object.__setattr__(typer, "first_commit_at", base + 400 * day)

    forward = EvidenceBuilder(limit=20)
    history_dna(click, typer, forward, 600)
    reverse = EvidenceBuilder(limit=20)
    history_dna(typer, click, reverse, 600)

    fwd_types = _types(forward)
    rev_types = _types(reverse)

    # Typer (later) compared against click (earlier): nothing rules derivation out.
    assert "target_predates_origin" not in fwd_types

    # Click (earlier) compared against typer (later): this DOES rule it out,
    # and the signal must survive so the answer does not depend on typing order.
    assert "target_predates_origin" in rev_types
    assert "origin_predates_target" in fwd_types


def test_chronology_claims_nothing_when_creation_time_is_unknown() -> None:
    """An unknown creation time must produce no direction claim.

    Guessing from a capped log is exactly the bug this replaced, so with no
    honest source the honest answer is silence.
    """
    from forkreason.analysis.dna import history_dna

    older = _profile("acme/older", [_fp("a/mod.py", "x = 1\n")])
    newer = _profile("acme/newer", [_fp("b/mod.py", "x = 1\n")])
    # first_commit_at stays None for both.

    builder = EvidenceBuilder(limit=20)
    history_dna(older, newer, builder, 600)

    claimed = _types(builder) & {"target_predates_origin", "origin_predates_target"}
    assert claimed == set(), f"direction claimed without a creation time: {claimed}"
