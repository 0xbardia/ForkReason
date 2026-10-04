"""The six Repo DNA layers.

Each layer is an independent deterministic analysis that emits `Evidence`
objects bound to real file paths, pinned commits and bounded excerpts. Layers
do not talk to each other; `pipeline.py` combines them and ranks the result.

Why six layers instead of one similarity score: a single score cannot tell
"copied" from "both implement the same spec from the same upstream". Only the
combination of *code*, *architecture*, *history*, *bug*, *test* and *language*
evidence can, because each layer fails in a different situation.
"""

from __future__ import annotations

import re
from collections import Counter
from typing import Sequence

from ..domain import Evidence, RepoProfile, strength_for_score
from ..ids import bounded_excerpt, evidence_id
from .fingerprint import (
    DISTINCTIVE_TERMS,
    FileFingerprint,
    containment,
    fingerprint_text,
    is_common,
    jaccard,
    rarity,
    shingles,
)
from .scoring import EvidenceBuilder, cap_by_commonality, combine, lift

# --- CODE DNA ------------------------------------------------------------

_SOURCE_SUFFIXES = {
    ".py", ".js", ".jsx", ".ts", ".tsx", ".go", ".rs", ".java", ".rb",
    ".c", ".h", ".cpp", ".cc", ".hpp", ".cs", ".php", ".swift", ".kt",
}


def _is_source(path: str) -> bool:
    return any(path.endswith(s) for s in _SOURCE_SUFFIXES)


def code_dna(
    origin: RepoProfile, target: RepoProfile, builder: EvidenceBuilder, excerpt_limit: int
) -> None:
    """Normalized code structure, unusual fragments, uncommon constants."""
    origin_prints = _fingerprint_map(origin, _is_source)
    target_prints = _fingerprint_map(target, _is_source)

    # 1. Structural similarity, computed only over tokens that are NOT common
    #    framework vocabulary. Comparing raw structure sets measures how much
    #    two projects both use Python, which is not evidence of anything.
    o_struct = _rare_structure(origin_prints)
    t_struct = _rare_structure(target_prints)
    if o_struct and t_struct:
        struct_sim = containment(o_struct, t_struct)
        if struct_sim > 0.2:
            # The ceiling still applies if the only shared items are ones we
            # could not classify as rare.
            common_only = not (o_struct & t_struct)
            score = cap_by_commonality(struct_sim, common_only=common_only)
            if not common_only:
                builder.add(
                    _evidence(
                        "CODE",
                        "structural_similarity",
                        lift(score, 0.2),
                        "Normalized code structure matches on non-boilerplate "
                        "tokens across the two repositories.",
                        origin,
                        target,
                        excerpt=_pick_excerpt(origin, target, excerpt_limit, "structure"),
                    )
                )

    # 2. Unusual constants: the strongest code-level signal.
    o_consts = Counter(c for p in origin_prints.values() for c in p.constants)
    t_consts = Counter(c for p in target_prints.values() for c in p.constants)

    # A string literal that recurs across many files of a single project is
    # that project's own vocabulary — a config key, a URL scheme, an attribute
    # name — not a constant that travelled from somewhere else.
    o_files = max(1, len(origin_prints))
    t_files = max(1, len(target_prints))

    def _discriminative(value: str) -> bool:
        """Shared, but not ubiquitous on either side."""
        if not _is_uncommon_constant(value):
            return False
        # Appears in a large share of one repository's files => shared
        # vocabulary, not inherited lineage.
        o_share = o_consts[value] / o_files
        t_share = t_consts[value] / t_files
        return o_share <= 0.25 and t_share <= 0.25

    shared_consts = {
        c for c in (set(o_consts) & set(t_consts)) if _discriminative(c)
    }
    if shared_consts:
        # More distinct shared constants means less chance of coincidence.
        breadth = min(1.0, len(shared_consts) / 8.0)
        builder.add(
            _evidence(
                "CODE",
                "shared_uncommon_constants",
                min(0.95, 0.45 + breadth * 0.5),
                f"{len(shared_consts)} uncommon constant(s) appear in both "
                "repositories. Refactoring rarely preserves magic numbers.",
                origin,
                target,
                excerpt=", ".join(sorted(shared_consts)[:6]),
            )
        )

    # 3. Shingle (ordered n-gram) overlap. Restricted to tokens that are not
    #    common vocabulary: an n-gram made entirely of boilerplate is shared by
    #    every Python project ever written.
    o_rare = _rare_shingles(origin_prints)
    t_rare = _rare_shingles(target_prints)
    if o_rare and t_rare:
        shingle_sim = jaccard(o_rare, t_rare)
        if shingle_sim > 0.05:
            builder.add(
                _evidence(
                    "CODE",
                    "ordered_token_overlap",
                    min(0.85, shingle_sim * 2.2),
                    "Ordered token sequences overlap, indicating the same "
                    "implementation choices rather than the same vocabulary.",
                    origin,
                    target,
                    excerpt=_pick_excerpt(origin, target, excerpt_limit, "code"),
                )
            )

    # 4. Renamed-file lineage: same fingerprint, different path.
    #
    # Only substantive files count. An empty `__init__.py` is a convention, not
    # evidence: two unrelated Python projects were reported LIKELY_DERIVED / HIGH
    # because `tests/testserver/__init__.py` and
    # `tests/test_apps/blueprintapp/apps/__init__.py` are both empty. Byte
    # identity between two empty files carries no lineage information at all.
    origin_by_hash = {p.sha256: p for p in origin_prints.values()}
    renamed = []
    for target_p in target_prints.values():
        if _is_low_information(target_p):
            continue
        match = origin_by_hash.get(target_p.sha256)
        if match is None or match.path == target_p.path:
            continue
        if _is_low_information(match):
            continue
        renamed.append((match, target_p))
    if renamed:
        # Prefer the largest match: a shared 400-line module is far stronger
        # evidence than a shared three-line constant block.
        renamed.sort(key=lambda pair: pair[1].size, reverse=True)
        match, target_p = renamed[0]
        builder.add(
            _evidence(
                "CODE",
                "identical_content_renamed",
                0.9,
                "Identical file content exists under a different path, which is "
                "the signature of a rename during derivation.",
                origin,
                target,
                origin_path=match.path,
                target_path=target_p.path,
                # Quote the TARGET file. Passing `origin` here made the lookup
                # miss every time, so the evidence shipped with no excerpt and a
                # reader could not see what the two files actually contain.
                excerpt=_first_line(target_p.path, target, excerpt_limit),
            )
        )


