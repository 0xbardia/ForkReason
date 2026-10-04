"""Test path setup.

`forkreason` must be importable as a single module object. If the package is
reachable under two different paths, `InvalidRepositoryInput` and its
registered API handler become two distinct classes, and exception mapping
silently stops working — which is exactly the kind of failure that looks like a
missing handler rather than a duplicated import.

The path is therefore inserted once, and only if absent.
"""

import pathlib
import sys

PACKAGE_ROOT = pathlib.Path(__file__).resolve().parents[1]  # -> apps/api

if str(PACKAGE_ROOT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_ROOT))

# Repository root, needed for `contracts/` and `alembic/` paths.
REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]