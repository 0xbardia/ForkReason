"""store the canonical evidence manifest on each revision

ForkReason's central claim is that a finding is independently checkable: anyone
holding the same two pinned commits must be able to recompute the manifest hash
and confirm nothing changed between analysis and record. The manifest was
computed on every analysis but never persisted, which made the hash an
unfalsifiable assertion rather than a verifiable one.

Also records the pinned origin/target commits on the case row. They were being
written as empty strings, so a case reported which repositories it compared but
not which commits, and the reproducibility claim could not be checked.

Revision ID: c4e91a7d2b60
Revises: 507921d67fb2
Create Date: 2026-10-04 04:10:00.000000
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "c4e91a7d2b60"
down_revision: Union[str, None] = "507921d67fb2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "case_revisions",
        sa.Column("manifest", sa.JSON(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("case_revisions", "manifest")