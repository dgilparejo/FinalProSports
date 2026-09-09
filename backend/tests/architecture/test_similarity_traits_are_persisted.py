"""Todo rasgo que la similitud PONDERA tiene que sobrevivir al viaje de ida y vuelta a la base de datos.

Por que existe este test. La ampliacion de la similitud anadio `body_type` con peso 0,10 (elegido en desarrollo,
medido una vez en el apartado). El rasgo estaba en el dominio, en la migracion 0013, en el mapeador de lectura y en
la politica... y el INSERT del repositorio de clientes no lo escribia. Resultado: cada cliente de la cartera guardaba
NULL, la comparacion no lo evaluaba nunca y el peso no hacia absolutamente nada. Es el mismo defecto que motivo la
ampliacion -- enriquecer un expediente que la funcion de comparacion no lee -- una capa mas abajo.

El test no comprueba `body_type`: comprueba la REGLA. Si manana se activa `height` o `sport` subiendo su peso de 0 a
algo, este test falla hasta que la columna se escriba. Es AST y lectura de los propios ficheros: sin base de datos, sin dataset y
sin pytest, para que corra en el pre-commit.
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

SRC = Path(__file__).resolve().parents[2] / "src"
sys.path.insert(0, str(SRC))

from finalprosports.domain.composition.policy.attribute_similarity_policy import DEFAULT_WEIGHTS  # noqa: E402
from finalprosports.domain.model import ClientProfile  # noqa: E402

ADAPTER = SRC / "finalprosports/infrastructure/adapter/outbound/persistence/service/client/client_repository_output_adapter.py"
MAPPER = SRC / "finalprosports/infrastructure/adapter/outbound/persistence/mapper/client_profile_mapper.py"
CASE_ADAPTER = SRC / "finalprosports/infrastructure/adapter/outbound/persistence/service/case/case_repository_output_adapter.py"

# Rasgos de la similitud que NO son columnas del perfil, con el porque. Cualquier otro nombre ponderado tiene que ser
# un campo de ClientProfile y aparecer en los tres ficheros.
NOT_A_PROFILE_COLUMN = {
    "goal": "se guarda como `goals`",
    "sex": "columna `sex`",
    "age": "columna `age`",
    "activity": "columna `activity_level`",
    "restrictions": "columna `restrictions`",
    "method": "vive en la DIETA (`diets.methods`), no en el perfil",
    # Los siete de la bascula (0015) NO son columnas de `client_profiles` y no deben serlo: no son atributos del
    # cliente sino del INSTANTE. Viven en `body_measurements` y llegan al perfil por la regla temporal
    # (`body_measurement_policy.as_of` + el LATERAL de CANDIDATE_SQL). Guardarlos en el perfil seria justo el error
    # que este fichero persigue, en espejo: un valor congelado que se usaria para dietas de cualquier fecha.
    # Su guarda equivalente es `tests/infrastructure/test_no_temporal_leak.py`.
    "weight": "body_measurements, resuelto por fecha", "fat": "body_measurements, resuelto por fecha",
    "muscle": "body_measurements, resuelto por fecha", "visceral": "body_measurements, resuelto por fecha",
    "metabolic_age": "body_measurements, resuelto por fecha", "basal_met": "body_measurements, resuelto por fecha",
    "hydration": "body_measurements, resuelto por fecha",
}


def weighted_traits() -> set[str]:
    """Los rasgos con peso ESTRICTAMENTE mayor que cero. Un peso 0 es un rasgo declarado y desactivado."""
    return {f: getattr(DEFAULT_WEIGHTS, f) for f in vars(DEFAULT_WEIGHTS)
            if "span" not in f and isinstance(getattr(DEFAULT_WEIGHTS, f), float) and getattr(DEFAULT_WEIGHTS, f) > 0}


def upsert_sql() -> str:
    """El literal del INSERT sobre client_profiles, aislado del resto del fuente.

    Se lee el SQL y no el fichero entero a proposito: buscar el nombre del rasgo en todo el modulo daba PASS aun
    despues de quitarlo de la lista de columnas, porque seguia apareciendo en el `DO UPDATE` y en el diccionario de
    parametros. Un guarda que no distingue esas dos situaciones no guarda nada.
    """
    tree = ast.parse(ADAPTER.read_text(encoding="utf-8"))
    literals = [n.value for n in ast.walk(tree)
                if isinstance(n, ast.Constant) and isinstance(n.value, str) and "INSERT INTO client_profiles" in n.value]
    assert len(literals) == 1, f"hay {len(literals)} INSERT sobre client_profiles"
    return literals[0]


def test_every_weighted_trait_is_written_read_and_retrieved():
    profile_fields = {f.name for f in ClientProfile.__dataclass_fields__.values()}
    sql = upsert_sql()
    columnas = sql.split("(", 1)[1].split(")", 1)[0]                    # la lista de columnas del INSERT
    values = sql.split("VALUES", 1)[1].split(")", 1)[0]                 # los marcadores :x del VALUES
    on_conflict = sql.split("DO UPDATE SET", 1)[1]                      # el UPDATE de la fila existente
    faltan = []
    for trait, peso in weighted_traits().items():
        if trait in NOT_A_PROFILE_COLUMN:
            continue
        if trait not in profile_fields:
            faltan.append(f"{trait}: pesa {peso} y no es un campo de ClientProfile")
            continue
        if trait not in [c.strip() for c in columnas.split(",")]:
            faltan.append(f"{trait}: pesa {peso} y no esta en la lista de columnas del INSERT")
        if f":{trait}" not in values:
            faltan.append(f"{trait}: pesa {peso} y no tiene marcador en el VALUES")
        if f"{trait} = EXCLUDED.{trait}" not in on_conflict:
            faltan.append(f"{trait}: pesa {peso} y el ON CONFLICT no lo actualiza (se pierde al reguardar)")
        for source, what in ((MAPPER, "el mapeador de lectura del perfil"),
                             (CASE_ADAPTER, "la hidratacion de los casos recuperados")):
            if trait not in source.read_text(encoding="utf-8"):
                faltan.append(f"{trait}: pesa {peso} y no aparece en {what} ({source.name})")
    assert not faltan, ("un rasgo ponderado que no viaja a la base de datos vale NULL para toda la cartera y el peso "
                        "no hace nada:\n  - " + "\n  - ".join(faltan))


def test_the_guard_can_fail():
    """Una comprobacion que no puede fallar no es una comprobacion: se activa un rasgo hoy a cero y tiene que saltar."""
    import dataclasses
    apagados = [f for f in vars(DEFAULT_WEIGHTS)
                if isinstance(getattr(DEFAULT_WEIGHTS, f), float) and getattr(DEFAULT_WEIGHTS, f) == 0.0]
    assert apagados, "sin rasgos a cero este test no puede demostrar nada; deja al menos uno declarado y desactivado"
    encendido = dataclasses.replace(DEFAULT_WEIGHTS, **{apagados[0]: 0.10})
    assert getattr(encendido, apagados[0]) > 0
    assert apagados[0] not in weighted_traits(), "con el peso a 0 el rasgo NO se exige"


def test_the_write_adapter_is_a_single_statement_so_the_grep_means_something():
    """El test de arriba busca el nombre del rasgo en el fuente. Eso solo prueba algo si el fuente tiene un unico
    sitio donde escribir el perfil: con dos INSERT distintos, encontrar el nombre en uno no garantiza el otro."""
    tree = ast.parse(ADAPTER.read_text(encoding="utf-8"))
    inserts = [n for n in ast.walk(tree)
               if isinstance(n, ast.Constant) and isinstance(n.value, str) and "INSERT INTO client_profiles" in n.value]
    assert len(inserts) == 1, f"hay {len(inserts)} INSERT sobre client_profiles; el test de arriba deja de ser suficiente"


if __name__ == "__main__":
    fallos = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"PASS {name}")
            except AssertionError as e:
                fallos += 1
                print(f"FAIL {name}: {e}")
    print(f"OK: {fallos} failing")
    raise SystemExit(1 if fallos else 0)
