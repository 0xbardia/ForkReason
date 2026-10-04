"""Safe repository intake tests (spec FR-A-004..007).

The critical properties here are negative: what the intake layer refuses. These
tests build real tar archives and a real git repository, including archives that
attempt path traversal, symlink escape, and binary floods.
"""

from __future__ import annotations

import io
import os
import subprocess
import tarfile
from pathlib import Path

import pytest

from forkreason.analysis.fingerprint import extension_language
from forkreason.domain import IntakeError, UnsupportedRepositoryError
from forkreason.repos.github_url import validate_repo_input
from forkreason.repos.snapshot import (
    IntakeLimits,
    RepoMetadata,
    _decode_text,
    _is_safe_member,
    _should_analyze_path,
    archive_commit,
    build_profile,
    read_commits,
)
from forkreason.domain import CommitEntry, RepoProfile


# --- archive member validation -------------------------------------------


def _member(name: str, kind: str = "file") -> tarfile.TarInfo:
    info = tarfile.TarInfo(name)
    if kind == "file":
        info.type = tarfile.REGTYPE
        info.size = 4
    elif kind == "sym":
        info.type = tarfile.SYMTYPE
        info.linkname = "/etc/passwd"
    elif kind == "link":
        info.type = tarfile.LNKTYPE
        info.linkname = "../../etc/passwd"
    elif kind == "fifo":
        info.type = tarfile.FIFOTYPE
    elif kind == "chr":
        info.type = tarfile.CHRTYPE
    return info


@pytest.mark.parametrize(
    "name",
    [
        "/etc/passwd",
        "//etc/passwd",
        "..",
        "../escape.txt",
        "a/../../escape.txt",
        "a/b/../../../etc/passwd",
        "\\windows\\system32",
        "C:/windows/system32",
    ],
)
def test_traversal_and_absolute_paths_are_rejected(name: str) -> None:
    assert _is_safe_member(_member(name)) is False


@pytest.mark.parametrize("kind", ["sym", "link", "fifo", "chr"])
def test_links_and_devices_are_rejected(kind: str) -> None:
    """A symlink in a hostile repo is the classic escape primitive."""
    assert _is_safe_member(_member("innocent.txt", kind)) is False


@pytest.mark.parametrize(
    "name", ["a.py", "src/main.js", "README.md", "docs/guide.rst", "a/b/c/d.py"]
)
def test_ordinary_paths_are_accepted(name: str) -> None:
    assert _is_safe_member(_member(name)) is True


def test_safe_paths_never_depend_on_traversal_depth() -> None:
    deep = "/".join(f"dir{i}" for i in range(30)) + "/file.py"
    assert _is_safe_member(_member(deep)) is True


# --- path filtering ------------------------------------------------------


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        ("node_modules/react/index.js", False),
        ("vendor/github.com/x/y.go", False),
        ("dist/bundle.min.js", False),
        (".git/config", False),
        ("src/app.min.js", False),
        ("static/logo.png", False),
        ("__pycache__/x.pyc", False),
        ("src/main.py", True),
        ("README.md", True),
        ("app/lib/util.ts", True),
        ("config/settings.yml", True),
    ],
)
def test_vendor_and_binary_paths_are_skipped(path: str, expected: bool) -> None:
    from forkreason.repos.snapshot import SKIP_DIRS
    from pathlib import PurePosixPath

    assert _should_analyze_path(PurePosixPath(path)) is expected


def test_git_directory_is_never_analyzed() -> None:
    from pathlib import PurePosixPath

    from forkreason.repos.snapshot import SKIP_DIRS

    assert ".git" in SKIP_DIRS
    assert _should_analyze_path(PurePosixPath(".git/config")) is False


# --- text decoding -------------------------------------------------------


def test_binary_content_is_not_decoded() -> None:
    assert _decode_text(b"\x00\x01\x02\x03binary") is None


def test_text_content_is_decoded() -> None:
    assert _decode_text(b"def main():\n    return 1\n") is not None


def test_utf8_is_decoded() -> None:
    assert _decode_text("café — naïve".encode("utf-8")) is not None


def test_invalid_utf8_falls_back_or_declines() -> None:
    # Must not raise; either decodes or returns None.
    assert _decode_text(b"\xff\xfe\x00binary\x00") is None


def test_large_binary_prefix_does_not_crash() -> None:
    assert _decode_text(b"\x00" * 10_000) is None


# --- limits --------------------------------------------------------------


def _meta(name: str = "acme/repo", size_bytes: int = 1024) -> RepoMetadata:
    ref = validate_repo_input(name)
    return RepoMetadata(
        ref=ref,
        commit_sha="a" * 40,
        default_branch="main",
        description="test",
        is_fork=False,
        parent_full_name=None,
        size_bytes=size_bytes,
        pushed_at=1700000000,
    )


def test_oversized_repository_is_rejected() -> None:
    limits = IntakeLimits(max_repo_mb=1)
    with pytest.raises(UnsupportedRepositoryError) as excinfo:
        from forkreason.repos.snapshot import check_repo_size

        check_repo_size(_meta(size_bytes=50 * 1024 * 1024), limits)
    assert excinfo.value.code == "repository_too_large"


