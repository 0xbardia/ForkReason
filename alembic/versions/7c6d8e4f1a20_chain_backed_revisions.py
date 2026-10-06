"""Separate provisional analysis from the first accepted chain revision.

Revision ID: 7c6d8e4f1a20
Revises: 3f81c2a97d40
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "7c6d8e4f1a20"
down_revision: Union[str, None] = "3f81c2a97d40"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("challenges", sa.Column("evidence_digest", sa.Text(), nullable=True))
    connection = op.get_bind()
    case_ids = connection.execute(
        sa.text(
            """SELECT c.id FROM cases c
               JOIN case_revisions r ON r.case_id = c.id AND r.revision_number = 1
               WHERE c.current_revision = 1 AND c.lifecycle = 'resolved'
                 AND r.tx_hash IS NULL
                 AND NOT EXISTS (SELECT 1 FROM challenges h WHERE h.case_id = c.id)
                 AND NOT EXISTS (SELECT 1 FROM chain_transactions t WHERE t.case_id = c.id)"""
        )
    ).scalars().all()
    for case_id in case_ids:
        connection.execute(
            sa.text("UPDATE case_revisions SET revision_number = 0, id = :new_id WHERE case_id = :case_id AND revision_number = 1"),
            {"new_id": f"{case_id}-0", "case_id": case_id},
        )
        connection.execute(
            sa.text("UPDATE evidence_items SET revision_number = 0 WHERE case_id = :case_id AND revision_number = 1"),
            {"case_id": case_id},
        )
        connection.execute(
            sa.text("UPDATE alternative_explanations SET revision_number = 0, id = replace(id, :old_suffix, :new_suffix) WHERE case_id = :case_id AND revision_number = 1"),
            {"old_suffix": "-1-", "new_suffix": "-0-", "case_id": case_id},
        )
        connection.execute(
            sa.text("UPDATE cases SET current_revision = 0, lifecycle = 'analysis_ready' WHERE id = :case_id"),
            {"case_id": case_id},
        )


def downgrade() -> None:
    connection = op.get_bind()
    case_ids = connection.execute(
        sa.text(
            """SELECT c.id FROM cases c
               JOIN case_revisions r ON r.case_id = c.id AND r.revision_number = 0
               WHERE c.current_revision = 0 AND c.lifecycle = 'analysis_ready'
                 AND r.tx_hash IS NULL
                 AND NOT EXISTS (SELECT 1 FROM case_revisions old WHERE old.case_id = c.id AND old.revision_number = 1)
                 AND NOT EXISTS (SELECT 1 FROM challenges h WHERE h.case_id = c.id)
                 AND NOT EXISTS (SELECT 1 FROM chain_transactions t WHERE t.case_id = c.id)"""
        )
    ).scalars().all()
    for case_id in case_ids:
        connection.execute(
            sa.text("UPDATE case_revisions SET revision_number = 1, id = :new_id WHERE case_id = :case_id AND revision_number = 0"),
            {"new_id": f"{case_id}-1", "case_id": case_id},
        )
        connection.execute(
            sa.text("UPDATE evidence_items SET revision_number = 1 WHERE case_id = :case_id AND revision_number = 0"),
            {"case_id": case_id},
        )
        connection.execute(
            sa.text("UPDATE alternative_explanations SET revision_number = 1, id = replace(id, :old_suffix, :new_suffix) WHERE case_id = :case_id AND revision_number = 0"),
            {"old_suffix": "-0-", "new_suffix": "-1-", "case_id": case_id},
        )
        connection.execute(
            sa.text("UPDATE cases SET current_revision = 1, lifecycle = 'resolved' WHERE id = :case_id"),
            {"case_id": case_id},
        )
    op.drop_column("challenges", "evidence_digest")