# Files at or below this many non-blank lines are a package marker, a licence
# stub, or a placeholder. Byte-identity between two of them is an accident of
# language convention, not a lineage signal.
_LOW_INFORMATION_LINES = 2
# A handful of short lines is still boilerplate regardless of line count.
_LOW_INFORMATION_CHARS = 24


def _is_low_information(print_: FileFingerprint) -> bool:
    """True for files too small or too generic to carry lineage evidence."""
    if print_.line_count <= _LOW_INFORMATION_LINES:
        return True
    # A handful of short lines is still boilerplate regardless of count.
    return print_.size < _LOW_INFORMATION_CHARS


def _rare_shingles(prints: dict[str, FileFingerprint]) -> set[str]:
    """Ordered n-grams built from non-boilerplate tokens only.

    A sequence is kept only when *every* token in it is rare, so
    `import os def main print hello` never contributes evidence.
    """
    out: set[str] = set()
    for p in prints.values():
        # Rebuild shingles from the rare token subsequence so that removing
        # common tokens cannot leave a fabricated adjacency.
        rare_seq = [t for t in p.names if rarity(t) > 0]
        out |= shingles(rare_seq)
    return out


def _rare_structure(prints: dict[str, FileFingerprint]) -> set[str]:
    """Structural tokens that are not common framework vocabulary.

    This filter is the difference between "both are Python projects" and "both
    implement the same thing". Without it, a shared `import os` scores as
    perfect structural agreement (constitution II.7).
    """
    out: set[str] = set()
    for p in prints.values():
        out |= {tok for tok in p.structure_set if rarity(tok) > 0}
    return out


