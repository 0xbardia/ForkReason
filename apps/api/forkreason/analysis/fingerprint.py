"""Deterministic source normalization and fingerprinting.

Everything here is a pure function of file content. No I/O, no network, no
model calls. That is what makes analysis reproducible (constitution II.10) and
what lets the contract trust a manifest hash.

The central idea: raw similarity is cheap and nearly useless, because every
Python project shares `import os`, `def main()`, and `if __name__`. ForkReason
only produces *evidence* from signals that survive an attempt to be
boilerplate — rare tokens, unusual constants, and structure that is specific to
an author rather than to a framework.
"""

from __future__ import annotations

import hashlib
import re
from collections import Counter
from dataclasses import dataclass
from typing import Iterable

# Tokens so common across mainstream frameworks and the standard library that
# finding them in both repositories carries almost no lineage information. A
# match on one of these can never, on its own, exceed LOW strength.
#
# This list is deliberately generous. Under-inclusion is the expensive error
# here: a token wrongly treated as distinctive produces confident nonsense
# (two projects that both `import sys` are not related).
COMMON_BOILERPLATE_TOKENS: frozenset[str] = frozenset(
    {
        # --- Python keywords / builtins / dunder ---
        "self", "none", "true", "false", "return", "class", "def", "import",
        "from", "if", "else", "elif", "for", "while", "try", "except",
        "finally", "with", "as", "in", "not", "and", "or", "is", "lambda",
        "yield", "pass", "break", "continue", "raise", "assert", "del",
        "global", "nonlocal", "await", "async", "match", "case", "nonetype",
        "__init__", "__name__", "__main__", "__doc__", "__str__", "__repr__",
        "__len__", "__iter__", "__call__", "__enter__", "__exit__",
        "__all__", "__version__", "__file__", "__class__", "__dict__",
        # --- builtins and standard library ---
        "print", "len", "str", "int", "float", "bool", "list", "dict", "set",
        "tuple", "range", "enumerate", "zip", "sorted", "sum", "min", "max",
        "abs", "open", "read", "write", "close", "append", "get", "post",
        "put", "delete", "update", "items", "keys", "values", "type", "types",
        "object", "isinstance", "issubclass", "super", "getattr", "setattr",
        "hasattr", "dir", "id", "hash", "repr", "format", "input", "iter",
        "next", "reversed", "slice", "property", "staticmethod", "classmethod",
        "sys", "os", "io", "json", "re", "math", "time", "datetime", "typing",
        "optional", "list", "dict", "tuple", "union", "any", "callable",
        "logger", "logging", "getlogger", "basicconfig", "exception",
        "subprocess", "threading", "socket", "urllib", "request", "requests",
        "pathlib", "path", "tempfile", "shutil", "glob", "csv", "sqlite",
        "hashlib", "base64", "struct", "uuid", "random", "shutil",
        "argparse", "unittest", "pytest", "mock", "patch", "assert",
        # --- generic domain vocabulary ---
        "test", "tests", "main", "init", "index", "name", "value", "key",
        "data", "result", "results", "item", "items", "config", "info",
        "debug", "error", "warning", "string", "number", "boolean", "array",
        "object", "function", "method", "parameter", "argument", "example",
        "usage", "license", "author", "version", "description", "title",
        "content", "status", "code", "message", "url", "file", "files",
        "line", "lines", "text", "http", "https", "github", "python", "pip",
        "install", "setup", "default", "user", "users", "new", "old", "all",
        "each", "other", "example", "note", "see", "use", "using", "can",
        "will", "should", "package", "module", "project", "src", "lib",
        "docs", "doc", "request", "response", "timeout", "default_timeout",
        "warning", "level", "handler", "format", "stream", "root",
    }
)

# Identifier patterns that carry authorial signal: unusual word choices,
# domain vocabulary, and compound nouns that a framework does not produce.
_IDENT_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]{2,}")
_STRING_LITERAL_RE = re.compile(r'"([^"\\\n]{3,120})"|\'([^\'\\\n]{3,120})\'')
_NUMBER_RE = re.compile(r"(?<![\w.])\d{3,}(?:\.\d+)?(?![\w.])")
_COMMENT_RE = re.compile(r"(?:#|//|/\*|\*)[^\n]{3,200}")

# Words that are unremarkable in ordinary prose but notable when they appear in
# code identifiers or comments.
DISTINCTIVE_TERMS: frozenset[str] = frozenset(
    {
        "quantum", "ledger", "ancestor", "lineage", "provenance", "genesis",
        "reconcile", "idempotent", "debounce", "throttle", "backoff",
        "canonical", "cursor", "watermark", "checkpoint", "invariant",
        "compensate", "saga", "outbox", "inbox", "poison", "quarantine",
        "sandbox", "taint", "untrusted", "escape", "normaliz", "sanitiz",
        "traversal", "symlink", "injection", "allowlist", "denylist",
        "consensus", "validator", "leader", "deterministic", "nondeterm",
        "fork", "rebase", "merge", "cherry", "ancestry", "provenance",
    }
)

_MIN_TOKEN_LEN = 3
_SHINGLE_SIZE = 5


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest()


