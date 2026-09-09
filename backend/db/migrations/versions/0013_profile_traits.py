"""dataset-v3 (2026-08-29) — `client_profiles.body_type` y `.training_time`: rasgos que la similitud sí puede usar.

La función de similitud miraba CINCO números (objetivo, edad, sexo, actividad, restricciones) y nada más. Todo lo que
el expediente añadió —báscula, analítica, entrenamientos, gustos— no entraba en la comparación, que es la razón por la
que los veinte vecinos empataban, por la que ponderar por similitud no movía nada y por la que reextraer el corpus
entero no mejoró las propuestas: se enriqueció un expediente que la función de similitud no consulta.

Estas dos columnas son las de mayor cobertura entre las que faltaban: `body_type` (complexión por muñeca) llega al
56,3 % de los clientes con dietas y es el proxy de composición corporal con dato suficiente —el % de grasa US Navy
solo cubre el 18,4 % y el IMC calculable el 8,4 %—, y `training_time` (franja horaria de entrenamiento) al 28,0 %.

Revision ID: 0013
Revises: 0012
"""
from alembic import op
import sqlalchemy as sa

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # IF NOT EXISTS: db/schema.sql (que ejecuta la 0001 en una base nueva) ya trae esto; esta migracion
    # existe para las bases creadas ANTES. Sin la guarda, `alembic upgrade head` desde cero falla aqui.
    op.execute("ALTER TABLE client_profiles ADD COLUMN IF NOT EXISTS body_type text")
    op.execute("ALTER TABLE client_profiles ADD COLUMN IF NOT EXISTS training_time text")


def downgrade() -> None:
    op.drop_column("client_profiles", "training_time")
    op.drop_column("client_profiles", "body_type")