def _is_uncommon_constant(value: str) -> bool:
    """Reject values that collide by accident rather than by shared authorship.

    Two things pass the length test but carry no lineage information:

    * **Round numbers** — `0`, `42`, `-1`.
    * **Ordinary identifiers used as string literals.** `base_url`, `host`,
      `method`, `endpoint` are web-framework vocabulary; every project in the
      ecosystem writes them. Counting them as "uncommon constants" inflated the
      CODE score for entirely unrelated repositories — two unrelated Python
      projects were reported LIKELY_DERIVED / HIGH on a shared list of attribute
      names.

    A constant is only lineage evidence if it is both **discriminative** (rare
    enough that coincidence is unlikely) and not a plain identifier. Anything
    that is a bare lowercase identifier is configuration vocabulary.
    """

    stripped = value.strip()
    if not stripped:
        return False

    # Reject values dominated by punctuation rather than words. Source contains
    # string literals that are mostly delimiters — `, 1), (` is a real one, and
    # it is shared by every project because it comes from tokenizing calls like
    # `f(a, 1), (b)`. A lineage signal has to be mostly alphanumerics, or be an
    # obvious format string / literal value such as `%s:%d`, `--no-cache` or
    # `0x5F3759DF`, which are legitimately punctuation-heavy.
    alnum = sum(1 for ch in stripped if ch.isalnum())
    if alnum * 2 < len(stripped) and not _looks_structured(stripped):
        return False

    # A literal that is really a slice of an expression. `, data=b`, `.replace(`
    # and `, 1), (` all survive the ratio test because they contain a few
    # alphanumerics, but none of them is a value a person wrote.
    if _looks_like_code_fragment(stripped) and not _looks_structured(stripped):
        return False

    # Round and sequence numbers. `12345`, `123456`, `10000` and `65536` are
    # test fixtures and default limits that every project writes; a five-digit
    # run of digits is a placeholder far more often than a magic number. Real
    # constants carry structure (`0x5F3759DF`, `%s:%d`) rather than being a bare
    # digit run.
    if stripped.isdigit() and len(stripped) <= 6:
        return False

    if stripped in _PLACEHOLDER_CONSTANTS:
        return False

    # Placeholder text is matched case-insensitively: source writes it as
    # `Hello`, `HELLO` or `hello` depending on the string, and none of those
    # spellings carries lineage information.
    if stripped.lower() in _PLACEHOLDER_CONSTANTS:
        return False

    # Protocol and tooling vocabulary. Two web frameworks in the same ecosystem
    # share HTTP verbs, headers and MIME types by definition; none of it
    # indicates that one was derived from the other.
    if stripped.upper() in _ECOSYSTEM_VOCABULARY:
        return False

    # A bare identifier (`base_url`, `host`) is framework vocabulary, not a
    # magic constant. Require either a non-word character (0x5F3759DF,
    # %s:%d, --flag) or a name that is uncommon by the shared rarity baseline.
    if stripped.replace("_", "").isalnum() and stripped.islower():
        return not is_common(stripped)

    return True


def _looks_structured(value: str) -> bool:
    """True for a punctuation-heavy value that is still a deliberate literal.

    Format specifiers, hex literals, flags and dotted paths carry meaning in
    their punctuation. Tokenizer debris like `, 1), (` does not: its punctuation
    is arbitrary, so the words around it must dominate.
    """
    # printf/format specifiers: %s, %d, {:>8}
    if "%" in value or "{" in value and "}" in value:
        return True
    # hex / binary / octal literals
    if re.search(r"\b0[xXbBoO][0-9a-fA-F_]+", value):
        return True
    # command-line flags
    if value.startswith("-") and len(value) > 1 and not value[1].isspace():
        return True
    # Path-like or URL-like values with a recognizable separator
    if "/" in value or value.count(".") >= 2:
        return True
    return False


# Code-shaped debris: a value that reads like a fragment of an expression
# rather than a value someone wrote. `, data=b`, `.replace(` and `, args=`
# are produced by tokenizing call sites and appear in any two projects that use
# keyword arguments at all.
_FRAGMENT_TAIL = ("(", ")", ",", "[", "]", "{", "}", ";", ":", "=")
_CODE_SHAPED_TAIL = ("(", "[", "{", "=")


def _looks_like_code_fragment(value: str) -> bool:
    """True for a value that is a slice of an expression, not a literal.

    A deliberate literal does not end in an opening bracket or an assignment.
    """
    stripped = value.rstrip()
    if stripped.endswith(_CODE_SHAPED_TAIL):
        return True
    # A value whose first meaningful character is punctuation and whose last is
    # too is a slice of source, not a value: `, data=b`, `(`, `),`.
    body = stripped.lstrip()
    if body[:1] in _FRAGMENT_TAIL and body[-1:] in _FRAGMENT_TAIL:
        return True
    # A leading delimiter alone is enough: `, data=b` starts a new argument.
    if body[:1] in _FRAGMENT_TAIL:
        return True
    return False


