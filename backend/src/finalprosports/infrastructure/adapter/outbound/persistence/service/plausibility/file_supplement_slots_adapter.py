"""La tabla de colocación de suplementos, leída del artefacto minado (`$FPS_DATASET_DIR/supplement_slots.json`).

Es el RESPALDO de `supplement_placement_policy`, no su criterio principal: la colocación la deciden primero los casos
recuperados de cada cliente, y esta tabla solo contesta el 25,2 % que los veinte vecinos no saben colocar.

Cuando el fichero no está, devuelve un diccionario vacío y la política se queda solo con los casos. Es degradación
correcta, no un fallo: sin respaldo unos pocos suplementos se quedan en el bloque genérico, que es exactamente lo que
la política hace cuando no sabe dónde ponerlos.
"""
from __future__ import annotations

import json
from pathlib import Path

from finalprosports.infrastructure.config.paths import dataset_dir

# Por debajo de esta concentración la moda no se usa. Se elige aquí y no en el minero porque es una decisión de
# CONSUMO: el artefacto guarda la distribución entera precisamente para que quien la lea ponga su propio listón.
# 0,25 deja fuera los suplementos que él reparte por todo el día sin preferencia, donde elegir la moda sería fingir
# un criterio que no tiene.
MIN_CONCENTRATION = 0.25


class FileSupplementSlotsAdapter:
    def __init__(self, path: Path | None = None, min_concentration: float = MIN_CONCENTRATION):
        self._path, self._min = path, min_concentration
        self._cache: dict[int, str] | None = None

    def load(self, professional_id: str) -> dict[int, str]:
        if self._cache is None:
            path = self._path or dataset_dir() / "supplement_slots.json"
            data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
            self._cache = {p["food_id"]: p["slot"] for p in (data.get("placements") or {}).values()
                           if p.get("concentration", 0.0) >= self._min}
        return self._cache
