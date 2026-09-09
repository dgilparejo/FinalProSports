"""dataset-v3 (2026-08-29) — `diets.method` / `diets.methods`: the structural regime, apart from the goal.

"Ayuno intermitente para perder grasa" declares two different things. The PURPOSE (fat loss) is what makes two cases
comparable — two clients fasting, one to lose fat and one to gain mass, are not each other's neighbour. The METHOD
(time-restricted eating, ketogenic macros, carbohydrate cycling) is what determines the SHAPE of the plan: which slots
exist at all, whether carbohydrates appear at dinner.

dataset-v2 read the method into `goal` and lost the purpose; the first v3 build read the purpose and lost the method.
Neither field can evict the other, so the method gets a column of its own. `goal` and `goals` are UNTOUCHED: no label is
rewritten, a field is added.

What it cost to have it collapsed: the conditional rules whose antecedent is a regime lost two thirds of their group
(`sin_hidratos_cena` 300 -> 98 diets) and were retired for insufficient support, which in turn left ONE conditional rule
with a measurable antecedent and made the conditional-compliance metric read a meaningless 1,000.

Revision ID: 0012
Revises: 0011
"""
from alembic import op
import sqlalchemy as sa

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # IF NOT EXISTS: db/schema.sql (que ejecuta la 0001 en una base nueva) ya trae esto; esta migracion
    # existe para las bases creadas ANTES. Sin la guarda, `alembic upgrade head` desde cero falla aqui.
    # Nullable on purpose: most diets declare no regime at all, and "no method" is a fact about the diet, not a gap.
    op.execute("ALTER TABLE diets ADD COLUMN IF NOT EXISTS method text")
    op.execute("ALTER TABLE diets ADD COLUMN IF NOT EXISTS methods text[] NOT NULL DEFAULT '{}'")
    op.execute("CREATE INDEX IF NOT EXISTS ix_diets_professional_method ON diets (professional_id, method)")


def downgrade() -> None:
    op.drop_index("ix_diets_professional_method", table_name="diets")
    op.drop_column("diets", "methods")
    op.drop_column("diets", "method")
