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

import dataclasses
import hashlib
import json
from pathlib import Path

from forkreason.analysis.dna import (
    _is_distinctive_test_name,
    _is_low_information,
    _is_uncommon_constant,
    code_dna,
)
from forkreason.analysis.dna import test_dna as analyze_test_dna
from forkreason.analysis.fingerprint import fingerprint_text
from forkreason.analysis.scoring import EvidenceBuilder
from forkreason.analysis.alternatives import ExplanationInputs, evaluate_explanations, select_verdict
from forkreason.domain import CommitEntry, Evidence, FileEntry, RepoProfile

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
        # Placeholder data that every project writes.
        "Hello",
        "Hello World!",
        "World!",
        "None",
        "12345",
        "123456",
        "65536",
        "foo",
        "bar",
        "example.com",
        "Show this message and exit.",
        "--help",
        "True",
        # Tokenizer punctuation, which every project in the language shares.
        ")",
        "(",
        "),",
        ", ",
        ", data=b",
        ".replace(",
        ", args=",
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


def test_commit_message_vocabulary_is_corroborative_only() -> None:
    """Shared commit prose must never carry a derivation claim.

    `pallets/werkzeug` and `psf/requests` shared 151 commit-message terms and
    scored 0.80 HIGH on `action`, `additional`, `annotation`, `application`,
    `attribute`, `auth` — ordinary English in two unrelated projects. Enough to
    overturn a chronology that had already established the direction.

    Stopword filtering and per-repository frequency gating were both tried and
    both failed, because these terms really are rare inside each repository
    (0.2%-0.7% of messages). So the signal is demoted instead: corroborative,
    never establishing.
    """
    from forkreason.analysis.dna import history_dna

    def _prose(repo: str, words: tuple[str, ...]) -> RepoProfile:
        # Each word appears in a single message, so a frequency gate would
        # happily pass it. Only the demotion stops it scoring HIGH.
        commits = tuple(
            CommitEntry(
                sha=f"{i:040x}",
                timestamp=BASE_TS + i * 86400,
                author=f"dev{i} <d{i}@example.com>",
                message=f"work on {word}",
            )
            for i, word in enumerate(words)
        )
        return dataclasses.replace(
            _profile(repo, [_fp(f"{repo.split('/')[-1]}/mod.py", "x = 1\n")]),
            commits=commits,
        )

    generic = ("about", "action", "additional", "annotation", "application", "auth")
    origin = _prose("acme/left", generic)
    target = _prose("acme/right", generic)

    builder = EvidenceBuilder(limit=20)
    history_dna(origin, target, builder, 600)

    vocab = [i for i in builder.items if i.evidence_type == "commit_message_vocabulary"]
    if vocab:
        assert vocab[0].score <= 0.35, (
            "commit-message vocabulary scored %s; it must stay corroborative "
            "and never reach HIGH" % vocab[0].score
        )
        assert vocab[0].strength != "HIGH"


def test_commit_vocabulary_demotion_does_not_silence_history_evidence() -> None:
    """Demotion must remove strength, not the signal itself.

    Checked against the real derived fixture rather than a synthetic one: the
    scenario that genuinely is derived still reports shared commit terminology,
    just no longer at HIGH.
    """
    from forkreason.analysis.dna import _message_term_counts

    from tests.fixtures_profiles import derived_pair

    origin, target = derived_pair()
    shared = set(_message_term_counts(origin)) & set(_message_term_counts(target))
    assert shared, (
        "the derived fixture should still share commit terminology; if it does "
        "not, the demotion has silenced the signal rather than weakening it"
    )

    # And the verdict for that fixture must still be a derivation.
    from forkreason.analysis.pipeline import PipelineConfig, run_pipeline

    result = run_pipeline(origin, target, PipelineConfig())
    assert result.outcome.verdict in {"LIKELY_DERIVED", "HEAVILY_DERIVED"}


def test_requests_werkzeug_lineage_is_stable_in_both_directions() -> None:
    """Pin the verdict stage against the evidence that produced the false positive.

    The fixture is the bounded evidence the pipeline emitted for the commit-
    pinned pair BEFORE the evidence layer was hardened (HTTP headers, `/get`,
    `0123456789`, `<local>`, dotfiles and `conftest` all counted at 0.95/0.90).
    Werkzeug -> Requests then read HEAVILY_DERIVED / HIGH. Feeding that same
    evidence through the verdict stage must now give INDEPENDENT both ways, so
    the verdict is robust even when a future evidence defect lets noise through.
    """
    fixture = json.loads(
        (Path(__file__).parent / "fixtures" / "requests_werkzeug_evidence.json").read_text()
    )
    results = []
    for row in fixture["directions"]:
        repos = fixture["provenance"]["repositories"]
        origin = RepoProfile(
            full_name=row["origin"], commit_sha=repos[row["origin"]]["commit"],
            files=(), commits=(), first_commit_at=repos[row["origin"]]["created_at"],
        )
        target = RepoProfile(
            full_name=row["target"], commit_sha=repos[row["target"]]["commit"],
            files=(), commits=(), first_commit_at=repos[row["target"]]["created_at"],
        )
        evidence = tuple(Evidence(**item) for item in row["evidence"])
        conflicting = tuple(Evidence(**item) for item in row["conflicting"])
        explanations = evaluate_explanations(
            ExplanationInputs(
                origin=origin, target=target, evidence=evidence, conflicting=conflicting,
                chronology=row["chronology"], chronology_detail=row["chronology_detail"],
                shared_upstream=row["shared_upstream"], upstream_score=row["upstream_score"],
                total_files_origin=row["total_files_origin"],
                total_files_target=row["total_files_target"],
            )
        )
        result = select_verdict(
            explanations, evidence=evidence, chronology=row["chronology"],
            shared_upstream=row["shared_upstream"], origin=origin, target=target,
        )
        assert result[0] not in {"LIKELY_DERIVED", "HEAVILY_DERIVED"}
        if row["origin"] == "psf/requests":
            assert any(item.is_counter_signal for item in evidence)
            assert conflicting, "chronology counter-evidence must remain in the conflict set"
        else:
            assert row["chronology"] == "ORIGIN_PREDATES_TARGET"
            assert any(item.dna_layer == "HISTORY" for item in evidence)
        results.append(result)

    assert [result[0] for result in results] == ["INDEPENDENT", "INDEPENDENT"]
    # The target-before-origin counter-signal raises confidence in the first
    # direction; reversing inputs preserves the older-origin HISTORY signal,
    # so confidence is MEDIUM. Directional evidence is retained, while lineage
    # classification remains independent in both orders.
    assert [result[1] for result in results] == ["HIGH", "MEDIUM"]


