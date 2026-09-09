"""0014 - client_profiles.corpus_alias: el puente entre la cartera y la base de casos.

La cartera identifica al cliente por UUID (S9) y el corpus por seudonimo `CLIENTE_NNN`. Sin puente entre los dos, la
exclusion obligatoria de `RetrieveSimilarCasesService` -- que mira `client_code` -- no protege a un cliente que ya era
caso del profesional antes de existir la aplicacion: el sistema puede devolverle SU PROPIA dieta como caso de un
tercero. Confirmado con un cliente real, cuyas dos dietas estan en el corpus con J = 1,0000.

La columna la RELLENA el profesional. `data_tools/link_portfolio_to_corpus.py` propone candidatos con un criterio
medido y no escribe nada sin `--apply`, porque el contenido no identifica a una persona en este corpus: hay 19 pares
de dietas identicas entre clientes distintos.

Un caso del corpus nunca tiene alias: es el propio corpus. El CHECK lo impone.
"""
from alembic import op
import sqlalchemy as sa

revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # IF NOT EXISTS: db/schema.sql (que ejecuta la 0001 en una base nueva) ya trae esto; esta migracion
    # existe para las bases creadas ANTES. Sin la guarda, `alembic upgrade head` desde cero falla aqui.
    op.execute("ALTER TABLE client_profiles ADD COLUMN IF NOT EXISTS corpus_alias text")
    # Postgres no tiene ADD CONSTRAINT IF NOT EXISTS: se pregunta al catalogo, que es lo mismo y se lee igual.
    op.execute("""
        DO $$ BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'ck_client_profiles_alias_only_for_portfolio') THEN
                ALTER TABLE client_profiles ADD CONSTRAINT ck_client_profiles_alias_only_for_portfolio
                    CHECK (corpus_alias IS NULL OR NOT is_corpus_case);
            END IF;
        END $$;
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_client_profiles_corpus_alias ON client_profiles (professional_id, corpus_alias)")


def downgrade() -> None:
    op.drop_index("ix_client_profiles_corpus_alias", table_name="client_profiles")
    op.drop_constraint("ck_client_profiles_alias_only_for_portfolio", "client_profiles", type_="check")
    op.drop_column("client_profiles", "corpus_alias")
