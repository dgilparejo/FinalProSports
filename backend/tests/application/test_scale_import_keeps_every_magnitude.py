# -*- coding: utf-8 -*-
"""El importador de la báscula guarda las ONCE magnitudes de la exportación, con los nombres que la exportación usa.

El `.bin` del aparato es un ZIP con `users`, `history` y `goals`, y sus filas de `history` van en camelCase
(`percentFat`, `percentHydration`, `boneMass`, `muscleMass`, `physiqueRating`, `visceralFatRating`, `metabolicAge`,
`basalMet`). El contrato se lee de `pipeline_v3/scale.py`, que es quien abre el fichero de verdad y construyó la serie
del corpus (1.338 lecturas de 171 clientes).

Antes de este test el importador esperaba `fat`, `water`, `bone` y no conocía las cinco magnitudes que abrió la
migración 0015, así que de una fila real guardaba el peso y la fecha y tiraba las otras nueve EN SILENCIO: sin error,
sin aviso, con la fila creada. Este test falla si se vuelve a estrechar.
"""
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
from finalprosports.application.usecase.record.import_body_composition_use_case import measurements_from_history  # noqa: E402

# Una fila tal cual la escribe la exportación. `basalMet` va como CADENA a propósito: es un defecto conocido del
# extractor documentado en `eval.body_signals`, y el importador tiene que sobrevivirlo.
BIN_ROW = {"uuid": "u-1", "date": 1_755_000_000_000, "weight": 78.8, "percentFat": 17.8, "percentHydration": 56.6,
           "boneMass": 3.2, "muscleMass": 61.7, "physiqueRating": 5, "visceralFatRating": 4.6, "metabolicAge": 27,
           "basalMet": "2725", "height": 171}

# La misma lectura ya renombrada por el extractor, que es lo que hay en `body_measurements.jsonl`.
JSONL_ROW = {"client_code": "CLIENTE_001", "date": "2026-08-12", "weight_kg": 78.8, "fat_pct": 17.8,
             "hydration_pct": 56.6, "bone_mass_kg": 3.2, "muscle_mass_kg": 61.7, "physique_rating": 5,
             "visceral_fat_rating": 4.6, "metabolic_age": 27, "basal_met_kcal": 2725, "height_cm": 171}

EXPECTED = {"weight_kg": 78.8, "body_fat_pct": 17.8, "water_pct": 56.6, "bone_kg": 3.2, "muscle_mass_kg": 61.7,
            "physique_rating": 5, "visceral_fat_rating": 4.6, "metabolic_age": 27, "basal_met_kcal": 2725,
            "height_cm": 171}


def _check(row: dict, dialect: str) -> None:
    (m,) = measurements_from_history([row])
    for field, expected in EXPECTED.items():
        got = getattr(m, field)
        assert got == expected, f"{dialect}: {field} = {got!r}, se esperaba {expected!r}"
    assert m.source == "scale"


def test_the_bin_dialect_keeps_every_magnitude():
    _check(BIN_ROW, "el .bin de la báscula")


def test_the_extractor_dialect_keeps_every_magnitude():
    _check(JSONL_ROW, "body_measurements.jsonl")


def test_muscle_in_kilos_never_lands_in_the_percentage_field():
    """La 0015 abrió `muscle_mass_kg` porque la báscula da KILOS y `muscle_pct` es un porcentaje. Convertir uno en el
    otro exigiría inventarse el peso de referencia, así que 61,7 kg no puede aparecer como 61,7 %."""
    (m,) = measurements_from_history([BIN_ROW])
    assert m.muscle_mass_kg == 61.7
    assert m.muscle_pct is None


def test_the_date_survives_epoch_milliseconds_and_iso():
    (a,) = measurements_from_history([BIN_ROW])
    (b,) = measurements_from_history([JSONL_ROW])
    assert a.measured_at == datetime.fromtimestamp(1_755_000_000, timezone.utc)
    assert b.measured_at.date().isoformat() == "2026-08-12"


def test_an_absent_magnitude_stays_none_instead_of_zero():
    """Un campo que la báscula no dio no es un cero: un 0 % de grasa se leería como una medición."""
    (m,) = measurements_from_history([{"date": 1_755_000_000_000, "weight": 80.0}])
    assert m.weight_kg == 80.0
    assert (m.body_fat_pct, m.water_pct, m.bone_kg, m.muscle_mass_kg, m.physique_rating,
            m.visceral_fat_rating, m.metabolic_age, m.basal_met_kcal) == (None,) * 8


def test_the_serialised_reading_carries_every_magnitude_to_the_interface():
    """Guardarlas y no devolverlas es el mismo defecto un piso más arriba: la frontera REST emitía seis de once."""
    from finalprosports.infrastructure.adapter.inbound.rest.service.record.client_record_rest_adapter import measurement_to_dict
    (m,) = measurements_from_history([BIN_ROW])
    d = measurement_to_dict(m)
    for field, expected in EXPECTED.items():
        assert d.get(field) == expected, f"la frontera REST no emite {field}"
    assert set(d) == set(EXPECTED) | {"measured_at", "muscle_pct", "source"}


if __name__ == "__main__":
    failed = 0
    for name, fn in sorted((k, v) for k, v in globals().items() if k.startswith("test_") and callable(v)):
        try:
            fn(); print(f"PASS {name}")
        except AssertionError as e:
            failed += 1; print(f"FAIL {name}: {e}")
    sys.exit(1 if failed else 0)
