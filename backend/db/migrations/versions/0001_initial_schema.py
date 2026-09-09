"""initial schema: professionals, client_profiles, foods, diets (vector 768), meals, diet_items, rules, archetypes, gaps

Revision ID: 0001
Revises:
"""
from pathlib import Path

from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

SCHEMA_SQL = Path(__file__).resolve().parents[2] / "schema.sql"


def statements(sql: str) -> list[str]:
    """Strip `--` comments FIRST (inline comments may contain ';'), then split on ';'. schema.sql has no '--' inside literals."""
    stripped = "\n".join(line.split("--", 1)[0].rstrip() for line in sql.splitlines())
    return [s.strip() for s in stripped.split(";") if s.strip()]


def upgrade() -> None:
    # The readable schema (db/schema.sql) is the single source of truth: it is executed statement by statement.
    for body in statements(SCHEMA_SQL.read_text(encoding="utf-8")):
        op.execute(body)


def downgrade() -> None:
    for table in ("gaps", "archetypes", "rules", "diet_items", "meals", "diets", "foods", "client_profiles", "professionals"):
        op.execute(f"DROP TABLE IF EXISTS {table} CASCADE")