# Placeholder text that appears verbatim in essentially every project: example
# strings, default help output and single words used as data. These were being
# counted as "uncommon constants" for pairs that share nothing.
_PLACEHOLDER_CONSTANTS = frozenset(
    {
        "true",
        "false",
        "null",
        "none",
        "hello",
        "hello world",
        "hello world!",
        "world",
        "world!",
        "foo",
        "bar",
        "baz",
        "foobar",
        "lorem ipsum",
        "test",
        "example",
        "example.com",
        "test@example.com",
        "user",
        "username",
        "password",
        "admin",
        "todo",
        "show this message and exit.",
        "usage",
        "help",
        "--help",
        "-h",
        "--version",
        "-v",
        "center",
        "left",
        "right",
    }
)


_ECOSYSTEM_VOCABULARY = frozenset(
    {
        # HTTP verbs and status classes.
        "GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS", "TRACE",
        "CONNECT",
        # Common headers and MIME types.
        "CONTENT-TYPE", "ACCEPT", "ACCEPT-ENCODING", "COOKIE", "SET-COOKIE",
        "AUTHORIZATION", "USER-AGENT", "HOST", "CONNECTION", "CACHE-CONTROL",
        "APPLICATION/JSON", "APPLICATION/X-WWW-FORM-URLENCODED",
        "TEXT/PLAIN", "TEXT/HTML", "MULTIPART/FORM-DATA",
        # CLI and config conventions.
        "UTF-8", "ASCII", "LOCALHOST", "127.0.0.1", "HTTP", "HTTPS", "SSH",
    }
)


# --- ARCHITECTURE DNA ----------------------------------------------------


def architecture_dna(
    origin: RepoProfile, target: RepoProfile, builder: EvidenceBuilder, excerpt_limit: int
) -> None:
    """Directory topology, module boundaries, subsystem organization."""
    origin_dirs = _dir_topology(origin)
    target_dirs = _dir_topology(target)

    if origin_dirs and target_dirs:
        sim = containment(origin_dirs, target_dirs)
        if sim > 0.3:
            shared = sorted(origin_dirs & target_dirs)
            builder.add(
                _evidence(
                    "ARCHITECTURE",
                    "directory_topology",
                    min(0.85, sim * 0.95),
                    f"{len(shared)} shared top-level and second-level "
                    "directories indicate the same subsystem decomposition.",
                    origin,
                    target,
                    excerpt=", ".join(shared[:10]),
                )
            )

    # Module boundary names: distinctive subsystem names are hard to
    # coincidentally share, unlike generic dirs like `src` or `utils`.
    origin_modules = _module_names(origin)
    target_modules = _module_names(target)
    shared_modules = {
        m for m in (origin_modules & target_modules)
        if not is_common(m) and len(m) >= 4
    }
    if shared_modules:
        breadth = min(1.0, len(shared_modules) / 6.0)
        builder.add(
            _evidence(
                "ARCHITECTURE",
                "shared_module_boundaries",
                min(0.9, 0.4 + breadth * 0.5),
                f"{len(shared_modules)} non-generic module name(s) are shared, "
                "suggesting the same decomposition rather than the same framework.",
                origin,
                target,
                excerpt=", ".join(sorted(shared_modules)[:8]),
            )
        )


def _dir_topology(profile: RepoProfile) -> set[str]:
    dirs: set[str] = set()
    for f in profile.files:
        parts = f.path.split("/")
        if len(parts) > 1:
            dirs.add(parts[0])
            if len(parts) > 2:
                dirs.add(f"{parts[0]}/{parts[1]}")
    return dirs


def _module_names(profile: RepoProfile) -> set[str]:
    names: set[str] = set()
    for f in profile.files:
        base = f.path.rsplit("/", 1)[-1]
        stem = base.rsplit(".", 1)[0]
        if stem not in {"index", "init", "main", "mod", "__init__"}:
            names.add(stem.lower().replace("-", "_").replace("_", ""))
    return names


# --- HISTORY DNA ---------------------------------------------------------


