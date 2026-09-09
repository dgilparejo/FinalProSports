"""Bloque 1.3 -- el campo `body_type` está sucio, y hay que separar «el rasgo no lleva señal» de «el campo no se lee».

`body_type` pesa 0,10 en la similitud y se compara con `==`. Con eso, `ectomorfo` y `ectomorfa` son **distintos**, y
`ECTOMORFO` y `Ectomorfo` también. Peor: de los 164 valores no nulos, **81 no son un somatotipo** — son la altura y el
peso escritos en la casilla equivocada (`173cm, 78kg`), y otros son frases (`ECTOMORFO TIRANDO A MESOMORFO`,
`Mesomorfo tirando a endomorfo`, `Ectomorfo trnasformado a mesomorfo por edad`).

El resultado es que la comparación cruda solo acierta cuando dos personas coinciden en el somatotipo **y en cómo lo
escribió él ese día**. Medir el rasgo así responde a una pregunta que no es la que interesa.

Esta política hace tres cosas, y las tres se miden por separado en el informe:

1. **`somatotype`** — normaliza: minúsculas, sin tildes, sin marca de género, tolerando la errata (`estomorfo`,
   `ectmorfa`), y resuelve los compuestos al **primero mencionado**, que es el que él escribe como base («X tirando a
   Y»). Se declara como simplificación: en un caso el texto dice que el actual es el segundo, y aun así se toma el
   primero, porque una regla que dependa de leer «transformado en» no es una regla.
2. **`is_clean`** — si el valor original era ya un somatotipo de una sola palabra. Es lo que permite medir el rasgo
   **restringido a los limpios** y saber si la señal existe cuando el campo está bien escrito.
3. **`height_cm` / `weight_kg`** — rescata lo que está mal colocado. `body_type` es el ÚNICO campo de texto libre del
   perfil que los lleva: se han buscado en los doce campos de texto del perfil y no aparecen en ningún otro.

AVISO sobre el peso rescatado: **no lleva fecha**. Es el peso del cuestionario, del día que el cliente rellenó la
hoja, y el perfil no guarda cuándo fue. Sirve para el expediente y para el PDF; **no** para una comparación fechada,
donde la báscula (0015) sí tiene fecha y cubre más. Se rescata y se declara, no se mete en la similitud por la puerta
de atrás.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

SOMATOTYPES = ("ectomorfo", "mesomorfo", "endomorfo")
# Raíces tolerantes a la errata: `estomorfo` por ectomorfo, `ectmorfa` por ectomorfa, `trnasformado` por transformado.
# Se aceptan porque son fallos de tecleo del propio profesional sobre una palabra que solo puede ser una de tres.
_ROOTS = ((re.compile(r"\be[cs]t[o]?m[o]?rf"), "ectomorfo"),
          (re.compile(r"\bmes[o]?m[o]?rf"), "mesomorfo"),
          (re.compile(r"\bend[o]?m[o]?rf"), "endomorfo"))
_HEIGHT = re.compile(r"\b(1[4-9]\d|2[01]\d)\s*cm\b", re.I)
_WEIGHT = re.compile(r"\b(\d{2,3})(?:[.,]\d+)?\s*(?:kg|kilos)\b", re.I)


def strip_accents(text: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", text) if unicodedata.category(c) != "Mn")


@dataclass(frozen=True)
class BodyTypeReading:
    somatotype: str | None          # 'ectomorfo' | 'mesomorfo' | 'endomorfo' | None
    secondary: str | None           # el segundo mencionado, cuando el valor es compuesto
    is_clean: bool                  # el original era UNA palabra que ya era un somatotipo
    height_cm: int | None           # rescatado del texto
    weight_kg: float | None         # rescatado del texto; SIN FECHA (ver el aviso de arriba)
    raw: str | None


EMPTY = BodyTypeReading(None, None, False, None, None, None)


def read(raw: str | None) -> BodyTypeReading:
    if not raw or not raw.strip():
        return EMPTY
    text = strip_accents(raw).lower()
    found = []
    for pattern, name in _ROOTS:
        m = pattern.search(text)
        if m:
            found.append((m.start(), name))
    found.sort()
    names = [n for _, n in found]
    height = _HEIGHT.search(raw)
    weight = _WEIGHT.search(raw)
    # «limpio» = una sola palabra y esa palabra es un somatotipo. `ectomorfa` cuenta: la marca de género no ensucia el
    # dato, solo rompía la comparación por `==`.
    word = re.sub(r"[^a-z]", "", text)
    clean = len(names) == 1 and word in {"ectomorfo", "ectomorfa", "mesomorfo", "mesomorfa", "endomorfo", "endomorfa"}
    return BodyTypeReading(
        somatotype=names[0] if names else None,
        secondary=names[1] if len(names) > 1 else None,
        is_clean=clean,
        height_cm=int(height.group(1)) if height else None,
        weight_kg=float(weight.group(1)) if weight else None,
        raw=raw)


def normalised(raw: str | None) -> str | None:
    """Lo que la similitud debería comparar: el somatotipo dominante, o None cuando el valor no lo declara."""
    return read(raw).somatotype
