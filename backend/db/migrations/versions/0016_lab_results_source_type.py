"""0016 — las analíticas del corpus entran en el motor, y por eso necesitan decir DE DÓNDE salen.

**Cambio de criterio, deliberado, y conviene que quede escrito aquí y no solo en un informe.** La 0007 creó esta tabla
diciendo «context for the professional, **never an engine input**». Se retira esa restricción. El objetivo del trabajo
es reproducir a ESTE profesional, y él mira esas mediciones antes de escribir: excluirlas hace el sistema menos
parecido a él, que es lo contrario de lo que se persigue. La postura es **no validamos el instrumento, modelamos al
profesional que lo usa**, y por eso hace falta `source_type`: para que nadie pueda comparar un índice de dispositivo
con una magnitud de laboratorio creyendo que son la misma cosa.

Qué entra: **18.177 valores de 254 informes de 155 clientes**, en cuatro espacios de nombres —`bioanalyzer` (217
informes, 189 parámetros, 106 de ellos con 30 clientes o más), `clinical` (31), `sports_physiology` (3) y
`nutrigenetic` (3)—. La analítica de laboratorio convencional cubre **1 de las 815 consultas**; el volumen es el
dispositivo.

`report_date` puede ser NULO y eso NO es un defecto que rellenar: 56 informes no llevan fecha en su nombre de fichero,
y sin fecha **no se pueden usar**, porque la regla temporal es la misma que la de la báscula (0015): para una dieta
solo cuentan las mediciones ANTERIORES a ella, la más reciente disponible. Un valor sin fecha no se puede afirmar que
precediera, así que queda guardado y fuera del motor.

`values_unreliable` marca los 22 informes de laboratorio cuyas columnas el PDF extrae desordenadas: se conservan —el
titular pidió no descartar nada— y ningún consumidor los usa.

RESTRICCIÓN QUE NO SE NEGOCIA, y tiene su propio test (`tests/architecture/test_labs_never_reach_the_client.py`):
estos valores pueden alimentar la recuperación y verse en la ficha del cliente, pero **no pueden aparecer en el
documento que recibe el cliente ni justificar en él ninguna recomendación**, tampoco en el panel de explicabilidad
como razón de un alimento.

Revision ID: 0016
Revises: 0015
"""
from alembic import op
import sqlalchemy as sa

revision = "0016"
down_revision = "0015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # IF NOT EXISTS: db/schema.sql (que ejecuta la 0001 en una base nueva) ya trae esto; esta migracion
    # existe para las bases creadas ANTES. Sin la guarda, `alembic upgrade head` desde cero falla aqui.
    op.execute("ALTER TABLE lab_results ADD COLUMN IF NOT EXISTS source_type text NOT NULL DEFAULT 'manual'")
    op.execute("ALTER TABLE lab_results ADD COLUMN IF NOT EXISTS report_sha1 text")
    op.execute("ALTER TABLE lab_results ADD COLUMN IF NOT EXISTS values_unreliable boolean NOT NULL DEFAULT false")
    op.execute("CREATE INDEX IF NOT EXISTS lab_results_source_idx ON lab_results (professional_id, source_type)")
    # El indice que sirve la regla temporal: por cliente y fecha descendente, que es como se pregunta siempre
    # («la mas reciente ANTERIOR a esta fecha»).
    op.execute("CREATE INDEX IF NOT EXISTS lab_results_asof_idx ON lab_results (professional_id, client_code, measured_at)")


def downgrade() -> None:
    op.drop_index("lab_results_asof_idx", table_name="lab_results")
    op.drop_index("lab_results_source_idx", table_name="lab_results")
    op.drop_column("lab_results", "values_unreliable")
    op.drop_column("lab_results", "report_sha1")
    op.drop_column("lab_results", "source_type")
