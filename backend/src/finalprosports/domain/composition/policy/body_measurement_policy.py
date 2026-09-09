"""La regla temporal de la báscula: qué lectura puede ver el motor cuando escribe una dieta.

    LA LECTURA VÁLIDA DE UNA DIETA ES LA MÁS RECIENTE ESTRICTAMENTE ANTERIOR A SU FECHA.

Por qué estrictamente, y por qué es una política de dominio y no un `ORDER BY` escondido en una consulta:

* **Por qué anterior.** El profesional escribió cada dieta con la información que tenía delante ese día. Predecir una
  dieta de 2019 usando una báscula de 2023 no es una mejora del modelo, es leer la respuesta: la báscula posterior
  refleja el efecto de la dieta que se está intentando predecir. La serie va de 2016 a 2026 sobre los mismos clientes,
  así que la fuga no es una posibilidad remota — es la explicación más probable de cualquier ganancia que apareciera
  sin esta regla.

* **Por qué ESTRICTA (`<`, no `<=`).** Una lectura del mismo día podría ser de después de la consulta. El orden dentro
  del día no consta en ninguno de los dos ficheros de partida, así que no se puede afirmar que precediera, y lo que no se puede
  afirmar no se usa. Cuesta poco: con `<=` se ganarían unas pocas consultas y se perdería la posibilidad de decir sin
  matices que no hay fuga.

* **Por qué no se imputa nada.** Un cliente sin lectura anterior no se compara como si tuviera el peso medio: se
  compara como si ese rasgo no dijera nada. La similitud excluye el rasgo del numerador y del denominador
  (`attribute_similarity_policy`), que es lo único honesto cuando el profesional no tenía el dato.

Cobertura con esta regla, medida sobre el arnés (`eval.body_signals`): 617 de las 815 consultas (75,7 %) tienen una
lectura utilizable, con antigüedad mediana de 13 días y p90 de 69. De las 198 que no la tienen, 74 son clientes sin
báscula, 92 tienen lecturas pero todas posteriores, y 32 son dietas cuyo documento no lleva fecha.
"""
from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime

from finalprosports.domain.model import ClientProfile
from finalprosports.domain.model.client_record import BodyMeasurement

# De la lectura al perfil. Los nombres difieren porque la tabla es de S3 (hoja del expediente) y el perfil habla el
# idioma de la báscula; el mapa se escribe una vez y aquí, no repartido por los adaptadores.
FIELD_MAP = {"weight_kg": "weight_kg", "body_fat_pct": "fat_pct", "muscle_mass_kg": "muscle_mass_kg",
             "water_pct": "hydration_pct", "bone_kg": "bone_mass_kg", "physique_rating": "physique_rating",
             "visceral_fat_rating": "visceral_fat_rating", "metabolic_age": "metabolic_age",
             "basal_met_kcal": "basal_met_kcal"}
PROFILE_FIELDS = tuple(FIELD_MAP.values())


def iso(value) -> str | None:
    """Fecha ISO a partir de `date`, `datetime` o cadena. El orden lexicográfico de `YYYY-MM-DD` ES el cronológico."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return str(value)[:10]


def as_of(readings, on_date) -> BodyMeasurement | None:
    """La lectura más reciente ESTRICTAMENTE anterior a `on_date`. `None` cuando no hay fecha o no hay lectura previa.

    Sin `on_date` no se devuelve nada. Es deliberado: un llamante que no sabe para qué fecha compone no puede recibir
    la última lectura «porque sí», que es exactamente como se cuela una fuga temporal.
    """
    cut = iso(on_date)
    if not cut:
        return None
    prior = [r for r in readings if iso(r.measured_at) and iso(r.measured_at) < cut]
    return max(prior, key=lambda r: iso(r.measured_at)) if prior else None


def with_measurement(profile: ClientProfile, reading: BodyMeasurement | None) -> ClientProfile:
    """El perfil con la composición corporal de esa lectura. Sin lectura, el perfil vuelve SIN los nueve campos.

    Que el caso sin lectura se devuelva limpio importa: reutilizar un perfil ya poblado para otra fecha arrastraría la
    lectura de la anterior, y ésa es la forma silenciosa de la fuga.
    """
    if reading is None:
        return replace(profile, measured_at=None, **{f: None for f in PROFILE_FIELDS})
    return replace(profile, measured_at=iso(reading.measured_at),
                   **{dst: getattr(reading, src) for src, dst in FIELD_MAP.items()})


def profile_as_of(profile: ClientProfile, readings, on_date) -> ClientProfile:
    return with_measurement(profile, as_of(readings, on_date))
