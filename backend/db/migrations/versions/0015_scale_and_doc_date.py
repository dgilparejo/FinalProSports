"""0015 — la báscula entra en el motor, y las dietas ganan su fecha.

Dos huecos que se descubrieron juntos, porque el segundo es condición del primero.

**`diets.doc_date`.** El corpus lleva la fecha del documento en `diets.jsonl` desde la reextracción, y la base de datos
no la tenía. Sin ella no se puede aplicar la única regla que hace utilizable una medida longitudinal: la lectura válida
de una dieta es la más reciente ANTERIOR a su fecha. Una báscula de 2023 no explica una dieta de 2019, y en un corpus
donde el mismo cliente reaparece a lo largo de diez años esa fuga no es teórica.

**Las cinco columnas nuevas de `body_measurements`.** La tabla se diseñó en S3 para la importación manual del expediente
y solo guardaba peso, altura, grasa, músculo (como porcentaje), agua y hueso. La exportación de la báscula trae cuatro
magnitudes más que el profesional sí registra —valoración física, grasa visceral, edad metabólica y metabolismo basal—
y da el músculo en KILOS, no en porcentaje, así que `muscle_pct` no podía recibirlo sin inventar una conversión.

La corrección de un dato del proyecto que estaba mal escrito: la 0013 justificó `body_type` diciendo que era «el proxy
de composición corporal con dato suficiente» porque el % de grasa US Navy cubría el 18,4 % y el IMC calculable el 8,4 %.
Esas dos cifras salen de los campos del CUESTIONARIO (cintura, cuello, muñeca), no de la báscula, y la conclusión que se
sacó de ellas es falsa: la báscula da composición corporal MEDIDA en 1.338 lecturas de 171 clientes, y con la regla
temporal aplicada cubre 617 de las 815 consultas del arnés (75,7 %), con una antigüedad mediana de 13 días. No es un
proxy y no es escaso.

El comentario de la tabla decía «weight never reaches retrieval». Deja de ser cierto con esta migración, y se cambia.

Revision ID: 0015
Revises: 0014
"""
from alembic import op
import sqlalchemy as sa

revision = "0015"
down_revision = "0014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # IF NOT EXISTS: db/schema.sql (que ejecuta la 0001 en una base nueva) ya trae esto; esta migracion
    # existe para las bases creadas ANTES. Sin la guarda, `alembic upgrade head` desde cero falla aqui.
    op.execute("ALTER TABLE diets ADD COLUMN IF NOT EXISTS doc_date date")
    op.execute("CREATE INDEX IF NOT EXISTS ix_diets_professional_doc_date ON diets (professional_id, doc_date)")
    for columna, tipo in (("muscle_mass_kg", "numeric(5,1)"), ("physique_rating", "smallint"),
                          ("visceral_fat_rating", "numeric(4,1)"), ("metabolic_age", "smallint"),
                          ("basal_met_kcal", "integer")):
        op.execute(f"ALTER TABLE body_measurements ADD COLUMN IF NOT EXISTS {columna} {tipo}")


def downgrade() -> None:
    op.drop_column("body_measurements", "basal_met_kcal")
    op.drop_column("body_measurements", "metabolic_age")
    op.drop_column("body_measurements", "visceral_fat_rating")
    op.drop_column("body_measurements", "physique_rating")
    op.drop_column("body_measurements", "muscle_mass_kg")
    op.drop_index("ix_diets_professional_doc_date", table_name="diets")
    op.drop_column("diets", "doc_date")