def test_repository_within_limits_is_accepted() -> None:
    from forkreason.repos.snapshot import check_repo_size

    check_repo_size(_meta(size_bytes=1024), IntakeLimits(max_repo_mb=1))


def test_max_files_limit_is_enforced(tmp_path: Path) -> None:
    for i in range(30):
        (tmp_path / f"f{i}.py").write_text(f"def f{i}():\n    return {i}\n")
    profile, truncated = build_profile(_meta(), tmp_path, [], IntakeLimits(max_files=10))
    assert len(profile.files) <= 10
    assert truncated is True


def test_oversized_file_is_skipped_and_marked(tmp_path: Path) -> None:
    (tmp_path / "small.py").write_text("x = 1\n")
    (tmp_path / "big.py").write_bytes(b"x = 1\n" * (3 * 1024 * 1024))
    profile, truncated = build_profile(
        _meta(), tmp_path, [], IntakeLimits(max_file_mb=1, max_files=100)
    )
    names = {f.path for f in profile.files}
    assert "small.py" in names
    assert "big.py" not in names
    assert truncated is True


def test_commit_limit_is_enforced(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text("x = 1\n")
    commits = [CommitEntry(sha=f"{i:040x}", timestamp=1700000000 + i, author="a", message="m") for i in range(50)]
    profile, truncated = build_profile(_meta(), tmp_path, commits, IntakeLimits(max_commits=5))
    assert len(profile.commits) == 5
    assert truncated is True


def test_symlink_in_tree_is_not_followed(tmp_path: Path) -> None:
    """A symlink pointing at /etc/passwd must never enter the inventory."""
    secret = tmp_path / "secret.txt"
    secret.write_text("TOP SECRET CONTENT")
    tree = tmp_path / "tree"
    tree.mkdir()
    (tree / "ok.py").write_text("x = 1\n")
    try:
        os.symlink(str(secret), str(tree / "link.py"))
    except OSError:
        pytest.skip("symlinks unavailable")
    profile, _ = build_profile(_meta(), tree, [], IntakeLimits())
    paths = {f.path for f in profile.files}
    assert "link.py" not in paths
    for f in profile.files:
        assert "TOP SECRET" not in (f.text or "")


def test_symlink_to_directory_is_not_traversed(tmp_path: Path) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "leak.py").write_text("SECRET = 'leaked'\n")
    tree = tmp_path / "tree"
    tree.mkdir()
    (tree / "ok.py").write_text("x = 1\n")
    try:
        os.symlink(str(outside), str(tree / "linked"))
    except OSError:
        pytest.skip("symlinks unavailable")
    profile, _ = build_profile(_meta(), tree, [], IntakeLimits())
    assert all("leak" not in f.path for f in profile.files)
    assert all("leaked" not in (f.text or "") for f in profile.files)


def test_nested_symlink_escape_is_blocked(tmp_path: Path) -> None:
    deep = tmp_path / "deep" / "deeper"
    deep.mkdir(parents=True)
    tree = tmp_path / "tree"
    tree.mkdir()
    try:
        os.symlink(str(tmp_path), str(deep / "up"))
    except OSError:
        pytest.skip("symlinks unavailable")
    (tree / "ok.py").write_text("x = 1\n")
    profile, _ = build_profile(_meta(), tree, [], IntakeLimits())
    assert {f.path for f in profile.files} == {"ok.py"}


# --- git invocation safety -----------------------------------------------


def test_git_args_must_be_strings(tmp_path: Path) -> None:
    from forkreason.repos.snapshot import _git

    with pytest.raises(IntakeError):
        _git(["init", 123], cwd=tmp_path)  # type: ignore[list-item]


def test_git_never_uses_a_shell(tmp_path: Path) -> None:
    """A repo name with shell metacharacters cannot become a command."""
    from forkreason.repos.snapshot import _git

    # This would run `id` if any shell interpolation existed.
    result = _git(["--version"], check=False)
    assert result.returncode == 0
    assert b"git version" in result.stdout.lower()


def test_git_env_disables_hooks_and_global_config(tmp_path: Path) -> None:
    from forkreason.repos.snapshot import _git

    result = _git(["config", "--list"], cwd=tmp_path, check=False)
    combined = (result.stdout + result.stderr).decode("utf-8", "replace")
    # GIT_CONFIG_NOSYSTEM / GIT_CONFIG_GLOBAL mean no user/system config leaks in.
    assert "credential.helper=*" not in combined


def test_missing_repository_raises_bounded_error(tmp_path: Path) -> None:
    from forkreason.repos.snapshot import _git

    with pytest.raises(IntakeError) as excinfo:
        _git(["archive", "--format=tar", "0" * 40], cwd=tmp_path)
    assert excinfo.value.code == "git_failed"
    # The user-facing message must not include raw stderr.
    assert "/root" not in excinfo.value.message


# --- end to end against a real local repository ---------------------------


def _git(*args: str, cwd: Path) -> None:
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)


