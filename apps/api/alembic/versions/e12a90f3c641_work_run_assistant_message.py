"""associate work runs with assistant messages

Revision ID: e12a90f3c641
Revises: d4f7912ab931
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "e12a90f3c641"
down_revision: Union[str, Sequence[str], None] = "d4f7912ab931"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("work_runs", sa.Column("assistant_message_id", sa.String(length=36), nullable=True))
    op.create_index(op.f("ix_work_runs_assistant_message_id"), "work_runs", ["assistant_message_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_work_runs_assistant_message_id"), table_name="work_runs")
    op.drop_column("work_runs", "assistant_message_id")
