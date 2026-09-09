"""diets.retrieval_text: structured text (goal + profile header, canonical foods per slot, informative notes) that is vectorised (E3.1)

Revision ID: 0002
Revises: 0001
"""
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # IF NOT EXISTS: db/schema.sql (executed by 0001 on fresh databases) already carries the column; this migration upgrades databases created before it.
    op.execute("ALTER TABLE diets ADD COLUMN IF NOT EXISTS retrieval_text text")


def downgrade() -> None:
    op.execute("ALTER TABLE diets DROP COLUMN IF EXISTS retrieval_text")