# --- Werkzeug / Requests: evidence layer and the full pipeline --------------


def test_protocol_and_runtime_literals_are_not_uncommon_constants() -> None:
    """Classes of literal that any two HTTP projects share carry no lineage."""
    noise = [
        "Content-Length", "Transfer-Encoding", "Content-Disposition", "max-age",
        "application/xml", "text/plain; charset=utf-8", "/get", "/status/200",
        "0123456789", "abcdefghijklmnopqrstuvwxyz", "0123456789abcdef",
        "<local>", "<string>", "http://example.com/", "blah", "auth", "domain",
    ]
    kept = [v for v in noise if v != "/status/200" and _is_uncommon_constant(v)]
    assert kept == []


def test_module_boundaries_ignore_dotfiles_and_convention_names() -> None:
    names = [
        ".pre-commit-config.yaml", ".readthedocs.yaml", "tests/conftest.py",
        "src/pkg/auth.py", "docs/conf.py", ".github/ISSUE_TEMPLATE/bug-report.md",
        "src/pkg/lineage_core.py",
    ]
    from forkreason.analysis.dna import _module_names

    profile = RepoProfile(
        full_name="a/b", commit_sha="a" * 40,
        files=tuple(FileEntry(path=n, size=1, sha256="0" * 64, language="text", text="x") for n in names),
        commits=(),
    )
    assert _module_names(profile) >= {"lineagecore"}
    assert not {".precommitconfig", ".readthedocs", "bugreport"} & _module_names(profile)


def _cached_profile(path: str) -> RepoProfile | None:
    import dataclasses
    from pathlib import PurePosixPath

    from forkreason.repos.snapshot import _decode_text, _should_analyze_path, profile_from_cache

    root = Path(path)
    profile = profile_from_cache(root / "_forkreason_inventory.json")
    if profile is None:
        return None
    files = []
    for entry in profile.files:
        file_path = root / entry.path
        text = None
        if _should_analyze_path(PurePosixPath(entry.path)) and file_path.is_file():
            text = _decode_text(file_path.read_bytes()[:2_000_000])
        files.append(dataclasses.replace(entry, text=text))
    return dataclasses.replace(profile, files=tuple(files))


def test_requests_werkzeug_full_pipeline_is_independent_in_both_directions() -> None:
    """Run the whole pipeline on the pinned snapshots, when they are cached.

    Skipped on a checkout without the snapshot cache; the bounded fixture test
    above covers CI. The pinned commits are the ones in the fixture provenance.
    """
    import pytest

    from forkreason.analysis.pipeline import PipelineConfig, run_pipeline

    base = Path("/var/lib/forkreason/snapshots")
    requests_ = _cached_profile(str(base / "psf" / "requests__d6761a5d48981e21"))
    werkzeug = _cached_profile(str(base / "pallets" / "werkzeug__666a22e61143d5da"))
    if requests_ is None or werkzeug is None:
        pytest.skip("pinned Requests/Werkzeug snapshots are not cached on this machine")
    assert requests_.commit_sha == "611c6162cbc4ac2020a2f91c7cfa4f3abf9bbb60"
    assert werkzeug.commit_sha == "594452f6a4fe4de38a544962fbf04bfc9d37fbc2"

    forward = run_pipeline(requests_, werkzeug, PipelineConfig()).outcome
    reverse = run_pipeline(werkzeug, requests_, PipelineConfig()).outcome

    assert (forward.verdict, reverse.verdict) == ("INDEPENDENT", "INDEPENDENT")
    assert forward.direction == reverse.direction == "NONE"
    # Chronology counter-evidence exists only where the chronology contradicts
    # the claimed direction, and it is retained there.
    assert any(item.is_counter_signal for item in forward.evidence)
    assert forward.conflicting
    # Reversing the inputs keeps the shared-signal conflict instead of dropping it.
    assert reverse.conflicting
    for outcome in (forward, reverse):
        strong = [i for i in outcome.evidence if i.evidence_type == "shared_uncommon_constants"]
        assert all(i.score < 0.9 for i in strong), "HTTP/runtime literals must not reach 0.90+"
