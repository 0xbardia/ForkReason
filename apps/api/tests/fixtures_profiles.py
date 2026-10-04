"""Synthetic repository profiles for the forensic engine tests.

These are in-process `RepoProfile` objects, not on-disk repositories. Building
them as real git repositories would test git plumbing, not the forensic
reasoning, so unit tests construct them directly. Fixture scenarios A-G (which
need real clones) live in `apps/api/tests/test_fixture_scenarios.py`.

The profiles here are deliberately not 20-line toys: they carry enough files,
history, and distinctive vocabulary that a weak implementation would produce a
different verdict than a correct one.
"""

from __future__ import annotations

import hashlib

from forkreason.domain import CommitEntry, FileEntry, RepoProfile

DAY = 86400
BASE_TS = 1_600_000_000  # 2020-09-13


def _fp(path: str, text: str) -> FileEntry:
    return FileEntry(
        path=path,
        size=len(text),
        sha256=hashlib.sha256(text.encode()).hexdigest(),
        language="python",
        text=text,
    )


def _commits(*specs: tuple[str, int, str, str]) -> tuple[CommitEntry, ...]:
    return tuple(
        CommitEntry(sha=sha, timestamp=ts, author=author, message=message)
        for sha, ts, author, message in specs
    )


BOILERPLATE_IMPORTS = """
import os
import sys
import json
import logging
from typing import Optional, List, Dict

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT = 30
"""


# --- Scenario A: target derived from origin, with rename and refactor -----

ORIGIN_CORE = """\"\"\"Reconciliation engine for distributed ledger checkpoints.\"\"\"
import hashlib

RECONCILE_BATCH = 0x1F4
MERGE_WINDOW_SECONDS = 900
CHECKPOINT_MAGIC = b"FRCKPT7"

def reconcile_orphaned_transactions(ledger_state, watermark):
    # deliberate off-by-one retained from the original implementation
    pending = []
    for index in range(0, len(ledger_state) - 1):
        tx = ledger_state[index]
        if tx.settled is False and tx.observed_at < watermark:
            pending.append(tx)
    return pending

def verify_checkpoint_chain(checkpoints, expected_root):
    running = expected_root
    for cp in checkpoints:
        running = hashlib.sha256(running + cp.digest).hexdigest()
    return running == checkpoints[-1].root_hash
"""

ORIGIN_LEDGER = """\"\"\"Ledger primitives shared across the reconciliation engine.\"\"\"
LEDGER_EPOCH = 1610000000
SETTLE_WINDOW = 900

class LedgerState:
    def __init__(self, entries):
        self.entries = entries
        self.settled = False

class SettlementError(Exception):
    pass

def settle(entries, watermark):
    stale = [e for e in entries if e.observed_at < watermark]
    if len(stale) > 0:
        raise SettlementError("stale entries present")
    return LedgerState(entries)
"""

ORIGIN_TESTS = """from ledger import LedgerState, settle
from core import reconcile_orphaned_transactions, verify_checkpoint_chain

def test_reconcile_orphaned_transactions_keeps_unsettled():
    state = [1, 2, 3]
    assert len(reconcile_orphaned_transactions(state, 10)) >= 0

def test_settlement_window_rejects_stale_entries():
    import pytest
    with pytest.raises(Exception):
        settle([1], 999999999)
"""

ORIGIN_README = """# Ledger reconciliation engine

This project reconciles orphaned transactions against a settlement watermark.

The reconciliation engine verifies checkpoint chains and settles ledger entries.
"""

# The target is the same project renamed and partially refactored: same
# constants, same distinctive tests, same off-by-one, new module names.
TARGET_ENGINE = """\"\"\"Reconciliation engine for distributed ledger checkpoints.\"\"\"
import hashlib

RECONCILE_BATCH = 0x1F4
MERGE_WINDOW_SECONDS = 900
CHECKPOINT_MAGIC = b"FRCKPT7"

def reconcile_orphaned_transactions(ledger_view, watermark):
    # deliberate off-by-one retained from the original implementation
    pending = []
    for index in range(0, len(ledger_view) - 1):
        tx = ledger_view[index]
        if tx.settled is False and tx.observed_at < watermark:
            pending.append(tx)
    return pending

def verify_checkpoint_chain(checkpoints, expected_root):
    running = expected_root
    for cp in checkpoints:
        running = hashlib.sha256(running + cp.digest).hexdigest()
    return running == checkpoints[-1].root_hash
"""

