# -*- coding: utf-8 -*-
"""La lista de clientes de demostracion (`make demo`), comprobada SIN base de datos.

Sembrar la cartera de demostracion tarda siete segundos y necesita el corpus cargado; los defectos que tiene una lista
de dieciseis clientes escrita a mano, en cambio, son de los que se ven leyendola: un objetivo que el corpus no puede
servir (y entonces la pantalla de ese cliente es un 422), dos clientes con el mismo telefono, una serie de bascula
apuntando a un `tag` que ya no existe, un nombre al que se le ha caido la palabra «Demo». Esta prueba fija esas
invariantes donde salen gratis, para que el fallo aparezca al escribir el cliente y no al ensenarlo.

Lo que NO comprueba: que la propuesta salga bien. Eso pide corpus, y lo cubre el propio sembrador al correr
(`propose` de los dieciseis) mas la puerta de entrega de `tests/infrastructure`.

Los objetivos servibles NO se listan aqui a mano: son los que el motor acepta segun `neighbourhood_policy` medido
sobre dataset-v3, y estan escritos en la cabecera del sembrador. Aqui se comprueba lo categorico -- que ninguno de los
cuatro que el motor rechaza con `goal_not_servable` (mantenimiento, alta_en_fibra, hipocalorica, descarga_carga) se
haya colado en la lista, ni el comodin `sin_clasificar`, que no es un objetivo que nadie elija.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from finalprosports.domain.model import Goal, RestrictionKind  # noqa: E402
from finalprosports.infrastructure.adapter.inbound.cli.seed_demo import (  # noqa: E402
    DEMO_CLIENTS,
    DEMO_LABS_VALUES,
    DEMO_RECORDS,
    DEMO_SCALE,
    LAB_REFS,
    demo_key,
    lab_panel,
    scale_export,
)

NOT_SERVABLE = {Goal.MAINTENANCE, Goal.HIGH_FIBRE, Goal.HYPOCALORIC, Goal.CARB_CYCLING, Goal.UNCLASSIFIED}
TAGS = tuple(s["tag"] for s in DEMO_CLIENTS)


def test_the_roster_is_between_ten_and_twenty_clients():
    """El encargo era «10-20 clientes para probar con datos completos»; el numero es dato, no casualidad."""
    assert 10 <= len(DEMO_CLIENTS) <= 20, len(DEMO_CLIENTS)


def test_no_demo_client_carries_a_goal_the_corpus_cannot_serve():
    for spec in DEMO_CLIENTS:
        assert spec["goal"] not in NOT_SERVABLE, f"{spec['tag']}: {spec['goal'].value} devuelve 422 goal_not_servable"


def test_tags_keys_phones_and_e_mails_are_unique():
    for field in ("tag", "phone", "email", "full_name"):
        values = [s[field] for s in DEMO_CLIENTS]
        assert len(set(values)) == len(values), f"{field} repetido"
    keys = [demo_key(t) for t in TAGS]
    assert len(set(keys)) == len(keys)


def test_every_name_says_it_is_a_demonstration():
    """Regla de manejo de datos: nadie que abra la aplicacion puede confundir la cartera con pacientes reales."""
    for spec in DEMO_CLIENTS:
        name = spec["full_name"]
        assert "Demo" in name or "Ficticio" in name or "Ficticia" in name, name
        assert len(name.split()) >= 3, name


def test_phones_and_e_mails_cannot_reach_anybody():
    for spec in DEMO_CLIENTS:
        assert spec["phone"].startswith("+34 000 "), spec["tag"]        # prefijo que ningun numero espanol tiene
        assert spec["email"].endswith(".invalid"), spec["tag"]          # TLD reservado (RFC 2606)


def test_the_profile_fields_the_engine_reads_are_all_filled():
    for spec in DEMO_CLIENTS:
        assert spec["sex"] in ("M", "F"), spec["tag"]
        assert 140 <= spec["height_cm"] <= 210, spec["tag"]
        assert 1 <= spec["activity_level"] <= 5, spec["tag"]
        assert isinstance(spec["goal"], Goal), spec["tag"]
        assert all(isinstance(r, RestrictionKind) for r in spec["restrictions"]), spec["tag"]
        assert 0 <= spec["versions"] <= 3, spec["tag"]


def test_every_client_has_an_intake_sheet_and_the_side_tables_point_at_real_tags():
    assert set(DEMO_RECORDS) == set(TAGS), set(DEMO_RECORDS) ^ set(TAGS)
    for table, name in ((DEMO_SCALE, "DEMO_SCALE"), (DEMO_LABS_VALUES, "DEMO_LABS_VALUES")):
        unknown = set(table) - set(TAGS)
        assert not unknown, f"{name} apunta a tags que no existen: {sorted(unknown)}"


def test_the_roster_covers_both_routings_both_sexes_and_the_declaring_band():
    """Una cartera de demostracion sirve para ver los CAMINOS del motor, no para tener muchas filas."""
    assert sum(1 for s in DEMO_CLIENTS if s["versions"] > 0) >= 3, "sin recurrentes no hay rotacion que ensenar"
    assert sum(1 for s in DEMO_CLIENTS if s["versions"] == 0) >= 3, "sin altas nuevas no hay arranque en frio"
    assert len({s["sex"] for s in DEMO_CLIENTS}) == 2
    assert any(s["goal"] is Goal.KETO for s in DEMO_CLIENTS), "cetosis_keto es la banda «servir declarando»"
    assert sum(1 for s in DEMO_CLIENTS if s["restrictions"]) >= 3, "sin restricciones el validador no se ve"
    assert sum(1 for s in DEMO_CLIENTS if not s["restrictions"]) >= 3


def test_two_records_are_left_thin_on_purpose():
    """Los medidores de completitud de S3 no dicen nada si todo el mundo esta al 100 %."""
    thin = [t for t in TAGS if t not in DEMO_SCALE and t not in DEMO_LABS_VALUES]
    assert len(thin) >= 2, thin


def test_the_lab_panels_use_declared_ranges_and_show_both_states():
    """Los colores semanticos se ven si hay marcadores fuera de rango; el estado «todo en rango» tambien es un
    resultado, y una analitica entera limpia (`india`, deportista de 31 anos) es lo que la pantalla ensena cuando no
    hay nada que mirar. Por eso la condicion es de CONJUNTO y no panel a panel."""
    con_hallazgo = 0
    for tag, (day, values) in DEMO_LABS_VALUES.items():
        assert values, tag
        unknown = set(values) - set(LAB_REFS)
        assert not unknown, f"{tag}: marcadores sin rango declarado: {sorted(unknown)}"
        panel = lab_panel(day, values)
        assert len(panel) == len(values)
        assert all(r.measured_at == day and r.unit for r in panel), tag
        con_hallazgo += any(r.out_of_range for r in panel)
    assert con_hallazgo >= len(DEMO_LABS_VALUES) - 2, f"solo {con_hallazgo} paneles con algo fuera de rango"
    assert con_hallazgo < len(DEMO_LABS_VALUES), "ninguna analitica sale limpia, y eso tambien hay que poder verlo"


def test_the_scale_series_is_monotonic_coherent_with_the_goal_and_physiologically_plausible():
    """La serie se GENERA, asi que lo que hay que fijar es que lo generado siga siendo un cuerpo posible."""
    by_tag = {s["tag"]: s for s in DEMO_CLIENTS}
    for tag, anchor in DEMO_SCALE.items():
        weight_now, fat_now, drift, readings = anchor
        users, history = scale_export(by_tag[tag], anchor)
        assert len(users) == 1 and len(history) == readings, tag
        assert users[0]["isMale"] is (by_tag[tag]["sex"] == "M"), tag
        weights = [row["weight"] for row in history]
        assert history[0]["date"] < history[-1]["date"], f"{tag}: la serie va de la mas antigua a la mas reciente"
        assert abs(weights[-1] - weight_now) < 0.05, f"{tag}: la ultima lectura es la del ancla"
        assert (weights[-1] < weights[0]) is (drift < 0), f"{tag}: la tendencia no acompana al objetivo"
        for row in history:
            assert 35 <= row["weight"] <= 200, tag
            assert 3 <= row["percentFat"] <= 60, tag
            assert 40 <= row["percentHydration"] <= 70, tag
            assert 1.0 <= row["boneMass"] <= 5.5, tag
            assert 15 <= row["muscleMass"] <= 80, tag
            assert 1 <= row["physiqueRating"] <= 9, tag
            assert 0.5 <= row["visceralFatRating"] <= 20, tag
            assert 15 <= row["metabolicAge"] <= 90, tag
            assert 900 <= int(row["basalMet"]) <= 3500, tag
        # la grasa acompana al peso: baja cuando se pierde peso y sube (poco) cuando se gana
        assert (history[-1]["percentFat"] < history[0]["percentFat"]) is (drift < 0), tag


if __name__ == "__main__":
    failed = 0
    for name, fn in sorted((k, v) for k, v in globals().items() if k.startswith("test_") and callable(v)):
        try:
            fn(); print(f"PASS {name}")
        except AssertionError as e:
            failed += 1; print(f"FAIL {name}: {e}")
    sys.exit(1 if failed else 0)
