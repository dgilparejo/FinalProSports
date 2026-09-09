# -*- coding: utf-8 -*-
"""LA REGLA TEMPORAL DE LAS ANALÍTICAS. Existe para que una fuga temporal por esta vía rompa la suite.

Es la misma regla que la de la báscula y por el mismo motivo: una analítica posterior a una dieta refleja el efecto de
la dieta que se intenta predecir. Aquí hay además dos cosas propias de esta fuente:

  * hay **56 informes sin fecha**, y sin fecha NO se usan. Es la vía más fácil de colar una medición del futuro:
    basta con tratar «sin fecha» como «vale siempre»;
  * hay **cuatro espacios de nombres** y solo dos pueden llegar al motor. `sports_physiology` es una tabla
    antropométrica que el extractor lee como si fueran analitos, y `nutrigenetic` no tiene filas de valor.
"""
import sys
from datetime import date, datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
from finalprosports.domain.composition.policy.lab_measurement_policy import ENGINE_NAMESPACES, LabValue, as_of  # noqa: E402


def v(marker, value, when, **kw):
    return LabValue(marker=marker, value=value, source_type=kw.pop("source_type", "bioanalyzer"),
                    measured_at=when, **kw)


SERIE = (v("Insulina", 3.1, "2018-05-01"), v("Insulina", 3.9, "2021-02-10"), v("Insulina", 4.4, "2024-06-30"),
         v("Glucagon", 2.4, "2021-02-10"))


def test_picks_the_most_recent_measurement_before_the_diet():
    got = as_of(SERIE, "2022-01-01")
    assert got["Insulina"].value == 3.9 and got["Insulina"].measured_at == "2021-02-10"
    assert got["Glucagon"].value == 2.4
    assert as_of(SERIE, "2019-01-01")["Insulina"].value == 3.1


def test_never_uses_a_measurement_after_the_diet():
    """Para CADA fecha de corte, todo lo devuelto es anterior. Es la comprobación que da nombre al fichero."""
    for corte in ("2018-01-01", "2018-05-01", "2020-12-31", "2021-02-10", "2024-06-30", "2026-01-01"):
        for marcador, val in as_of(SERIE, corte).items():
            assert val.measured_at < corte, (corte, marcador, val.measured_at)
    assert as_of(SERIE, "2018-05-01") == {}          # la del MISMO día no vale
    assert "Glucagon" not in as_of(SERIE, "2021-02-10")


def test_a_report_without_a_date_is_never_used():
    """56 informes no llevan fecha. Tratarlos como «valen siempre» sería la fuga más fácil de colar."""
    sin_fecha = (v("Insulina", 99.0, None),)
    assert as_of(sin_fecha, "2026-01-01") == {}
    assert not sin_fecha[0].usable


def test_without_a_diet_date_nothing_is_returned():
    assert as_of(SERIE, None) == {} and as_of(SERIE, "") == {}


def test_only_the_two_engine_namespaces_reach_the_motor():
    assert ENGINE_NAMESPACES == {"bioanalyzer", "clinical"}
    fuera = (v("GENERAL PESO", 68.2, "2020-01-01", source_type="sports_physiology"),
             v("Informe", 1.0, "2020-01-01", source_type="nutrigenetic"))
    assert as_of(fuera, "2026-01-01") == {}


def test_unreliable_values_are_kept_but_never_used():
    """Los 22 informes con las columnas desordenadas se conservan —no se descarta nada— y no los usa nadie."""
    malo = (v("TRIGLICERIDOS", 150.0, "2020-01-01", source_type="clinical", unreliable=True),)
    assert malo[0].value == 150.0                     # sigue ahí
    assert not malo[0].usable and as_of(malo, "2026-01-01") == {}


def test_one_value_per_marker_the_one_in_force_that_day():
    got = as_of(SERIE, "2026-01-01")
    assert set(got) == {"Insulina", "Glucagon"} and got["Insulina"].value == 4.4


if __name__ == "__main__":
    failed = 0
    for name, fn in sorted((k, v2) for k, v2 in globals().items() if k.startswith("test_") and callable(v2)):
        try:
            fn(); print(f"PASS {name}")
        except AssertionError as e:
            failed += 1; print(f"FAIL {name}: {e}")
    sys.exit(1 if failed else 0)