def history_dna(
    origin: RepoProfile, target: RepoProfile, builder: EvidenceBuilder, excerpt_limit: int
) -> None:
    """Commit chronology, first occurrence, implementation order.

    Direction-sensitive reasoning here runs on the provider's repository
    creation time, never on the bounded commit log. Reading the first commit out
    of a capped log means comparing two arbitrary recent commits and calling it
    history, and it made the verdict depend on which repository the user typed
    first: `pallets/click` vs `fastapi/typer` produced LIKELY_DERIVED in one
    direction and INDEPENDENT in the other, purely because the two windows
    happened to start at different dates.
    """
    if not origin.commits or not target.commits:
        return

    origin_span = _span(origin)
    target_span = _span(target)
    if origin_span is None or target_span is None:
        return

    o_first, o_last = origin_span
    t_first, t_last = target_span

    # Temporal direction, from honest repository creation times.
    o_created = _first_activity(origin)
    t_created = _first_activity(target)
    if o_created is not None and t_created is not None and t_created < o_created:
        builder.add(
            _evidence(
                "HISTORY",
                "target_predates_origin",
                0.8,
                "The target repository existed before the origin repository was "
                "created. The target cannot have been derived from the origin.",
                origin,
                target,
                excerpt=(
                    f"origin created {_iso(o_created)}, "
                    f"target created {_iso(t_created)}"
                ),
                counter_signal=True,
            )
        )
        return
    if o_created is not None and t_created is not None and o_created < t_created:
        # Permissive in the reverse direction too: the same pair compared the
        # other way round must not lose the fact that the origin came first.
        builder.add(
            _evidence(
                "HISTORY",
                "origin_predates_target",
                0.2,
                "The origin repository existed before the target was created, "
                "which is consistent with the target following it. Chronology "
                "alone does not establish derivation.",
                origin,
                target,
                excerpt=(
                    f"origin created {_iso(o_created)}, "
                    f"target created {_iso(t_created)}"
                ),
            )
        )

    # A target that appeared later is *permissive*, not *evidentiary*. It rules
    # nothing in on its own: two unrelated projects started a year apart look
    # exactly like this. On its own it must not be able to support derivation,
    # so it contributes zero to the derivation score and only ever appears as a
    # permissive marker.
    if t_first >= o_last:
        builder.add(
            _evidence(
                "HISTORY",
                "target_created_after_origin_matured",
                min(0.35, 0.2 + 0.15 * min(1.0, (o_last - o_first) / 86400 / 365)),
                "The target was created after the origin had already been "
                "developed. This permits derivation but does not evidence it: "
                "unrelated projects started a year apart look identical.",
                origin,
                target,
                excerpt=f"origin spans {_iso(o_first)}..{_iso(o_last)}, "
                f"target starts {_iso(t_first)}",
            )
        )

    # Commit-message vocabulary overlap.
    o_msgs = _message_terms(origin)
    t_msgs = _message_terms(target)
    if o_msgs and t_msgs:
        shared = {m for m in (o_msgs & t_msgs) if not is_common(m)}
        if len(shared) >= 3:
            builder.add(
                _evidence(
                    "HISTORY",
                    "commit_message_vocabulary",
                    min(0.8, 0.35 + len(shared) * 0.05),
                    f"{len(shared)} distinctive commit-message term(s) overlap, "
                    "which is unlikely for independent development.",
                    origin,
                    target,
                    excerpt=", ".join(sorted(shared)[:10]),
                )
            )


def _first_activity(profile: RepoProfile) -> int | None:
    """The repository's true first activity, when it is honestly known.

    `profile.commits` is capped by ANALYSIS_MAX_COMMITS, so its earliest
    timestamp is the earliest commit *inside that window* — for a repository
    with thousands of commits that is an arbitrary recent date, not its
    beginning. Two repositories compared in one direction could therefore have
    their recent histories appear to run in opposite orders, which produced
    `target_predates_origin` in one direction and nothing in the reverse. The
    provider's `created_at` is the only field that means "when this repository
    came into existence", so that is what chronology uses. When it is unknown we
    return None rather than guessing from a truncated log.
    """
    if profile.first_commit_at is not None:
        return profile.first_commit_at
    return None


def _span(profile: RepoProfile) -> tuple[int, int] | None:
    if not profile.commits:
        return None
    stamps = [c.timestamp for c in profile.commits]
    return min(stamps), max(stamps)


def _message_terms(profile: RepoProfile) -> set[str]:
    terms: set[str] = set()
    for c in profile.commits:
        for tok in re.findall(r"[A-Za-z][A-Za-z0-9_-]{3,}", c.message.lower()):
            terms.add(tok)
    return terms


# --- BUG DNA -------------------------------------------------------------

