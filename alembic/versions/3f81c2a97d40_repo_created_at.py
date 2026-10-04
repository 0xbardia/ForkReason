"""record the repository's true creation time on each snapshot

Chronology reasoning was reading the earliest timestamp out of the commit log,
which is capped at ANALYSIS_MAX_COMMITS. For any repository with more history
than that, the earliest commit in the window is an arbitrary recent date, not
the repository's beginning. Two repositories compared in one direction could
therefore have their bounded windows appear to run in opposite orders, and the
verdict changed depending only on which repository the user typed first:
`pallets/click` vs `fastapi/typer` came out LIKELY_DERIVED / HIGH in one
direction and INDEPENDENT in the other.

The forge already reports when a repository was created. Recording it separately
from `created_at` (when this row was written) lets direction-sensitive
chronology use a real creation time, and lets the reverse direction record that
the origin came first.

Existing rows stay NULL: their bounded windows cannot be repaired after the
fact, and guessing would reintroduce exactly the bug this fixes. Analyses
against them simply carry no direction claim.

Revision ID: 3f81c2a97d40
Revises: c4e91a7d2b60
Create Date: 2026-10-04 08:40:00.000000
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "3f81c2a97d40"
down_revision: Union[str, None] = "c4e91a7d2b60"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "repository_snapshots",
        sa.Column("repo_created_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("repository_snapshots", "repo_created_at")