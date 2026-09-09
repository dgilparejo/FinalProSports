"""0017 - `client_profiles.liked_food_ids`: los gustos POSITIVOS, que se extraian y no se usaban en ningun sitio.

La columna hermana `disliked_food_ids` existe desde S3 y alimenta las exclusiones blandas del validador. La positiva
no existia: el cuestionario preguntaba «que alimentos te gustan», el ETL lo guardaba como texto y ahi se quedaba.

Entra porque esta MEDIDO que el los tiene en cuenta al escribir (`eval.food_preferences`): los alimentos que un
cliente declara aparecen en sus dietas **+0,0643 [+0,0120, +0,1211]** por encima de la tasa base de ese mismo alimento
en el mismo objetivo, sobre 169 pares de 61 clientes. Y el control negativo sale donde tiene que salir -- los que el
cliente rechaza aparecen **-0,0612 [-0,1093, -0,0110]** por debajo --, asi que la mitad positiva es fiable.

Cobertura: 61 de los 261 clientes con dietas (23,4 %), 2,8 alimentos resueltos de media. Es una senal real sobre una
porcion pequena, y asi hay que leerla.

Lo que la columna NO habilita: proponer un alimento porque el cliente lo escribio. Solo desempata entre candidatos que
YA vienen de los casos recuperados (`composition_policy.compose_meals`), y lo impone
`tests/domain/test_likes_never_introduce_a_food.py`.

Revision ID: 0017
Revises: 0016
"""
from alembic import op
import sqlalchemy as sa

revision = "0017"
down_revision = "0016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # IF NOT EXISTS: db/schema.sql (que ejecuta la 0001 en una base nueva) ya trae esto; esta migracion
    # existe para las bases creadas ANTES. Sin la guarda, `alembic upgrade head` desde cero falla aqui.
    op.execute("ALTER TABLE client_profiles ADD COLUMN IF NOT EXISTS liked_food_ids integer[]")


def downgrade() -> None:
    op.drop_column("client_profiles", "liked_food_ids")
