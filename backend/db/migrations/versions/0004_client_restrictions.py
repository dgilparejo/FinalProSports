"""client_profiles.restrictions: structured restrictions (RestrictionKind flag names) declared in the registration form (E6)

Revision ID: 0004
Revises: 0003
"""
from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE client_profiles ADD COLUMN IF NOT EXISTS restrictions text[] NOT NULL DEFAULT '{}'")


def downgrade() -> None:
    op.execute("ALTER TABLE client_profiles DROP COLUMN IF EXISTS restrictions")