TARGET_LEDGER = """\"\"\"Ledger primitives shared across the reconciliation engine.\"\"\"
LEDGER_EPOCH = 1610000000
SETTLE_WINDOW = 900

class LedgerView:
    def __init__(self, entries):
        self.entries = entries
        self.settled = False

class SettlementError(Exception):
    pass

def settle(entries, watermark):
    stale = [e for e in entries if e.observed_at < watermark]
    if len(stale) > 0:
        raise SettlementError("stale entries present")
    return LedgerView(entries)
"""

TARGET_TESTS = """from ledger import LedgerView, settle
from engine import reconcile_orphaned_transactions, verify_checkpoint_chain

def test_reconcile_orphaned_transactions_keeps_unsettled():
    view = [1, 2, 3]
    assert len(reconcile_orphaned_transactions(view, 10)) >= 0

def test_settlement_window_rejects_stale_entries():
    import pytest
    with pytest.raises(Exception):
        settle([1], 999999999)
"""

TARGET_README = """# Ledger reconciliation engine

This project reconciles orphaned transactions against a settlement watermark.

The reconciliation engine verifies checkpoint chains and settles ledger entries.
"""


def derived_pair() -> tuple[RepoProfile, RepoProfile]:
    """Scenario A: a real derivation with rename and refactor."""
    origin = RepoProfile(
        full_name="acme/ledger-core",
        commit_sha="a1b2c3d4e5f60718293a4b5c6d7e8f9012345678",
        files=(
            _fp("core.py", ORIGIN_CORE),
            _fp("ledger.py", ORIGIN_LEDGER),
            _fp("tests/test_core.py", ORIGIN_TESTS),
            _fp("README.md", ORIGIN_README),
            _fp("setup.py", BOILERPLATE_IMPORTS + "NAME='ledger-core'\n"),
        ),
        commits=_commits(
            ("1a2b3c4d5e6f708192a3b4c5d6e7f8091a2b3c4d", BASE_TS, "ann", "initial commit"),
            ("2b3c4d5e6f708192a3b4c5d6e7f8091a2b3c4d5e", BASE_TS + 40 * DAY, "ann", "add reconciliation engine"),
            ("3c4d5e6f708192a3b4c5d6e7f8091a2b3c4d5e6f", BASE_TS + 120 * DAY, "ann", "fix: correct off-by-one in checkpoint walk"),
        ),
    )
    target = RepoProfile(
        full_name="contrib/ledger-engine",
        commit_sha="0f1e2d3c4b5a69788796a5b4c3d2e1f001122334",
        files=(
            _fp("engine.py", TARGET_ENGINE),
            _fp("ledger.py", TARGET_LEDGER),
            _fp("tests/test_engine.py", TARGET_TESTS),
            _fp("README.md", TARGET_README),
            _fp("setup.py", BOILERPLATE_IMPORTS + "NAME='ledger-engine'\n"),
        ),
        commits=_commits(
            ("4d5e6f708192a3b4c5d6e7f8091a2b3c4d5e6f70", BASE_TS + 200 * DAY, "dev", "initial import"),
            ("5e6f708192a3b4c5d6e7f8091a2b3c4d5e6f7081", BASE_TS + 205 * DAY, "dev", "rename core to engine"),
        ),
    )
    return origin, target


# --- Scenario B: both derive from a common upstream C ---------------------

UPSTREAM_LEDGER = """\"\"\"Shared upstream: canonical reconciliation primitives.\"\"\"
LEDGER_EPOCH = 1610000000
SETTLE_WINDOW = 900
CHECKPOINT_MAGIC = b"FRCKPT7"

def reconcile_orphaned_transactions(entries, watermark):
    out = []
    for index in range(0, len(entries) - 1):
        if entries[index].settled is False and entries[index].observed_at < watermark:
            out.append(entries[index])
    return out

def verify_checkpoint_chain(checkpoints, expected_root):
    import hashlib
    running = expected_root
    for cp in checkpoints:
        running = hashlib.sha256(running + cp.digest).hexdigest()
    return running == checkpoints[-1].root_hash
"""

