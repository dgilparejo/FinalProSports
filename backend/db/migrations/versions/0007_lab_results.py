"""S4 — lab_results: markers of an analysis attached to a portfolio client (marker, value, unit, reference range, date). Context for the
professional; never an input of the engine.

Revision ID: 0007
Revises: 0006
"""
from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS lab_results (
            id               bigserial PRIMARY KEY,
            professional_id  text NOT NULL REFERENCES professionals(id),
            client_code      text NOT NULL,
            measured_at      date,
            marker           text NOT NULL,
            value            numeric(12,3) NOT NULL,
            unit             text,
            ref_low          numeric(12,3), ref_high numeric(12,3),
            note             text,
            source           text NOT NULL,
            FOREIGN KEY (professional_id, client_code) REFERENCES client_profiles(professional_id, client_code)
        )""")
    op.execute("CREATE INDEX IF NOT EXISTS lab_results_client_idx ON lab_results (professional_id, client_code, measured_at)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS lab_results")
