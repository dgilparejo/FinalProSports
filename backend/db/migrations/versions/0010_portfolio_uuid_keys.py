"""S9 (2026-08-27) — the key of a portfolio client is a UUID assigned by the application; his identity is his name (client_records).

Registering clients by a human-readable code mixed two things: the corpus is pseudonymised (CLIENTE_NNN) because it is a third
party's data used as the case base; the portfolio is the professional's own clients, whom he registers by name as his intake sheet
asks. This migration re-keys every existing portfolio client (only demo / test identities could exist before S9: the application is
delivered empty) to a fresh UUID — profile, saved diets (id, client_code and the payloads that quote the old key), record, measurements
and lab results — and then enforces the key format with a CHECK constraint. Corpus rows are untouched.

The re-keying is not reversible (the old codes are not kept); downgrade only drops the constraint.

Revision ID: 0010
Revises: 0009
"""
from alembic import op

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None

UUID_RE = "^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"
CHILD_TABLES = ("client_records", "body_measurements", "lab_results")


def upgrade() -> None:
    op.execute(f"""
        CREATE TEMP TABLE rekey ON COMMIT DROP AS
        SELECT professional_id, client_code AS old_code, gen_random_uuid()::text AS new_code
        FROM client_profiles WHERE NOT is_corpus_case AND client_code !~* '{UUID_RE}'""")
    op.execute("""
        CREATE TEMP TABLE newp ON COMMIT DROP AS
        SELECT p.* FROM client_profiles p JOIN rekey r ON r.professional_id = p.professional_id AND r.old_code = p.client_code""")
    op.execute("UPDATE newp n SET client_code = r.new_code FROM rekey r WHERE r.professional_id = n.professional_id AND r.old_code = n.client_code")
    op.execute("INSERT INTO client_profiles SELECT * FROM newp")
    for table in CHILD_TABLES:
        op.execute(f"UPDATE {table} t SET client_code = r.new_code FROM rekey r WHERE t.professional_id = r.professional_id AND t.client_code = r.old_code")
    op.execute("""
        UPDATE saved_diets d SET client_code = r.new_code,
                                 id = r.new_code || substr(d.id, length(r.old_code) + 1),
                                 payload = replace(d.payload::text, '"' || r.old_code, '"' || r.new_code)::jsonb,
                                 original_payload = CASE WHEN d.original_payload IS NULL THEN NULL ELSE replace(d.original_payload::text, '"' || r.old_code, '"' || r.new_code)::jsonb END,
                                 diff = CASE WHEN d.diff IS NULL THEN NULL ELSE replace(d.diff::text, '"' || r.old_code, '"' || r.new_code)::jsonb END
        FROM rekey r WHERE d.professional_id = r.professional_id AND d.client_code = r.old_code""")
    op.execute("DELETE FROM client_profiles p USING rekey r WHERE p.professional_id = r.professional_id AND p.client_code = r.old_code")
    # Idempotent on purpose. Revision 0001 executes db/schema.sql, which is the CURRENT schema and already
    # carries this constraint, so on a clean bootstrap (0001 -> ... -> 0010) the plain ADD CONSTRAINT hits
    # "constraint already exists" and every later step fails. That is what broke `make verify-clean-clone`
    # between S9 and the v2 branch: a migration replayed over a schema.sql-built database must not assume
    # the object is missing.
    op.execute("ALTER TABLE client_profiles DROP CONSTRAINT IF EXISTS portfolio_key_is_uuid")
    op.execute(f"ALTER TABLE client_profiles ADD CONSTRAINT portfolio_key_is_uuid CHECK (is_corpus_case OR client_code ~* '{UUID_RE}')")


def downgrade() -> None:
    op.execute("ALTER TABLE client_profiles DROP CONSTRAINT IF EXISTS portfolio_key_is_uuid")
