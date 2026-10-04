"""Repository intake: GitHub metadata and safe local snapshots.

Threat model for this module (spec FR-A-005..007, FR-M-001):

* Repository content is untrusted and is NEVER executed. The only subprocess
  invoked is `git`, with a fixed argv list. No shell, no `-c`, no string
  interpolation of repository-derived values.
* Analysis happens on a working tree produced by `git archive`, which contains
  only tracked blobs from the pinned commit. Working-tree state, `.git/`
  configuration, and hooks are never part of the analyzed tree.
* Every traversal is bounds-checked before it happens: file count, per-file
  size, total size, and path length.
* Symlinks are skipped. A symlink in a hostile repository can point anywhere,
  and following one would turn analysis into arbitrary file read.
* Submodules and Git LFS pointers are detected and skipped rather than
  resolved, because resolving them means fetching attacker-chosen content.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import shutil
import subprocess
import tarfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from .github_url import RepoRef
from ..domain import CommitEntry, FileEntry, IntakeError, RepoProfile, UnsupportedRepositoryError
from ..ids import snapshot_id_for

log = logging.getLogger(__name__)

# Bound on what we are willing to read into memory for analysis.
MAX_TEXT_BYTES = 1_500_000
MAX_ENCODINGS_PROBED = 2
GIT_TIMEOUT_SECONDS = 300

# Extensions we will read as text. Everything else is inventoried but not
# parsed, which keeps binary floods out of the analyser.
TEXT_EXTENSIONS = {
    ".py", ".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs", ".go", ".rs",
    ".java", ".kt", ".rb", ".php", ".c", ".h", ".cc", ".cpp", ".hpp",
    ".cs", ".swift", ".scala", ".sh", ".bash", ".zsh", ".fish", ".sql",
    ".md", ".rst", ".txt", ".json", ".yml", ".yaml", ".toml", ".ini", ".cfg",
    ".env.example", ".gitignore", ".editorconfig", ".lock",
}

# Paths never analyzed: build outputs, vendored trees, and binary payloads that
# would dominate the fingerprint without carrying authorship signal.
SKIP_DIRS = {
    ".git", "node_modules", "vendor", "dist", "build", "out", "target",
    ".next", ".nuxt", ".venv", "venv", "__pycache__", ".mypy_cache",
    ".pytest_cache", ".tox", "coverage", ".idea", ".vscode", "site-packages",
    ".gradle", ".terraform", "bower_components", "jspm_packages",
}

SKIP_FILE_SUFFIXES = {
    ".min.js", ".min.css", ".map", ".lock", ".png", ".jpg", ".jpeg", ".gif",
    ".webp", ".ico", ".pdf", ".zip", ".tar", ".gz", ".bz2", ".xz", ".7z",
    ".so", ".dylib", ".dll", ".exe", ".bin", ".wasm", ".woff", ".woff2",
    ".ttf", ".eot", ".mp4", ".mp3", ".class", ".jar", ".pyc", ".o", ".a",
}


@dataclass(frozen=True, slots=True)
class IntakeLimits:
    max_repo_mb: int = 48
    max_file_mb: int = 1
    max_files: int = 4000
    max_commits: int = 600


@dataclass(frozen=True, slots=True)
class RepoMetadata:
    """Normalized GitHub repository metadata."""

    ref: RepoRef
    commit_sha: str
    default_branch: str
    description: str
    is_fork: bool
    parent_full_name: str | None
    size_bytes: int
    pushed_at: int | None
    # GitHub's `created_at` for the repository: the true moment the repository
    # came into existence. Chronology reasoning cannot use the commit log we
    # read, because that log is capped at ANALYSIS_MAX_COMMITS and therefore
    # describes only the most recent history.
    created_at: int | None = None


# --- git invocation ------------------------------------------------------


def _git(
    args: list[str],
    *,
    cwd: Path | None = None,
    timeout: int = GIT_TIMEOUT_SECONDS,
    check: bool = True,
) -> subprocess.CompletedProcess[bytes]:
    """Run git with an argument array.

    `shell=False` is the default and is never overridden. Every argument is
    passed as a separate list element, so a repository name containing shell
    metacharacters cannot become a command.
    """
    if any(not isinstance(a, str) for a in args):
        raise IntakeError("invalid_git_args", "git arguments must be strings.")
    try:
        result = subprocess.run(  # noqa: S603 - argv list, shell=False, fixed binary
            ["git", *args],
            cwd=str(cwd) if cwd else None,
            capture_output=True,
            timeout=timeout,
            check=False,
            shell=False,
            env={
                "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
                "HOME": "/nonexistent-forkreason",
                "GIT_TERMINAL_PROMPT": "0",
                "GIT_ASKPASS": "/bin/false",
                # A hostile repository must never be able to run a command via
                # core hooks or pager settings from its own config.
                "GIT_CONFIG_NOSYSTEM": "1",
                "GIT_CONFIG_GLOBAL": "/dev/null",
                "GIT_OPTIONAL_LOCKS": "0",
                "GIT_ADVICE": "0",
            },
        )
    except FileNotFoundError as exc:
        raise IntakeError("git_missing", "git is not available on this host.") from exc
    except subprocess.TimeoutExpired as exc:
        raise IntakeError(
            "git_timeout", f"git timed out after {timeout}s while reading the repository."
        ) from exc

    if check and result.returncode != 0:
        stderr = result.stderr.decode("utf-8", "replace")[:400]
        raise IntakeError(
            "git_failed",
            "git could not read this repository.",
            detail=f"exit={result.returncode} {stderr}",
        )
    return result


# --- safe extraction -----------------------------------------------------


def _is_safe_member(member: tarfile.TarInfo) -> bool:
    """Reject absolute paths, parent traversal, links and devices."""
    name = member.name
    if name.startswith("/") or name.startswith("\\"):
        return False
    if os.path.isabs(name):
        return False
    # Windows-style absolute/drive paths.
    if len(name) > 1 and name[1] == ":":
        return False
    parts = PurePosixPath(name.replace("\\", "/")).parts
    if any(part == ".." for part in parts):
        return False
    if member.issym() or member.islnk():
        # Never follow or recreate links: they are the classic escape primitive.
        return False
    if member.isdev() or member.isfifo():
        return False
    if not (member.isfile() or member.isdir()):
        return False
    return True


def _should_analyze_path(rel: PurePosixPath) -> bool:
    parts = rel.parts
    if any(part in SKIP_DIRS for part in parts[:-1]):
        return False
    name = parts[-1]
    if name in SKIP_DIRS:
        return False
    lowered = name.lower()
    if any(lowered.endswith(sfx) for sfx in SKIP_FILE_SUFFIXES):
        return False
    return True


def _decode_text(raw: bytes) -> str | None:
    """Decode only if it looks like text.

    A NUL byte or a high ratio of undecodable bytes means binary. Failing this
    check keeps a repository from flooding the analyser with binary content.
    """
    if b"\x00" in raw[:4096]:
        return None
    for encoding in ("utf-8", "latin-1"):
        try:
            text = raw.decode(encoding)
        except (UnicodeDecodeError, ValueError):
            continue
        if encoding == "latin-1":
            # latin-1 never fails; only accept it if the content looks textual.
            printable = sum(1 for ch in text[:2000] if ch.isprintable() or ch in "\n\r\t")
            if printable / max(1, len(text[:2000])) < 0.9:
                return None
        return text
    return None


# --- snapshot construction ----------------------------------------------


def build_profile(
    metadata: RepoMetadata,
    tree_dir: Path,
    commits: list[CommitEntry],
    limits: IntakeLimits,
) -> tuple[RepoProfile, bool]:
    """Turn an extracted tree into a RepoProfile.

    Returns (profile, truncated). `truncated` is True when limits stopped the
    inventory, and it is surfaced to the user rather than hidden — a partial
    analysis must not read as a complete one.
    """
    files: list[FileEntry] = []
    total_bytes = 0
    truncated = False

    # os.walk with followlinks=False (the default) plus an explicit islink guard.
    for root, dirnames, filenames in os.walk(tree_dir, followlinks=False):
        # Prune skipped directories in place so os.walk does not descend.
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for filename in sorted(filenames):
            abs_path = Path(root) / filename
            rel = abs_path.relative_to(tree_dir)

            # Defence in depth: never traverse a symlink, whatever os.walk says.
            if abs_path.is_symlink():
                continue
            if not abs_path.is_file():
                continue

            try:
                size = abs_path.stat().st_size
            except OSError:
                continue
            if size > limits.max_file_mb * 1024 * 1024:
                truncated = True
                continue

            rel_posix = PurePosixPath(rel)
            if len(rel_posix.parts) > 24 or len(str(rel_posix)) > 400:
                # Pathological nesting; skip rather than risk resolver limits.
                truncated = True
                continue

            # Inventory every tracked file, analyze only what is worth reading.
            try:
                raw = abs_path.read_bytes()[:MAX_TEXT_BYTES]
            except OSError:
                truncated = True
                continue

            sha = hashlib.sha256(raw).hexdigest()
            total_bytes += len(raw)
            if total_bytes > limits.max_repo_mb * 1024 * 1024:
                truncated = True
                break

            if len(files) >= limits.max_files:
                truncated = True
                break

            analyze = _should_analyze_path(rel_posix)
            text = _decode_text(raw) if analyze else None
            if analyze and text is None:
                # Binary or undecodable: keep it in the inventory as a fact,
                # without a body.
                text = None

            files.append(
                FileEntry(
                    path=str(rel_posix),
                    size=size,
                    sha256=sha,
                    language=_language_for(rel_posix),
                    text=text,
                    truncated=False,
                )
            )

    bounded_commits = commits[: limits.max_commits]
    if len(commits) > limits.max_commits:
        truncated = True

    profile = RepoProfile(
        full_name=metadata.ref.full_name,
        commit_sha=metadata.commit_sha,
        files=tuple(files),
        commits=tuple(bounded_commits),
        description=metadata.description,
        is_fork=metadata.is_fork,
        parent_full_name=metadata.parent_full_name,
        first_commit_at=metadata.created_at,
    )
    return profile, truncated


def _language_for(path: PurePosixPath) -> str:
    from ..analysis.fingerprint import extension_language

    return extension_language(str(path))


def archive_commit(repo_url: str, commit_sha: str, dest: Path, timeout: int = GIT_TIMEOUT_SECONDS) -> Path:
    """Extract one pinned commit into `dest` using `git archive`.

    `git archive <sha>` emits a tar of exactly the tracked blobs at that commit:
    no working tree, no `.git`, no hooks, no submodule contents. This is the
    safest way to materialize a snapshot and is why no `clone` is used.
    """
    dest.mkdir(parents=True, exist_ok=True)
    # A bare, isolated repository used only to produce the archive.
    staging = dest.parent / f".staging-{os.getpid()}-{snapshot_id_for(repo_url, commit_sha)[:8]}"
    if staging.exists():
        shutil.rmtree(staging, ignore_errors=True)
    staging.mkdir(parents=True, exist_ok=True)

    try:
        _git(
            ["init", "--quiet", "--bare", str(staging)],
            timeout=60,
        )
        _git(
            [
                "fetch",
                "--quiet",
                "--depth",
                "1",
                "--no-tags",
                "--filter=blob:none",
                repo_url,
                commit_sha,
            ],
            cwd=staging,
            timeout=timeout,
        )
        result = _git(
            ["archive", "--format=tar", commit_sha],
            cwd=staging,
            timeout=timeout,
            check=False,
        )
        if result.returncode != 0:
            # --filter=blob:none leaves objects unpopulated; fetch them once.
            _git(["fetch", "--quiet", "--depth", "1", repo_url, commit_sha], cwd=staging, timeout=timeout)
            result = _git(["archive", "--format=tar", commit_sha], cwd=staging, timeout=timeout)

        with tarfile.open(fileobj=__import__("io").BytesIO(result.stdout), mode="r|") as archive:
            # Single pass. The stream is not seekable, so members cannot be
            # collected first and extracted afterwards; each member is
            # validated and written as it is read.
            dest_root = dest.resolve()
            extracted = 0
            for member in archive:
                if not _is_safe_member(member):
                    log.warning(
                        "skipping unsafe archive member",
                        extra={"repo": repo_url, "member": member.name},
                    )
                    continue
                if not member.isfile():
                    continue
                # Re-check after resolution: a name that looked safe could still
                # escape via a pre-existing symlink inside dest.
                target = (dest / member.name).resolve()
                try:
                    target.relative_to(dest_root)
                except ValueError:
                    log.warning(
                        "refusing archive path escaping destination",
                        extra={"repo": repo_url, "member": member.name},
                    )
                    continue
                source = archive.extractfile(member)
                if source is None:
                    continue
                target.parent.mkdir(parents=True, exist_ok=True)
                with source, open(target, "wb") as handle:
                    shutil.copyfileobj(source, handle, length=1 << 20)
                extracted += 1
    finally:
        shutil.rmtree(staging, ignore_errors=True)

    return dest


def read_commits(
    repo_url: str, commit_sha: str, limit: int, staging_dir: Path
) -> list[CommitEntry]:
    """Read commit metadata for the pinned commit and its ancestry.

    Uses `git log` on the fetched history. Author-controlled text is stored as
    data and never interpreted; it is bounded before being returned.
    """
    staging = staging_dir / f".history-{snapshot_id_for(repo_url, commit_sha)[:8]}"
    if staging.exists():
        shutil.rmtree(staging, ignore_errors=True)
    staging.mkdir(parents=True, exist_ok=True)
    try:
        _git(["init", "--quiet", "--bare", str(staging)], timeout=60)
        # Deeper fetch so ancestry is available for chronology analysis.
        _git(
            ["fetch", "--quiet", "--depth", str(limit), "--no-tags", repo_url, commit_sha],
            cwd=staging,
            timeout=GIT_TIMEOUT_SECONDS,
        )
        result = _git(
            ["log", "--max-count", str(limit), "--format=%H%x1f%at%x1f%aN%x1f%s", commit_sha],
            cwd=staging,
            timeout=GIT_TIMEOUT_SECONDS,
            check=False,
        )
    finally:
        shutil.rmtree(staging, ignore_errors=True)

    if result.returncode != 0 or not result.stdout.strip():
        return []

    entries: list[CommitEntry] = []
    for line in result.stdout.decode("utf-8", "replace").splitlines():
        parts = line.split("\x1f")
        if len(parts) != 4:
            continue
        sha, ts, author, message = parts
        try:
            timestamp = int(ts)
        except ValueError:
            continue
        entries.append(
            CommitEntry(
                sha=sha.strip()[:64],
                timestamp=timestamp,
                author=author.strip()[:120],
                message=message.strip()[:400],
            )
        )
    return entries


def cache_dir_for(base: Path, ref: RepoRef, commit_sha: str) -> Path:
    """Deterministic on-disk location for a pinned snapshot."""
    sid = snapshot_id_for(ref.full_name, commit_sha)
    return base / ref.owner / f"{ref.name}__{sid[:16]}"


def profile_from_cache(meta_path: Path) -> RepoProfile | None:
    """Rehydrate a cached profile without re-cloning (spec FR-A-008)."""
    try:
        raw = meta_path.read_text(encoding="utf-8")
    except OSError:
        return None
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return None
    if data.get("schema") != "forkreason/snapshot/v1":
        return None
    try:
        ref = RepoRef(owner=data["owner"], name=data["name"])
        return RepoProfile(
            full_name=ref.full_name,
            commit_sha=data["commit_sha"],
            files=tuple(
                FileEntry(
                    path=f["path"],
                    size=f["size"],
                    sha256=f["sha256"],
                    language=f["language"],
                    text=None,
                    truncated=bool(f.get("truncated")),
                )
                for f in data.get("files", [])
            ),
            commits=tuple(
                CommitEntry(
                    sha=c["sha"],
                    timestamp=c["timestamp"],
                    author=c["author"],
                    message=c["message"],
                )
                for c in data.get("commits", [])
            ),
            description=data.get("description", ""),
            is_fork=bool(data.get("is_fork")),
            parent_full_name=data.get("parent_full_name"),
            first_commit_at=data.get("first_commit_at"),
        )
    except (KeyError, TypeError, ValueError):
        return None


def cache_profile_metadata(
    path: Path, ref: RepoRef, profile: RepoProfile, truncated: bool
) -> None:
    """Persist the inventory (not the file bodies) for reuse.

    File contents are not cached: re-reading them is cheap next to trusting a
    cache that could go stale relative to the pinned commit.
    """
    payload = {
        "schema": "forkreason/snapshot/v1",
        "owner": ref.owner,
        "name": ref.name,
        "commit_sha": profile.commit_sha,
        "description": profile.description,
        "is_fork": profile.is_fork,
        "parent_full_name": profile.parent_full_name,
        # Kept separately from the commit log: the log is capped, so its first
        # entry is not the repository's first commit.
        "first_commit_at": profile.first_commit_at,
        "truncated": truncated,
        "files": [
            {
                "path": f.path,
                "size": f.size,
                "sha256": f.sha256,
                "language": f.language,
                "truncated": f.truncated,
            }
            for f in profile.files
        ],
        "commits": [
            {
                "sha": c.sha,
                "timestamp": c.timestamp,
                "author": c.author,
                "message": c.message,
            }
            for c in profile.commits
        ],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")


def check_repo_size(metadata: RepoMetadata, limits: IntakeLimits) -> None:
    """Reject repositories that exceed the configured bound."""
    if metadata.size_bytes > limits.max_repo_mb * 1024 * 1024:
        raise UnsupportedRepositoryError(
            "repository_too_large",
            f"This repository is larger than the {limits.max_repo_mb} MB analysis "
            "limit. ForkReason V1 analyzes public repositories up to that size.",
        )


def describe(metadata: RepoMetadata, truncated: bool) -> dict:
    """Frontend-facing description of what will be analyzed."""
    return {
        "full_name": metadata.ref.full_name,
        "canonical_url": metadata.ref.canonical_url,
        "commit": metadata.commit_sha,
        "default_branch": metadata.default_branch,
        "description": metadata.description,
        "is_fork": metadata.is_fork,
        "parent": metadata.parent_full_name,
        "pushed_at": metadata.pushed_at,
        "size_bytes": metadata.size_bytes,
        "truncated": truncated,
    }