def normalized_tokens(text: str) -> list[str]:
    """Lowercased identifier-ish tokens, filtered for signal."""
    return [
        m.group(0).lower()
        for m in _IDENT_RE.finditer(text)
        if len(m.group(0)) >= _MIN_TOKEN_LEN
    ]


def structural_tokens(text: str) -> list[str]:
    """Tokens describing structure rather than content.

    Comments and string literals are stripped so that two files differing only
    in prose do not look structurally identical, and vice versa.
    """
    stripped = re.sub(r"(?m)#.*$", " ", text)
    stripped = re.sub(r"(?m)//.*$", " ", stripped)
    stripped = re.sub(r"/\*.*?\*/", " ", stripped, flags=re.S)
    stripped = _STRING_LITERAL_RE.sub(" ", stripped)
    return normalized_tokens(stripped)


def shingles(tokens: Iterable[str], size: int = _SHINGLE_SIZE) -> set[str]:
    """Contiguous token n-grams, hashed.

    Shingles capture *ordering*, so two files with the same vocabulary in a
    different order score differently. This is the single most important
    discriminator between "shared framework" and "shared implementation".
    """
    seq = list(tokens)
    if len(seq) < size:
        return {hashlib.sha256(" ".join(seq).encode()).hexdigest()} if seq else set()
    return {
        hashlib.sha256(" ".join(seq[i : i + size]).encode()).hexdigest()
        for i in range(len(seq) - size + 1)
    }


def jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    inter = len(a & b)
    if inter == 0:
        return 0.0
    return inter / len(a | b)


def containment(a: set[str], b: set[str]) -> float:
    """Fraction of `a` that appears in `b`.

    Used instead of Jaccard when one side is much larger: if a small project was
    copied into a large one, Jaccard is diluted but containment is not.
    """
    if not a:
        return 0.0
    return len(a & b) / len(a)


def is_common(token: str) -> bool:
    return token in COMMON_BOILERPLATE_TOKENS


def rarity(token: str) -> float:
    """Weight in [0,1] reflecting how much a matching token is worth.

    Distinctive domain terms score highest; common framework tokens score zero.
    """
    if is_common(token):
        return 0.0
    if token in DISTINCTIVE_TERMS:
        return 1.0
    # Longer, compound tokens are less likely to collide by accident.
    length = len(token)
    if length >= 12:
        return 0.8
    if length >= 8:
        return 0.55
    if length >= 6:
        return 0.35
    return 0.15


@dataclass(frozen=True, slots=True)
class FileFingerprint:
    path: str
    sha256: str
    size: int
    language: str
    token_set: frozenset[str]
    shingle_set: frozenset[str]
    structure_set: frozenset[str]
    constants: tuple[str, ...]
    phrases: tuple[str, ...]
    names: tuple[str, ...]
    line_count: int

    @property
    def weighted_tokens(self) -> dict[str, float]:
        return {t: rarity(t) for t in self.token_set if rarity(t) > 0}


def extension_language(path: str) -> str:
    ext = path.rsplit(".", 1)[-1].lower() if "." in path else ""
    return {
        "py": "python", "js": "javascript", "jsx": "javascript",
        "ts": "typescript", "tsx": "typescript", "go": "go", "rs": "rust",
        "java": "java", "rb": "ruby", "c": "c", "h": "c", "cpp": "cpp",
        "cc": "cpp", "hpp": "cpp", "cs": "csharp", "php": "php", "sh": "shell",
        "md": "markdown", "json": "json", "yml": "yaml", "yaml": "yaml",
        "toml": "toml", "sql": "sql", "swift": "swift", "kt": "kotlin",
    }.get(ext, "other")


def fingerprint_text(path: str, text: str) -> FileFingerprint:
    tokens = normalized_tokens(text)
    return FileFingerprint(
        path=path,
        sha256=sha256_text(text),
        size=len(text),
        language=extension_language(path),
        token_set=frozenset(tokens),
        shingle_set=frozenset(shingles(tokens)),
        structure_set=frozenset(structural_tokens(text)),
        constants=tuple(_extract_constants(text)),
        phrases=tuple(_extract_phrases(text)),
        names=tuple(tokens),
        line_count=text.count("\n") + 1,
    )


def _extract_constants(text: str) -> list[str]:
    """Numeric literals and repeated string literals.

    Magic numbers and fixed strings are among the few things a refactor does
    not erase, which makes them disproportionately useful as lineage evidence.
    """
    out: list[str] = []
    for m in _NUMBER_RE.finditer(text):
        out.append(m.group(0))
    seen: Counter[str] = Counter()
    for m in _STRING_LITERAL_RE.finditer(text):
        value = (m.group(1) or m.group(2) or "").strip()
        if len(value) >= 4 and not value.isdigit():
            seen[value] += 1
    out.extend(v for v, n in seen.items() if n >= 2)
    return sorted(set(out))


def _extract_phrases(text: str) -> list[str]:
    """Distinctive multi-word phrases from comments and docstrings."""
    out: list[str] = []
    for m in _COMMENT_RE.finditer(text):
        phrase = " ".join(m.group(0).lstrip("#/* ").split())
        if len(phrase) >= 8:
            out.append(phrase.lower())
    return sorted(set(out))[:64]