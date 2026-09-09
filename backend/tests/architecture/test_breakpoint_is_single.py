# -*- coding: utf-8 -*-
"""El punto de corte del móvil está definido DOS veces, y las dos tienen que decir lo mismo.

Casi toda la adaptación a móvil vive en `@media` dentro de `styles.sass`, que es su sitio. Pero la lista de clientes
deja de ser una tabla y pasa a tarjetas por debajo del corte, y eso es un cambio de plantilla: lo decide TypeScript
(`LayoutService`), que necesita el mismo número.

Si los dos se separan queda una franja de anchos en la que ni la tabla ni las tarjetas se ven bien — y es un defecto
que no rompe ninguna compilación ni ningún test de comportamiento, así que no lo encontraría nadie. Por eso se
comprueba aquí, donde ya viven las comprobaciones que leen ficheros del árbol.
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
STYLES = ROOT / "frontend" / "src" / "styles.sass"
SERVICE = ROOT / "frontend" / "src" / "app" / "services" / "layout" / "layout.service.ts"


def test_typescript_and_the_stylesheet_agree_on_the_narrow_breakpoint():
    ts = SERVICE.read_text(encoding="utf-8")
    m = re.search(r"NARROW_MAX_WIDTH_PX\s*=\s*(\d+)", ts)
    assert m, "LayoutService ya no declara NARROW_MAX_WIDTH_PX"
    in_ts = int(m.group(1))

    sass = STYLES.read_text(encoding="utf-8")
    widths = {int(w) for w in re.findall(r"@media \(max-width: (\d+)px\)", sass)}
    assert widths, "styles.sass ya no declara ningún @media (max-width: …)"
    assert in_ts in widths, f"el corte de TypeScript es {in_ts} px y la hoja de estilos usa {sorted(widths)}"


def test_the_service_asks_the_media_query_instead_of_reading_the_width():
    """`innerWidth` leído una vez no se enteraría de un giro de pantalla ni de un redimensionado."""
    ts = SERVICE.read_text(encoding="utf-8")
    assert "matchMedia" in ts
    assert "innerWidth" not in ts, "un ancho leído a mano no reacciona a un giro de pantalla"
    assert "addEventListener" in ts and "removeEventListener" in ts, "el listener se registra y se retira"


if __name__ == "__main__":
    failed = 0
    for name, fn in sorted((k, v) for k, v in globals().items() if k.startswith("test_") and callable(v)):
        try:
            fn(); print(f"PASS {name}")
        except AssertionError as e:
            failed += 1; print(f"FAIL {name}: {e}")
    sys.exit(1 if failed else 0)
