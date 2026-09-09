"""S1 — case base vs portfolio: client_profiles.is_corpus_case separates the pseudonymous profiles of the corpus (retrieval
only, never served as clients) from the clients the professional registers in the application. Backfill: every profile that
owns a diet of the case base (or carries the corpus pseudonym pattern) is a corpus case.

Revision ID: 0005
Revises: 0004
"""
from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE client_profiles ADD COLUMN IF NOT EXISTS is_corpus_case boolean NOT NULL DEFAULT false")
    op.execute("""
        UPDATE client_profiles p SET is_corpus_case = true
        WHERE p.client_code ~ '^CLIENTE_[0-9]{3}$'
           OR EXISTS (SELECT 1 FROM diets d WHERE d.professional_id = p.professional_id AND d.client_code = p.client_code)""")


def downgrade() -> None:
    op.execute("ALTER TABLE client_profiles DROP COLUMN IF EXISTS is_corpus_case")