# Defect signatures are matched against source text. Each pattern encodes a
# class of error that is visible in code, is rare by construction, and survives
# a copy even when the surrounding code is renamed or reformatted.
BUG_SIGNATURES: tuple[tuple[str, str, str], ...] = (
    ("off_by_one_range", r"range\(\s*0\s*,\s*len\([^)]*\)\s*-\s*1\s*\)",
     "Classic off-by-one range construct."),
    ("mutable_default_arg", r"def\s+\w+\([^)]*=\s*\[\]|def\s+\w+\([^)]*=\s*\{\}",
     "Mutable default argument, a distinct historical defect."),
    ("bare_except", r"except\s*:\s*(?:pass|#)",
     "Bare except that silently swallows failures."),
    ("yoda_condition", r"if\s+None\s*==\s*\w+|if\s+\d+\s*==\s*\w+",
     "Yoda-style comparison, unusual outside legacy code."),
    ("float_equality", r"==\s*\d+\.\d+|!=\s*\d+\.\d+",
     "Direct floating-point equality comparison."),
    ("eval_usage", r"\beval\s*\(|exec\s*\(",
     "Dynamic evaluation of a computed string."),
    ("unbounded_recursion", r"def\s+(\w+)\(.*\):[\s\S]{0,400}?\1\s*\(",
     "Function that appears to call itself without a base case."),
)

# Bug/fix commit detection uses conventional commit prefixes and fix wording.
_FIX_MARKERS = re.compile(
    r"\b(fix|fixed|fixes|bug|hotfix|patch|resolve[sd]?|correct)\b", re.IGNORECASE
)
_INTRODUCE_MARKERS = re.compile(r"\b(introduc\w*|add\w*|initial\w*|first)\b", re.IGNORECASE)


def bug_dna(
    origin: RepoProfile, target: RepoProfile, builder: EvidenceBuilder, excerpt_limit: int
) -> None:
    """Historically traceable defects: shared defects and fix-first release.

    A target that was derived from an origin but *omits* a defect the origin
    already fixed is a strong signal, because copying the defect would have been
    the path of least resistance.
    """
    origin_sigs = _bug_signatures(origin)
    target_sigs = _bug_signatures(target)

    shared = sorted(set(origin_sigs) & set(target_sigs))
    if shared:
        builder.add(
            _evidence(
                "BUG",
                "shared_defect_signature",
                min(0.92, 0.5 + len(shared) * 0.12),
                f"{len(shared)} defect signature(s) appear in both "
                "repositories. Independent implementations rarely reproduce the "
                "same defect in the same form.",
                origin,
                target,
                excerpt="; ".join(shared[:5]),
            )
        )

    # The pre-fix behaviour test, expressed on commit history.
    origin_fixes = _fix_commits(origin)
    target_fixes = _fix_commits(target)
    if origin_fixes:
        latest_fix = max(ts for ts, _ in origin_fixes)
        target_first = _span(target)
        if target_first and target_first[0] > latest_fix:
            target_sig_names = set(target_sigs)
            origin_sig_names = set(origin_sigs)
            still_present = sorted(origin_sig_names & target_sig_names)
            if still_present:
                builder.add(
                    _evidence(
                        "BUG",
                        "target_predates_origin_fix",
                        0.55,
                        "The target appeared after the origin fixed at least one "
                        "commit but still carries a signature that looks "
                        "pre-fix. This is weaker than a shared defect because it "
                        "may be coincidence.",
                        origin,
                        target,
                        excerpt=f"origin latest fix commit {_iso(latest_fix)}",
                    )
                )


def _bug_signatures(profile: RepoProfile) -> dict[str, str]:
    found: dict[str, str] = {}
    for f in profile.files:
        if not _is_source(f.path) or f.text is None:
            continue
        for name, pattern, _desc in BUG_SIGNATURES:
            if name in found:
                continue
            if re.search(pattern, f.text):
                found[name] = f.path
    return found


def _fix_commits(profile: RepoProfile) -> list[tuple[int, str]]:
    out = []
    for c in profile.commits:
        if _FIX_MARKERS.search(c.message) and not _INTRODUCE_MARKERS.search(c.message):
            out.append((c.timestamp, c.sha[:7]))
    return out



