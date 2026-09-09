# -*- coding: utf-8 -*-
"""Las migraciones tienen que poder correr sobre una base de datos VACÍA, no solo sobre la tuya.

El diseño de este proyecto es que `db/schema.sql` es la fuente de verdad legible y la ejecuta la migración **0001**.
Consecuencia directa, y es la que se olvida: en una base NUEVA la 0001 ya crea la forma moderna del esquema — con
`diets.method`, `client_profiles.body_type`, `lab_results.source_type`… — y **todas las migraciones posteriores se
encuentran hecho lo que venían a hacer**. Si una de ellas dice `ALTER TABLE ... ADD COLUMN` a secas, Postgres
responde `DuplicateColumn` y `alembic upgrade head` **falla desde cero**.

No es hipotético: pasó. Las 0002–0011 llevaban la guarda `IF NOT EXISTS` con el motivo escrito, y las **0012–0017 se
escribieron sin ella**. Es un fallo invisible en desarrollo, porque toda base existente se ha migrado paso a paso y
nunca vuelve a ejecutar la 0001 sobre vacío; aparece solo al levantar la aplicación entera sobre un volumen nuevo,
que es justo lo que hará quien clone el repositorio.

Este test lee las migraciones con `ast` — sin base de datos, sin Alembic, sin dependencias — y exige que ninguna
posterior a la 0001 use DDL sin guarda. La 0001 queda fuera a propósito: es la que crea el esquema y no tiene nada
contra lo que protegerse.

Lo que NO comprueba: que el SQL sea correcto. Para eso está `make verify-clean-clone`, y ahora también
`docker compose up` sobre un volumen nuevo, que es la prueba de verdad.
"""
import ast
import sys
from pathlib import Path

VERSIONS = Path(__file__).resolve().parents[2] / "db" / "migrations" / "versions"

# Constructores de Alembic que fallan si el objeto ya existe. Cada uno con la forma guardada que sí sirve.
SIN_GUARDA = {
    "add_column": "op.execute(\"ALTER TABLE t ADD COLUMN IF NOT EXISTS c tipo\")",
    "create_index": "op.execute(\"CREATE INDEX IF NOT EXISTS i ON t (c)\")",
    "create_table": "op.execute(\"CREATE TABLE IF NOT EXISTS t (...)\")",
    "create_check_constraint": "op.execute con DO $$ IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = ...) $$",
    "create_unique_constraint": "idem, preguntando a pg_constraint",
    "create_foreign_key": "idem, preguntando a pg_constraint",
}
# Y las sentencias en texto plano que tampoco llevan guarda.
TEXTO_SIN_GUARDA = (("add column", "if not exists"), ("create index", "if not exists"),
                    ("create table", "if not exists"), ("create unique index", "if not exists"))


def _migraciones() -> list[Path]:
    return sorted(p for p in VERSIONS.glob("0*.py") if not p.name.startswith("0001_"))


def test_there_are_migrations_to_check():
    """Si el glob dejara de encontrar nada, el resto pasaría por vacío y no estaríamos comprobando nada."""
    assert len(_migraciones()) >= 10, [p.name for p in _migraciones()]


def test_no_migration_after_0001_uses_unguarded_ddl():
    fallos = []
    for p in _migraciones():
        arbol = ast.parse(p.read_text(encoding="utf-8"))
        subir = next((n for n in ast.walk(arbol) if isinstance(n, ast.FunctionDef) and n.name == "upgrade"), None)
        if subir is None:
            continue
        for nodo in ast.walk(subir):
            if not isinstance(nodo, ast.Call):
                continue
            f = nodo.func
            nombre = f.attr if isinstance(f, ast.Attribute) else None
            if nombre in SIN_GUARDA:
                fallos.append(f"{p.name}: op.{nombre}(...) — usar {SIN_GUARDA[nombre]}")
            elif nombre == "execute" and nodo.args and isinstance(nodo.args[0], ast.Constant) and isinstance(nodo.args[0].value, str):
                sql = " ".join(nodo.args[0].value.lower().split())
                for verbo, guarda in TEXTO_SIN_GUARDA:
                    if verbo in sql and guarda not in sql:
                        fallos.append(f"{p.name}: «{verbo}» sin «{guarda}»")
    assert not fallos, ("DDL sin guarda: en una base NUEVA la 0001 ya ejecutó db/schema.sql y esto falla con "
                        "DuplicateColumn / DuplicateTable.\n  " + "\n  ".join(fallos))


def test_the_schema_source_of_truth_carries_what_the_late_migrations_add():
    """El otro lado del mismo contrato: si `schema.sql` NO llevara lo que añade una migración tardía, una base nueva
    se quedaría sin esa columna — y como la migración ahora es idempotente, tampoco fallaría. Silencio, que es peor."""
    esquema = (VERSIONS.parents[1] / "schema.sql").read_text(encoding="utf-8").lower()
    esperado = {"diets": ["method", "methods", "doc_date", "retrieval_text"],
                "client_profiles": ["body_type", "training_time", "corpus_alias", "liked_food_ids", "is_corpus_case"],
                "lab_results": ["source_type", "report_sha1", "values_unreliable"],
                "body_measurements": ["muscle_mass_kg", "physique_rating", "visceral_fat_rating", "metabolic_age", "basal_met_kcal"]}
    faltan = [f"{t}.{c}" for t, cols in esperado.items() for c in cols if c not in esquema]
    assert not faltan, f"db/schema.sql no declara: {faltan}. Una base nueva arrancaría sin esas columnas."


if __name__ == "__main__":
    fallidos = 0
    for nombre, fn in sorted((k, v) for k, v in globals().items() if k.startswith("test_") and callable(v)):
        try:
            fn(); print(f"PASS {nombre}")
        except AssertionError as e:
            fallidos += 1; print(f"FAIL {nombre}: {e}")
    sys.exit(1 if fallidos else 0)
