"""model mandate configuration (currency, universe, benchmark blend, excess-return goal)

Revision ID: b7c1d2e3f4a5
Revises: 3b7fe3cc4ad2
Create Date: 2026-11-03 11:30:00

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "b7c1d2e3f4a5"
down_revision: Union[str, Sequence[str], None] = "3b7fe3cc4ad2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("model_portfolios") as batch:
        batch.add_column(sa.Column("mandate", sa.JSON(), nullable=False, server_default="{}"))


def downgrade() -> None:
    with op.batch_alter_table("model_portfolios") as batch:
        batch.drop_column("mandate")