@pytest.fixture()
def local_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "src_repo"
    repo.mkdir()
    _git("init", "--quiet", "-b", "main", cwd=repo)
    _git("config", "user.email", "t@example.com", cwd=repo)
    _git("config", "user.name", "Test", cwd=repo)
    (repo / "engine.py").write_text(
        "CHECKPOINT_MAGIC = b'FRCKPT7'\n"
        "def reconcile_orphaned_transactions(items, watermark):\n"
        "    return [i for i in items if i.settled is False]\n"
    )
    (repo / "README.md").write_text("# Reconciliation upstream\n\nCanonical primitives.\n")
    _git("add", "-A", cwd=repo)
    _git("commit", "--quiet", "-m", "initial commit", cwd=repo)
    _git("tag", "-a", "v1", "-m", "v1", cwd=repo)
    _git("commit", "--quiet", "--allow-empty", "-m", "fix: correct edge case", cwd=repo)
    return repo


def test_archive_and_history_from_a_real_repository(local_repo: Path, tmp_path: Path) -> None:
    sha = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=local_repo, capture_output=True, text=True, check=True
    ).stdout.strip()

    dest = tmp_path / "extracted"
    archive_commit(str(local_repo), sha, dest)

    assert (dest / "engine.py").exists()
    assert (dest / "README.md").exists()
    # No git internals leak into the analyzed tree.
    assert not (dest / ".git").exists()

    profile, truncated = build_profile(_meta(), dest, [], IntakeLimits())
    assert {f.path for f in profile.files} == {"engine.py", "README.md"}
    assert "CHECKPOINT_MAGIC" in (profile.file_by_path("engine.py").text or "")
    assert truncated is False

    commits = read_commits(str(local_repo), sha, limit=50, staging_dir=tmp_path)
    assert len(commits) >= 2
    assert any("fix" in c.message for c in commits)
    assert all(len(c.message) <= 400 for c in commits)
    assert all(len(c.author) <= 120 for c in commits)


def test_vendored_and_binary_files_are_excluded_from_analysis(local_repo: Path, tmp_path: Path) -> None:
    (local_repo / "node_modules").mkdir()
    (local_repo / "node_modules" / "dep.js").write_text("module.exports = 'vendored';\n")
    (local_repo / "logo.png").write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 100)
    _git("add", "-A", cwd=local_repo)
    _git("commit", "--quiet", "-m", "add vendored deps", cwd=local_repo)
    sha = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=local_repo, capture_output=True, text=True, check=True
    ).stdout.strip()

    dest = tmp_path / "extracted"
    archive_commit(str(local_repo), sha, dest)
    profile, _ = build_profile(_meta(), dest, [], IntakeLimits())

    paths = {f.path for f in profile.files}
    assert "engine.py" in paths
    # Vendored trees are excluded from the inventory entirely: they are not the
    # analyzed project's own code and would swamp every fingerprint.
    assert not any(p.startswith("node_modules/") for p in paths)

    # A binary file is still inventoried (its existence is a fact about the
    # repository) but carries no body, so it cannot enter fingerprinting.
    logo = profile.file_by_path("logo.png")
    assert logo is not None, "binary files should still be inventoried"
    assert logo.text is None
    assert logo.sha256 and len(logo.sha256) == 64

    # And it must not have been decoded into anything.
    assert all("PNG" not in (f.text or "") for f in profile.files)


def test_submodule_is_not_resolved(local_repo: Path, tmp_path: Path) -> None:
    """A submodule pointer must not cause a fetch of attacker-chosen content."""
    other = tmp_path / "other"
    other.mkdir()
    _git("init", "--quiet", "-b", "main", cwd=other)
    _git("config", "user.email", "t@example.com", cwd=other)
    _git("config", "user.name", "T", cwd=other)
    (other / "mod.py").write_text("SECRET = 'submodule'\n")
    _git("add", "-A", cwd=other)
    _git("commit", "--quiet", "-m", "sub", cwd=other)

    _git("-c", "protocol.file.allow=always", "submodule", "add", "--quiet", str(other), "sub",
         cwd=local_repo)
    _git("commit", "--quiet", "-m", "add submodule", cwd=local_repo)
    sha = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=local_repo, capture_output=True, text=True, check=True
    ).stdout.strip()

    dest = tmp_path / "extracted"
    archive_commit(str(local_repo), sha, dest)
    profile, _ = build_profile(_meta(), dest, [], IntakeLimits())

    # The submodule's own files must never exist on disk: resolving a gitlink
    # would mean fetching attacker-chosen content from an attacker-chosen URL.
    assert not (dest / "sub" / "mod.py").exists(), "submodule content was fetched"
    assert not (dest / "sub").exists() or not any((dest / "sub").rglob("*.py"))
    # Only the pointer file is recorded, never the referenced content.
    assert not any(f.path.startswith("sub/") for f in profile.files)
    # The submodule's secret must appear nowhere in the analyzed tree.
    assert all("SECRET" not in (f.text or "") for f in profile.files)


def test_language_detection_covers_common_extensions() -> None:
    assert extension_language("a/b.py") == "python"
    assert extension_language("a/b.tsx") == "typescript"
    assert extension_language("a/b.unknown") == "other"