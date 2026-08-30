"""user enabled plugins

Revision ID: d4f7912ab931
Revises: 247d3b53178e
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "d4f7912ab931"
down_revision: Union[str, Sequence[str], None] = "247d3b53178e"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("user_settings", sa.Column("enabled_plugins", sa.JSON(), nullable=False, server_default="[]"))


def downgrade() -> None:
    op.drop_column("user_settings", "enabled_plugins")
