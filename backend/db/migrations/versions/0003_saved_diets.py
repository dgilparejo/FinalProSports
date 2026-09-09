"""saved_diets: proposals accepted / edited by the professional, stored whole (meals with evidence, notes, validation, parameters) as jsonb (E6)

Revision ID: 0003
Revises: 0002
"""
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS saved_diets (
            id               text NOT NULL,
            professional_id  text NOT NULL REFERENCES professionals(id),
            client_code      text NOT NULL,
            created_at       timestamptz NOT NULL DEFAULT now(),
            goal             text NOT NULL,
            strategy         text NOT NULL,
            edited           boolean NOT NULL DEFAULT false,
            payload          jsonb NOT NULL,
            PRIMARY KEY (professional_id, id),
            FOREIGN KEY (professional_id, client_code) REFERENCES client_profiles(professional_id, client_code)
        )""")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS saved_diets")
