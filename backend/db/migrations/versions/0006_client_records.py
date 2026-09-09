"""S3 — intake: client_records (the professional's questionnaire, five blocks, one row per portfolio client), body_measurements (scale
import / manual readings) and the algorithm inputs synchronised into client_profiles (disliked_food_ids, owned_supplement_ids).

Revision ID: 0006
Revises: 0005
"""
from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS client_records (
            client_code        text NOT NULL,
            professional_id    text NOT NULL REFERENCES professionals(id),
            full_name          text, birth_date date, phone text, email text,
            first_visit        date, initial_weight_kg numeric(5,1), height_cm smallint, wrist_cm numeric(4,1), waist_cm numeric(5,1), neck_cm numeric(4,1), hip_cm numeric(5,1),
            somatotype         text,
            allergies          text, intolerances text, injuries text, surgeries text,
            liked_foods        text, disliked_foods text, food_vices text, smokes boolean, drinks_alcohol boolean,
            training_years     numeric(4,1), sports text, achievements text, goals_text text, work_schedule text, training_schedule text,
            supplements_owned  text, first_diet_notes text, watch_brand text,
            updated_at         timestamptz NOT NULL DEFAULT now(),
            PRIMARY KEY (professional_id, client_code),
            FOREIGN KEY (professional_id, client_code) REFERENCES client_profiles(professional_id, client_code)
        )""")
    op.execute("""
        CREATE TABLE IF NOT EXISTS body_measurements (
            id               bigserial PRIMARY KEY,
            professional_id  text NOT NULL REFERENCES professionals(id),
            client_code      text NOT NULL,
            measured_at      timestamptz NOT NULL,
            weight_kg        numeric(5,1), height_cm smallint, body_fat_pct numeric(4,1), muscle_pct numeric(4,1), water_pct numeric(4,1), bone_kg numeric(4,1),
            source           text NOT NULL,
            UNIQUE (professional_id, client_code, measured_at, source),
            FOREIGN KEY (professional_id, client_code) REFERENCES client_profiles(professional_id, client_code)
        )""")
    op.execute("ALTER TABLE client_profiles ADD COLUMN IF NOT EXISTS disliked_food_ids integer[] NOT NULL DEFAULT '{}'")
    op.execute("ALTER TABLE client_profiles ADD COLUMN IF NOT EXISTS owned_supplement_ids integer[] NOT NULL DEFAULT '{}'")


def downgrade() -> None:
    op.execute("ALTER TABLE client_profiles DROP COLUMN IF EXISTS owned_supplement_ids")
    op.execute("ALTER TABLE client_profiles DROP COLUMN IF EXISTS disliked_food_ids")
    op.execute("DROP TABLE IF EXISTS body_measurements")
    op.execute("DROP TABLE IF EXISTS client_records")
