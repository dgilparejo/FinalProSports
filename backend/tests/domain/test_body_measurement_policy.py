# -*- coding: utf-8 -*-
"""LA REGLA TEMPORAL DE LA BÁSCULA (bloque 0.1). Este fichero existe para que una fuga temporal rompa la suite.

La lectura válida de una dieta es la MÁS RECIENTE ESTRICTAMENTE ANTERIOR a su fecha. Sin esta comprobación, cualquier
mejora que apareciera al activar los pesos de la báscula sería indistinguible de leer la respuesta: la báscula posterior
a una dieta refleja el efecto de esa dieta, y la serie va de 2016 a 2026 sobre los mismos clientes.

Las cuatro cosas que se afirman aquí, y qué se rompería si dejaran de cumplirse:
  1. se elige la anterior más reciente, no la última de la serie   -> fuga directa;
  2. la comparación es ESTRICTA: la del mismo día no vale          -> fuga de un día, indemostrable;
  3. sin fecha de dieta no se devuelve NINGUNA lectura             -> fuga silenciosa en las 32 dietas sin fecha;
  4. un perfil sin lectura vuelve LIMPIO                           -> arrastre de la lectura de la consulta anterior.
"""
import sys
from datetime import date, datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
from finalprosports.domain.composition.policy.body_measurement_policy import (  # noqa: E402
    FIELD_MAP, PROFILE_FIELDS, as_of, iso, profile_as_of, with_measurement)
from finalprosports.domain.model import ClientProfile  # noqa: E402
from finalprosports.domain.model.client_record import BodyMeasurement  # noqa: E402

SERIE = (BodyMeasurement(datetime(2017, 5, 3, tzinfo=timezone.utc), weight_kg=95.0, body_fat_pct=30.0),
         BodyMeasurement(datetime(2019, 2, 1, tzinfo=timezone.utc), weight_kg=88.0, body_fat_pct=25.0),
         BodyMeasurement(datetime(2019, 8, 9, tzinfo=timezone.utc), weight_kg=84.0, body_fat_pct=22.0),
         BodyMeasurement(datetime(2023, 4, 4, tzinfo=timezone.utc), weight_kg=70.0, body_fat_pct=12.0))
PERFIL = ClientProfile("CLIENTE_001", "prof_001", "M", 34, 180, 3)


def test_picks_the_most_recent_reading_before_the_diet():
    assert as_of(SERIE, "2019-09-01").weight_kg == 84.0                 # la de agosto, no la de febrero
    assert as_of(SERIE, "2019-06-01").weight_kg == 88.0
    assert as_of(SERIE, "2018-01-01").weight_kg == 95.0


def test_never_uses_a_reading_after_the_diet():
    """La comprobación que da nombre al fichero: para CADA fecha de corte, lo devuelto es anterior."""
    for corte in ("2017-01-01", "2018-06-30", "2019-02-01", "2019-12-31", "2023-04-04", "2026-01-01"):
        r = as_of(SERIE, corte)
        if r is not None:
            assert iso(r.measured_at) < corte, (corte, iso(r.measured_at))
    assert as_of(SERIE, "2017-05-03") is None                           # la del MISMO día no vale: orden intradía desconocido
    assert as_of(SERIE, "2017-01-01") is None                           # no hay ninguna anterior


def test_without_a_diet_date_there_is_no_reading():
    assert as_of(SERIE, None) is None and as_of(SERIE, "") is None
    assert profile_as_of(PERFIL, SERIE, None).weight_kg is None


def test_a_profile_without_a_reading_comes_back_clean():
    """Un perfil ya poblado que se reutiliza para otra fecha NO puede conservar la lectura anterior."""
    poblado = profile_as_of(PERFIL, SERIE, "2023-01-01")
    assert poblado.weight_kg == 84.0 and poblado.measured_at == "2019-08-09"
    limpio = profile_as_of(poblado, SERIE, "2017-01-01")
    assert limpio.measured_at is None
    for f in PROFILE_FIELDS:
        assert getattr(limpio, f) is None, f


def test_every_mapped_field_reaches_the_profile():
    lectura = BodyMeasurement(datetime(2020, 1, 1, tzinfo=timezone.utc), weight_kg=80.0, body_fat_pct=18.0,
                              water_pct=55.0, bone_kg=3.1, muscle_mass_kg=60.0, physique_rating=5,
                              visceral_fat_rating=7.0, metabolic_age=29, basal_met_kcal=1800)
    p = with_measurement(PERFIL, lectura)
    for src, dst in FIELD_MAP.items():
        assert getattr(p, dst) == getattr(lectura, src), (src, dst)
    assert p.measured_at == "2020-01-01" and p.has_body_composition


def test_iso_accepts_date_datetime_and_string():
    assert iso(date(2021, 3, 4)) == "2021-03-04"
    assert iso(datetime(2021, 3, 4, 22, 30, tzinfo=timezone.utc)) == "2021-03-04"
    assert iso("2021-03-04T10:00:00") == "2021-03-04" and iso(None) is None


if __name__ == "__main__":
    failed = 0
    for name, fn in sorted((k, v) for k, v in globals().items() if k.startswith("test_") and callable(v)):
        try:
            fn(); print(f"PASS {name}")
        except AssertionError as e:
            failed += 1; print(f"FAIL {name}: {e}")
    sys.exit(1 if failed else 0)