# Test names that every project in a language writes. `test_basic` and
# `test_repr` are pytest convention, not authorship: two unrelated projects
# were reported LIKELY_DERIVED / HIGH on a shared list of them.
_GENERIC_TEST_SUFFIXES = frozenset(
    {
        "basic", "simple", "main", "init", "setup", "teardown", "empty",
        "repr", "str", "len", "eq", "equality", "hash", "bool", "iter",
        "default", "value", "values", "get", "set", "add", "remove",
        "update", "delete", "create", "read", "write", "list", "dict",
        "file", "path", "dir", "name", "type", "valid", "invalid", "error",
        "ok", "fail", "true", "false", "none", "some", "all", "one",
        "two", "new", "old", "copy", "clone", "reset", "close", "open",
        "help", "doc", "docs", "version", "config", "option", "args",
        "kwargs", "returns", "return", "raises", "raise", "call", "called",
        "works", "works2", "smoke", "sanity", "dummy", "mock", "stub",
    }
)


def _is_distinctive_test_name(name: str) -> bool:
    """True only for a test name that is not a language-wide convention.

    A distinctive name must carry domain meaning. A bare `test_basic` says
    nothing about who wrote it; `test_reconcile_orphaned_transactions` says a
    great deal. Requiring a domain-bearing segment is what separates the two.
    """

    if is_common(name) or len(name) < 8:
        return False

    # Split into the segments of the identifier.
    parts = [p for p in re.split(r"[^A-Za-z0-9]+", name) if p]
    segments: list[str] = []
    for part in parts:
        segments.extend(re.findall(r"[A-Z]+(?![a-z])|[A-Z][a-z]*|[a-z]+|[0-9]+", part))

    # Every segment generic => convention, not authorship.
    meaningful = [p for p in parts if p.lower() not in _GENERIC_TEST_SUFFIXES]
    if not meaningful:
        return False

    # Require at least one segment long enough to carry domain meaning.
    return any(len(p) >= 5 for p in meaningful)


# --- TEST DNA ------------------------------------------------------------


def test_dna(
    origin: RepoProfile, target: RepoProfile, builder: EvidenceBuilder, excerpt_limit: int
) -> None:
    """Uncommon tests, fixtures, regression scenarios, distinctive structure."""
    is_test = lambda p: (  # noqa: E731 - short local predicate
        "test" in p.lower() and p.endswith((".py", ".js", ".ts", ".rb", ".go"))
    )
    o_tests = _fingerprint_map(origin, is_test)
    t_tests = _fingerprint_map(target, is_test)

    if not o_tests or not t_tests:
        return

    o_names: set[str] = set()
    for p in o_tests.values():
        o_names |= _test_identifiers(p)
    t_names: set[str] = set()
    for p in t_tests.values():
        t_names |= _test_identifiers(p)
    shared_names = sorted(o_names & t_names)
    # A distinctive test name that appears in both is strong: nobody
    # independently writes `test_reconcile_orphaned_transactions`.
    distinctive = [n for n in shared_names if _is_distinctive_test_name(n)]
    if distinctive:
        builder.add(
            _evidence(
                "TEST",
                "shared_distinctive_test_names",
                min(0.9, 0.45 + len(distinctive) * 0.09),
                f"{len(distinctive)} distinctive test name(s) are shared, such as "
                f"{distinctive[0]!r}.",
                origin,
                target,
                excerpt=", ".join(distinctive[:6]),
            )
        )

    o_shingles = set().union(*(p.shingle_set for p in o_tests.values())) if o_tests else set()
    t_shingles = set().union(*(p.shingle_set for p in t_tests.values())) if t_tests else set()
    if o_shingles and t_shingles:
        sim = jaccard(o_shingles, t_shingles)
        if sim > 0.08:
            builder.add(
                _evidence(
                    "TEST",
                    "test_body_overlap",
                    min(0.8, sim * 1.9),
                    "Test bodies overlap in ordered token sequences, which "
                    "suggests tests travelled with the implementation.",
                    origin,
                    target,
                    excerpt=_pick_excerpt(origin, target, excerpt_limit, "test"),
                )
            )


def _test_identifiers(fp: FileFingerprint) -> set[str]:
    out: set[str] = set()
    for tok in fp.token_set:
        if tok.startswith("test") or tok.startswith("should") or tok.startswith("it"):
            out.add(tok)
    return out


# --- LANGUAGE DNA --------------------------------------------------------


