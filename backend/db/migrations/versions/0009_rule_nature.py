"""Fase 9 (B) — rules.nature: prescriptive (kept or policy AND followed in the majority of its group, prevalence >= 0.5) or descriptive
(reported and explained, never demanded of a proposal). Decided by pipeline/src/data_tools/build_validated_rules.py and loaded with the
constitution; the plausibility envelope reads Rule.nature instead of re-deriving it from the prevalence.

Revision ID: 0009
Revises: 0008
"""
from alembic import op

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE rules ADD COLUMN IF NOT EXISTS nature text")


def downgrade() -> None:
    op.execute("ALTER TABLE rules DROP COLUMN IF EXISTS nature")
