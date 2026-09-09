"""S5 — editable diets and professional-added foods: saved_diets keeps the ORIGINAL proposal and the diff against what the professional saved
(traceability of his criterion, evaluation material); foods.created_by_professional tells the mined catalogue from the hand-added one.

Revision ID: 0008
Revises: 0007
"""
from alembic import op

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE saved_diets ADD COLUMN IF NOT EXISTS original_payload jsonb")
    op.execute("ALTER TABLE saved_diets ADD COLUMN IF NOT EXISTS diff jsonb")
    op.execute("ALTER TABLE foods ADD COLUMN IF NOT EXISTS created_by_professional boolean NOT NULL DEFAULT false")


def downgrade() -> None:
    op.execute("ALTER TABLE foods DROP COLUMN IF EXISTS created_by_professional")
    op.execute("ALTER TABLE saved_diets DROP COLUMN IF EXISTS diff")
    op.execute("ALTER TABLE saved_diets DROP COLUMN IF EXISTS original_payload")
