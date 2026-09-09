"""v2 (2026-08-28) — `professionals.keycloak_subject`: the identity provider's subject that owns each professional.

The professional stops being a configured constant and becomes whoever the validated token says. The link is the OIDC
`sub`, stored here and looked up on every request (ProfessionalDirectoryAdapter). It is UNIQUE: two professionals cannot
share a subject, and a subject that maps to nothing gets a 403, never a default professional.

The value for the test user is NOT invented: the realm is a versioned export (`keycloak/realm-fps.json`) where the user
carries an explicit `id`, so the subject is fixed and reproducible in any clean clone.
`tests/architecture/test_keycloak_subject_matches_the_realm.py` fails if the two ever drift apart.

Revision ID: 0011
Revises: 0010
"""
from alembic import op

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None

# keycloak/realm-fps.json -> users[username == "entrenador"].id
TEST_TRAINER_SUBJECT = "11111111-1111-4111-8111-111111111111"


def upgrade() -> None:
    op.execute("ALTER TABLE professionals ADD COLUMN IF NOT EXISTS keycloak_subject text")
    op.execute("CREATE UNIQUE INDEX IF NOT EXISTS professionals_keycloak_subject_key ON professionals (keycloak_subject)")

    # Single-tenant installation: the one professional already in the table is the realm's test trainer.
    # Only fills a subject that is still empty, so re-running never re-points a mapping someone set by hand.
    #
    # On a CLEAN bootstrap this updates nothing, and that is correct: migrations run before any data is
    # loaded, so `professionals` is still empty here. The row — and its mapping — is created by
    # pipeline/load_postgres.py, which owns it. This UPDATE is the upgrade path for a database that
    # already had a professional before the column existed.
    op.execute(f"""
        UPDATE professionals SET keycloak_subject = '{TEST_TRAINER_SUBJECT}'
         WHERE keycloak_subject IS NULL
           AND id = (SELECT id FROM professionals ORDER BY created_at, id LIMIT 1)
    """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS professionals_keycloak_subject_key")
    op.execute("ALTER TABLE professionals DROP COLUMN IF EXISTS keycloak_subject")