# Both forks reimplemented the upstream independently: same vocabulary and
# constants, but different internal structure and different bug history.
FORK_A_CORE = """\"\"\"Reconciliation engine (fork A).\"\"\"
LEDGER_EPOCH = 1610000000
SETTLE_WINDOW = 900
CHECKPOINT_MAGIC = b"FRCKPT7"

class Reconciler:
    def __init__(self, entries, watermark):
        self.entries = entries
        self.watermark = watermark

    def orphans(self):
        found = []
        for position in range(0, len(self.entries) - 1):
            candidate = self.entries[position]
            if candidate.settled is False and candidate.observed_at < self.watermark:
                found.append(candidate)
        return found

    def chain_root(self, checkpoints, seed):
        import hashlib
        acc = seed
        for step in checkpoints:
            acc = hashlib.sha256(acc + step.digest).hexdigest()
        return acc
"""

FORK_B_CORE = """\"\"\"Reconciliation engine (fork B).\"\"\"
LEDGER_EPOCH = 1610000000
SETTLE_WINDOW = 900
CHECKPOINT_MAGIC = b"FRCKPT7"

def collect_orphans(entries, watermark):
    result = []
    index = 0
    while index < len(entries):
        row = entries[index]
        if row.settled is False:
            if row.observed_at < watermark:
                result.append(row)
        index = index + 1
    return result

def compute_chain(checkpoints, seed):
    import hashlib
    current = seed
    for node in checkpoints:
        current = hashlib.sha256(node.digest + current).hexdigest()
    return current
"""


def shared_upstream_triple() -> tuple[RepoProfile, RepoProfile, RepoProfile]:
    """Scenario B: both repositories descend from the same upstream."""
    upstream = RepoProfile(
        full_name="acme/reconcile-upstream",
        commit_sha="aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        files=(
            _fp("reconcile.py", UPSTREAM_LEDGER),
            _fp("README.md", "# Reconciliation upstream\n\nCanonical reconciliation primitives for ledger consumers.\n"),
            _fp("setup.py", BOILERPLATE_IMPORTS + "NAME='reconcile-upstream'\n"),
        ),
        commits=_commits(
            ("1111111111111111111111111111111111111111", BASE_TS, "up", "initial commit"),
            ("2222222222222222222222222222222222222222", BASE_TS + 30 * DAY, "up", "add chain verification"),
        ),
    )
    fork_a = RepoProfile(
        full_name="acme/reconcile-a",
        commit_sha="bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
        files=(
            _fp("reconciler.py", FORK_A_CORE),
            _fp("README.md", "# Reconciliation A\n\nA consumer implementation of the reconciliation primitives.\n"),
            _fp("setup.py", BOILERPLATE_IMPORTS + "NAME='reconcile-a'\n"),
        ),
        commits=_commits(
            ("3333333333333333333333333333333333333333", BASE_TS + 90 * DAY, "a", "initial commit"),
            ("4444444444444444444444444444444444444444", BASE_TS + 95 * DAY, "a", "add reconciler class"),
        ),
    )
    fork_b = RepoProfile(
        full_name="acme/reconcile-b",
        commit_sha="cccccccccccccccccccccccccccccccccccccccc",
        files=(
            _fp("collector.py", FORK_B_CORE),
            _fp("README.md", "# Reconciliation B\n\nAnother consumer implementation of the reconciliation primitives.\n"),
            _fp("setup.py", BOILERPLATE_IMPORTS + "NAME='reconcile-b'\n"),
        ),
        commits=_commits(
            ("5555555555555555555555555555555555555555", BASE_TS + 100 * DAY, "b", "initial commit"),
            ("6666666666666666666666666666666666666666", BASE_TS + 110 * DAY, "b", "add orphan collector"),
        ),
    )
    return fork_a, fork_b, upstream


# --- Scenario C: independent implementations of one spec -----------------