def language_dna(
    origin: RepoProfile, target: RepoProfile, builder: EvidenceBuilder, excerpt_limit: int
) -> None:
    """Naming, comments, unusual terminology, distinctive phrases."""
    o_docs = _doc_fingerprints(origin)
    t_docs = _doc_fingerprints(target)

    if o_docs and t_docs:
        o_phrases = set().union(*(set(p.phrases) for p in o_docs))
        t_phrases = set().union(*(set(p.phrases) for p in t_docs))
        shared = {p for p in (o_phrases & t_phrases) if len(p) >= 12}
        if shared:
            builder.add(
                _evidence(
                    "LANGUAGE",
                    "shared_documentation_phrases",
                    min(0.85, 0.4 + len(shared) * 0.06),
                    f"{len(shared)} distinctive documentation phrase(s) are "
                    "shared, which is difficult to produce independently.",
                    origin,
                    target,
                    excerpt=" / ".join(sorted(shared)[:3]),
                )
            )

    o_terms = Counter()
    for p in o_docs:
        for tok in p.token_set:
            if tok in DISTINCTIVE_TERMS:
                o_terms[tok] += 1
    t_terms = Counter()
    for p in t_docs:
        for tok in p.token_set:
            if tok in DISTINCTIVE_TERMS:
                t_terms[tok] += 1
    shared_terms = sorted(set(o_terms) & set(t_terms))
    if shared_terms:
        builder.add(
            _evidence(
                "LANGUAGE",
                "shared_domain_vocabulary",
                min(0.75, 0.35 + len(shared_terms) * 0.08),
                f"{len(shared_terms)} distinctive domain term(s) are shared.",
                origin,
                target,
                excerpt=", ".join(shared_terms[:8]),
            )
        )


def _doc_fingerprints(profile: RepoProfile) -> list[FileFingerprint]:
    out = []
    for f in profile.files:
        if not f.path.lower().endswith((".md", ".rst", ".txt")) or f.text is None:
            continue
        out.append(fingerprint_text(f.path, f.text))
    return out


# --- helpers -------------------------------------------------------------


def _fingerprint_map(
    profile: RepoProfile, predicate
) -> dict[str, FileFingerprint]:
    out: dict[str, FileFingerprint] = {}
    for f in profile.files:
        if f.text is None or not predicate(f.path):
            continue
        out[f.path] = fingerprint_text(f.path, f.text)
    return out


def _evidence(
    layer: str,
    evidence_type: str,
    score: float,
    rationale: str,
    origin: RepoProfile,
    target: RepoProfile,
    *,
    excerpt: str | None = None,
    origin_path: str | None = None,
    target_path: str | None = None,
    excerpt_limit: int = 600,
    counter_signal: bool = False,
) -> Evidence:
    score = max(0.0, min(1.0, score))
    origin_ref = {"repo": origin.full_name, "commit": origin.commit_sha, "path": origin_path}
    target_ref = {"repo": target.full_name, "commit": target.commit_sha, "path": target_path}
    return Evidence(
        id=evidence_id(
            dna_layer=layer,
            evidence_type=evidence_type,
            origin_ref=origin_ref,
            target_ref=target_ref,
            excerpt=excerpt,
        ),
        dna_layer=layer,  # type: ignore[arg-type]
        evidence_type=evidence_type,
        strength=strength_for_score(score),
        score=score,
        rationale=rationale,
        origin_ref=origin_ref,
        target_ref=target_ref,
        excerpt=bounded_excerpt(excerpt, excerpt_limit),
    )


def _pick_excerpt(
    origin: RepoProfile, target: RepoProfile, limit: int, kind: str
) -> str | None:
    """Return a bounded excerpt from the most relevant file we can find."""
    for profile in (target, origin):
        for f in profile.files:
            if f.text is None:
                continue
            if kind == "test" and "test" not in f.path.lower():
                continue
            if kind == "structure" and not _is_source(f.path):
                continue
            if kind == "code" and not _is_source(f.path):
                continue
            first = f.text.strip().split("\n", 1)[0] if f.text.strip() else ""
            if first:
                return first[:limit]
    return None


def _first_line(path: str, profile: RepoProfile, limit: int) -> str | None:
    f = profile.file_by_path(path)
    if f is None or f.text is None:
        return None
    return f.text.strip().split("\n", 1)[0][:limit]


def _iso(ts: int) -> str:
    import datetime

    return datetime.datetime.fromtimestamp(ts, tz=datetime.timezone.utc).strftime(
        "%Y-%m-%d"
    )


from ..domain import FileEntry  # noqa: E402  (used in type hints above)