"""Las analíticas como fuente del motor: la misma regla temporal que la báscula, y una frontera que no se cruza.

**Por qué entran.** El objetivo del trabajo es reproducir a ESTE profesional, y él mira estas mediciones antes de
escribir. Excluirlas hace el sistema menos parecido a él, que es lo contrario de lo que se persigue. La postura, y
conviene decirla entera: **no se valida el instrumento, se modela al profesional que lo usa.**

**Qué son, sin adornos.** El volumen —217 de los 254 informes, 189 parámetros distintos, 106 de ellos en 30 clientes o
más— sale de un **bioanalizador**, un dispositivo con índices propios; entre sus «parámetros» hay `Pie Jue Yin
Higado`, `Meridiano del Pie Yangmin` y `Sistema Motor`. No son magnitudes de laboratorio y no pueden presentarse como
tales. La analítica de laboratorio convencional cubre **1 de las 815 consultas del arnés**. Por eso `source_type` es
obligatorio en cada fila: para que nadie compare un índice de dispositivo con una magnitud clínica creyendo que son la
misma cosa.

**La regla temporal, idéntica a la de la báscula (`body_measurement_policy`):**

    LA MEDICIÓN VÁLIDA DE UNA DIETA ES LA MÁS RECIENTE ESTRICTAMENTE ANTERIOR A SU FECHA.

Estricta por lo mismo: el orden dentro del día no consta. Un informe **sin fecha** no se usa nunca — 56 no la llevan —
y eso no es un hueco que rellenar: sin fecha no se puede afirmar que precediera, y una analítica posterior a la dieta
refleja el efecto de la dieta que se intenta predecir.

**LA FRONTERA QUE NO SE CRUZA.** Estos valores pueden alimentar la recuperación y verse en la ficha del cliente. **No
pueden aparecer en el documento que recibe el cliente, ni justificar en él ninguna recomendación, ni figurar en el
panel de explicabilidad como razón de un alimento.** No es prudencia: es que el sistema no está validado para emitir
hallazgos de salud, y un índice de bioanalizador impreso junto a una recomendación se lee como si lo estuviera. Lo
impone `tests/architecture/test_labs_never_reach_the_client.py`, no este comentario.
"""
from __future__ import annotations

from dataclasses import dataclass

from finalprosports.domain.composition.policy.body_measurement_policy import iso

# Los espacios de nombres que el motor PUEDE mirar. `sports_physiology` y `nutrigenetic` quedan fuera: el primero es
# una tabla antropométrica que el extractor lee mal, el segundo no tiene filas analito/valor.
ENGINE_NAMESPACES = frozenset({"bioanalyzer", "clinical"})


@dataclass(frozen=True)
class LabValue:
    marker: str
    value: float
    source_type: str
    measured_at: str | None
    unit: str | None = None
    ref_low: float | None = None
    ref_high: float | None = None
    unreliable: bool = False

    @property
    def usable(self) -> bool:
        return (not self.unreliable and self.measured_at is not None
                and self.source_type in ENGINE_NAMESPACES)


def as_of(values, on_date) -> dict[str, LabValue]:
    """Para cada parámetro, la medición más reciente ESTRICTAMENTE anterior a `on_date`.

    Devuelve un diccionario `marcador -> valor` y no una lista: lo que el motor puede usar de un cliente en una fecha
    es UN valor por parámetro, el vigente ese día. Sin `on_date` devuelve vacío, deliberadamente — un llamante que no
    sabe para qué fecha compone no puede recibir «la última», que es como se cuela una fuga.
    """
    cut = iso(on_date)
    if not cut:
        return {}
    out: dict[str, LabValue] = {}
    for v in values:
        if not v.usable:
            continue
        stamp = iso(v.measured_at)
        if not stamp or stamp >= cut:
            continue
        current = out.get(v.marker)
        if current is None or iso(current.measured_at) < stamp:
            out[v.marker] = v
    return out