SPEC_ALPHA = '''"""Markdown to HTML converter implementing CommonMark subset."""
import re

HEADING = re.compile(r"^(#{1,6})\\s+(.*)$")
CODE_FENCE = re.compile(r"^```(\\w*)$")

def parse_headings(text):
    out = []
    for line in text.split("\\n"):
        match = HEADING.match(line)
        if match:
            out.append((len(match.group(1)), match.group(2)))
    return out

def render(text):
    return "<p>" + text.replace("\\n", "</p><p>") + "</p>"
'''

SPEC_BETA = '''"""A different markdown renderer for the same CommonMark subset."""
import re

_ATX = re.compile(r"^\\s*(#{1,6})[ \\t]+(.*?)\\s*#*\\s*$")

def extract_headings(document):
    headings = []
    for raw in document.splitlines():
        hit = _ATX.match(raw)
        if hit is not None:
            headings.append((len(hit.group(1)), hit.group(2)))
    return headings

def to_html(document):
    blocks = document.split("\\n\\n")
    return "".join("<section>" + b + "</section>" for b in blocks)
'''


def independent_pair() -> tuple[RepoProfile, RepoProfile]:
    """Scenario C: same specification, independent implementations.

    Deliberately similar vocabulary (both implement markdown headings) but
    different structure, no shared history, and no distinctive defect overlap.
    """
    origin = RepoProfile(
        full_name="acme/md-alpha",
        commit_sha="dddddddddddddddddddddddddddddddddddddddd",
        files=(
            _fp("markdown.py", SPEC_ALPHA),
            _fp("README.md", "# MD Alpha\n\nA markdown renderer supporting headings and paragraphs.\n"),
            _fp("setup.py", BOILERPLATE_IMPORTS + "NAME='md-alpha'\n"),
        ),
        commits=_commits(
            ("7777777777777777777777777777777777777777", BASE_TS + 400 * DAY, "alpha", "initial commit"),
            ("8888888888888888888888888888888888888888", BASE_TS + 410 * DAY, "alpha", "support code fences"),
        ),
    )
    target = RepoProfile(
        full_name="other/md-beta",
        commit_sha="eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee",
        files=(
            _fp("renderer.py", SPEC_BETA),
            _fp("README.md", "# MD Beta\n\nAn independent markdown renderer for the same subset.\n"),
            _fp("setup.py", BOILERPLATE_IMPORTS + "NAME='md-beta'\n"),
        ),
        commits=_commits(
            ("9999999999999999999999999999999999999999", BASE_TS + 500 * DAY, "beta", "initial commit"),
            ("aaaaaaaaaaaaabbbbbbbbbbbbbbbbcccccccccccc", BASE_TS + 505 * DAY, "beta", "tighten heading regex"),
        ),
    )
    return origin, target


# --- Scenario D: insufficient history -----------------------------------

def insufficient_pair() -> tuple[RepoProfile, RepoProfile]:
    """Scenario D: too little signal and history to conclude anything."""
    origin = RepoProfile(
        full_name="acme/sparse-a",
        commit_sha="1234567890abcdef1234567890abcdef12345678",
        files=(
            _fp("main.py", "def main():\n    print('hello')\n"),
            _fp("setup.py", BOILERPLATE_IMPORTS),
        ),
        commits=_commits(
            ("1234567890abcdef1234567890abcdef12345678", BASE_TS + 800 * DAY, "a", "init"),
        ),
    )
    target = RepoProfile(
        full_name="acme/sparse-b",
        commit_sha="fedcba0987654321fedcba0987654321fedcba09",
        files=(
            _fp("main.py", "def main():\n    print('hi')\n"),
            _fp("setup.py", BOILERPLATE_IMPORTS),
        ),
        commits=_commits(
            ("fedcba0987654321fedcba0987654321fedcba09", BASE_TS + 810 * DAY, "b", "init"),
        ),
    )
    return origin, target


# --- Scenario F: declared legitimate fork -------------------------------

def declared_fork_pair() -> tuple[RepoProfile, RepoProfile]:
    """Scenario F: target declares origin as its GitHub upstream parent."""
    origin, target = derived_pair()
    target = RepoProfile(
        full_name=target.full_name,
        commit_sha=target.commit_sha,
        files=target.files,
        commits=target.commits,
        is_fork=True,
        parent_full_name=origin.full_name,
    )
    return origin, target