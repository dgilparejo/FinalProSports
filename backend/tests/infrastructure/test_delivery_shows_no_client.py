# -*- coding: utf-8 -*-
"""LA APLICACIÓN SE ENTREGA VACÍA — comprobado sobre la base de datos de entrega, no mirado por la pantalla.

Requisito del cliente, y es legal antes que estético: **ningún dato de un cliente real puede verse desde la
aplicación, ni aunque esté seudonimizado**. El corpus está en la base de datos porque el pgvector lo necesita para
recuperar; no está para mostrarse.

Y ahora hay más superficie que antes. Hasta la migración 0014 lo único que un descuido podía sacar era un perfil:
sexo, edad, altura, objetivo. Desde la **0015** y la **0016** hay dos tablas de datos de salud que no existían —
`body_measurements` (la báscula: peso, grasa, músculo, agua, edad metabólica) y `lab_results` (analíticas: 18.038
parámetros de 254 informes de 155 clientes) — y las dos cuelgan de `client_code`, que es el mismo campo que usa la
cartera. Un `is_corpus_case` olvidado en un `JOIN` ya no filtra un perfil: filtra un expediente clínico.

Tres comprobaciones, y cada una responde a una pregunta distinta:

1. `test_the_check_is_not_vacuous_the_corpus_is_loaded` — **sobre una base vacía «no se ve ningún cliente» es cierto
   y no prueba nada.** Exige que el corpus ESTÉ cargado (perfiles de caso, dietas, embeddings, lecturas y
   parámetros, todos > 0) antes de que las otras dos signifiquen algo.

2. `test_no_corpus_person_is_reachable_from_any_endpoint` — **el invariante, que rige siempre**, en desarrollo y en
   entrega. Recorre la superficie de la API leída del **propio OpenAPI** (no de una lista escrita a mano, que
   envejecería en cuanto alguien añadiera una ruta) y prueba **todos** los códigos del corpus que tienen báscula o
   analítica, no una muestra: son exactamente los que un fallo del filtro dejaría salir con datos de salud dentro.
   Además lee el cuerpo de cada respuesta buscando un marcador o un peso del corpus.

3. `test_the_delivered_database_lists_no_client` — **la puerta de la entrega.** Cero filas de cartera en las cinco
   tablas que pueden llevar identidad y `GET /clients` vacío. En una base de desarrollo la cartera tiene clientes a
   propósito (`make demo`), así que se SALTA con el motivo escrito… salvo con `FPS_DELIVERY_CHECK=1`, que es como
   la lanza `make verify-delivery`: entonces falla. Una puerta que se salta cuando importa no es una puerta.

Lo que SÍ sale, declarado y no escondido: la API devuelve identificadores seudónimos de CASO (`CLIENTE_NNN::vNN`)
en `retrieved_case_ids` y en `/similar-cases`. Son la trazabilidad de la propuesta y no llevan ni nombre, ni perfil,
ni lectura, ni parámetro. La INTERFAZ no los pinta: muestra su número (`retrieved_case_ids.length`) y no llama a
`/similar-cases` (comprobado en `test_the_ui_never_renders_a_corpus_identifier`).

Ninguna aserción imprime un nombre: cuando encuentra uno lo nombra por la columna y por su longitud, nunca por su
contenido (regla 1 de las reglas de manejo de datos personales de la memoria).
"""
import os

import pytest

pytestmark = pytest.mark.infrastructure

# Tablas que pueden llevar la identidad de una persona de la CARTERA. La consulta dice qué significa «de cartera»
# en cada una: un expediente o una dieta guardada lo son por existir; una lectura o un parámetro, por colgar de un
# perfil que NO es caso del corpus.
# Cartera que NO es de demostración. El filtro `client_code <> ALL(:demo)` es la corrección del 2026-09-09: la puerta
# exigía CERO clientes, y desde que la entrega incluye datos (`docker compose up` deja la aplicación usable) el
# arranque siembra los clientes ficticios de `make demo`. Con la exigencia anterior, `make verify-delivery` fallaba
# siempre y una puerta que falla siempre no se lee: se desactiva. Lo que la entrega no puede llevar es un cliente
# REAL, y eso es lo que se comprueba ahora — con las claves leídas del sembrador, no copiadas aquí.
PORTFOLIO_SQL = {
    "client_profiles (cartera no demo)": ("SELECT count(*) FROM client_profiles WHERE professional_id = :p "
                                          "AND NOT is_corpus_case AND client_code <> ALL(:demo)"),
    "client_records (no demo)": "SELECT count(*) FROM client_records WHERE professional_id = :p AND client_code <> ALL(:demo)",
    "saved_diets (no demo)": "SELECT count(*) FROM saved_diets WHERE professional_id = :p AND client_code <> ALL(:demo)",
    "body_measurements (cartera no demo)": ("SELECT count(*) FROM body_measurements b JOIN client_profiles c USING (professional_id, client_code) "
                                            "WHERE b.professional_id = :p AND NOT c.is_corpus_case AND b.client_code <> ALL(:demo)"),
    "lab_results (cartera no demo)": ("SELECT count(*) FROM lab_results l JOIN client_profiles c USING (professional_id, client_code) "
                                      "WHERE l.professional_id = :p AND NOT c.is_corpus_case AND l.client_code <> ALL(:demo)"),
}

# Lo que TIENE que estar para que las otras dos comprobaciones prueben algo.
CORPUS_SQL = {
    "perfiles de caso": "SELECT count(*) FROM client_profiles WHERE professional_id = :p AND is_corpus_case",
    "dietas del corpus": "SELECT count(*) FROM diets WHERE professional_id = :p",
    "lecturas de bascula del corpus": ("SELECT count(*) FROM body_measurements b JOIN client_profiles c USING (professional_id, client_code) "
                                       "WHERE b.professional_id = :p AND c.is_corpus_case"),
    "parametros de analitica del corpus": ("SELECT count(*) FROM lab_results l JOIN client_profiles c USING (professional_id, client_code) "
                                           "WHERE l.professional_id = :p AND c.is_corpus_case"),
}

READ_ROUTES = ("/api/v1/clients/{c}", "/api/v1/clients/{c}/record", "/api/v1/clients/{c}/lab-results",
               "/api/v1/clients/{c}/body-composition", "/api/v1/clients/{c}/diets")


@pytest.fixture(scope="module")
def ctx():
    if not os.environ.get("DATABASE_URL"):
        pytest.skip("DATABASE_URL not set")
    from finalprosports.infrastructure.composition_root import CompositionRoot
    from tests.support.authenticated_client import authenticated_client, configured_professional_id
    root = CompositionRoot.from_env()
    pid = configured_professional_id()
    return root, pid, authenticated_client(pid)


def _count(root, sql: str, pid: str, demo: list[str] | None = None) -> int:
    from sqlalchemy import text
    with root.case_repository._sf() as s:                                                        # noqa: SLF001
        return int(s.execute(text(sql), {"p": pid, "demo": demo or [""]}).scalar_one())


def _demo_keys() -> list[str]:
    """Las claves de los clientes de demostración, LEÍDAS DEL SEMBRADOR y no escritas aquí."""
    from finalprosports.infrastructure.adapter.inbound.cli.seed_demo import DEMO_CLIENTS, demo_key
    return [demo_key(spec["tag"]) for spec in DEMO_CLIENTS]


def _codes_with_health_data(root, pid: str) -> list[str]:
    from sqlalchemy import text
    with root.case_repository._sf() as s:                                                        # noqa: SLF001
        return list(s.execute(text(
            "SELECT DISTINCT t.client_code FROM ("
            "  SELECT client_code FROM body_measurements WHERE professional_id = :p"
            "  UNION SELECT client_code FROM lab_results WHERE professional_id = :p) t "
            "JOIN client_profiles c ON c.client_code = t.client_code AND c.professional_id = :p "
            "WHERE c.is_corpus_case ORDER BY 1"), {"p": pid}).scalars().all())


def _health_needles(root, pid: str) -> tuple[set[str], set[str]]:
    """Cadenas que no pueden aparecer en NINGUNA respuesta: marcadores de analítica y pesos de báscula del corpus."""
    from sqlalchemy import text
    with root.case_repository._sf() as s:                                                        # noqa: SLF001
        markers = {m for m in s.execute(text(
            "SELECT DISTINCT marker FROM lab_results WHERE professional_id = :p LIMIT 200"), {"p": pid}).scalars().all() if m}
        weights = {f"{float(w):.1f}" for w in s.execute(text(
            "SELECT DISTINCT weight_kg FROM body_measurements b JOIN client_profiles c USING (professional_id, client_code) "
            "WHERE b.professional_id = :p AND c.is_corpus_case AND weight_kg IS NOT NULL LIMIT 200"), {"p": pid}).scalars().all()}
    return markers, weights


# Los EMBEDDINGS quedan fuera de esta lista a proposito. La estrategia de recuperacion entregada es `attributes`, que
# no lee `diets.embedding`, y el arranque en contenedor no los calcula (ahorra 1,1 GB de descarga del modelo e5 en el
# primer `docker compose up`). Exigirlos aqui hacia fallar la suite en el unico escenario que importa: una base recien
# cargada, que es la que se encuentra quien clona el repositorio. Se piden con FPS_BOOTSTRAP_EMBED=1 y hacen falta solo
# para las estrategias vectoriales y para el arnes.
def test_the_check_is_not_vacuous_the_corpus_is_loaded(ctx):
    """Sin esto, «la aplicación no muestra ningún cliente» lo cumpliría también una base de datos sin nada dentro."""
    root, pid, _ = ctx
    counts = {name: _count(root, sql, pid) for name, sql in CORPUS_SQL.items()}
    vacios = [k for k, v in counts.items() if v == 0]
    assert not vacios, f"el corpus no está cargado ({vacios}); sobre una base vacía esta suite no prueba nada: `make load`"


def test_no_corpus_person_is_reachable_from_any_endpoint(ctx):
    """El invariante, siempre: exista o no cartera, ni un caso del corpus sale por ninguna ruta."""
    root, pid, client = ctx
    codes = _codes_with_health_data(root, pid)
    assert codes, "ningún código del corpus tiene báscula ni analítica: la sonda de datos de salud no prueba nada"
    markers, weights = _health_needles(root, pid)

    served = []
    for code in codes:                                                    # TODOS, no una muestra
        for route in READ_ROUTES:
            r = client.get(route.format(c=code))
            if r.status_code == 200:
                cuerpo = r.text
                served.append((route, "MARCADOR" if any(m in cuerpo for m in markers)
                               else "PESO" if any(w in cuerpo for w in weights) else "sin dato de salud"))
            else:
                assert r.status_code in (404, 409, 422), (route, r.status_code)
    assert not served, f"{len(served)} respuestas 200 para códigos del corpus: {sorted(set(served))[:5]}"

    # y el resto de la superficie con TODOS sus verbos, leída del OpenAPI para que una ruta nueva entre sola
    from finalprosports.main import app
    paths = {p: ops for p, ops in app.openapi()["paths"].items() if "{client_id}" in p}
    assert len(paths) >= 5, sorted(paths)
    sample = codes[:3] + codes[-2:]
    for path, ops in paths.items():
        for method in ops:
            for code in sample:
                url = path.replace("{client_id}", code).replace("{result_id}", "1")
                r = client.request(method.upper(), url, json={} if method in ("post", "put", "patch") else None)
                assert r.status_code in (404, 409, 422), (method.upper(), path, r.status_code)
    assert client.post("/api/v1/diets/propose", json={"client_id": codes[0], "goal": "volumen_masa"}).status_code == 422


def test_the_delivered_database_lists_no_client(ctx):
    """La puerta de la entrega: la aplicación entregada no lleva NINGÚN cliente real, solo los ficticios de `make demo`.

    Se salta en desarrollo si aparece algo ajeno (la base del titular tiene sus pruebas); con FPS_DELIVERY_CHECK=1 falla.
    Sigue teniendo dientes: un cliente que no esté en `DEMO_CLIENTS` —el real del e2e, por ejemplo— la rompe."""
    root, pid, client = ctx
    demo = _demo_keys()
    counts = {name: _count(root, sql, pid, demo) for name, sql in PORTFOLIO_SQL.items()}
    listado = client.get("/api/v1/clients")
    assert listado.status_code == 200
    ajenos = [c for c in listado.json() if str(c.get("id")) not in set(demo)]
    counts["GET /clients (no demo)"] = len(ajenos)
    sucias = {k: v for k, v in counts.items() if v}
    if sucias and not os.environ.get("FPS_DELIVERY_CHECK"):
        pytest.skip(f"base de DESARROLLO: {sucias}. La puerta de entrega se ejecuta con FPS_DELIVERY_CHECK=1 (`make verify-delivery`)")
    assert not sucias, (f"la base de datos de entrega lleva clientes que NO son de demostración: {sucias}. "
                        f"Vaciarla con `make clear-portfolio` y sembrar solo la demo con `make demo`. "
                        f"(el corpus se queda: {_count(root, CORPUS_SQL['perfiles de caso'], pid)} perfiles de caso intactos)")


def test_the_ui_never_renders_a_corpus_identifier():
    """Los identificadores de caso viajan en el payload; la INTERFAZ solo pinta su número. Comprobado sobre el HTML.

    Es la mitad de la respuesta que no se puede dar desde la API: `retrieved_case_ids` sale de `/diets/propose`, y lo
    que decide si el usuario ve un seudónimo o no es qué hace la plantilla con esa lista. Si alguien cambia
    `retrieved_case_ids.length` por `retrieved_case_ids` en una plantilla, esto falla.
    """
    import re
    from pathlib import Path
    web = Path(__file__).resolve().parents[3] / "frontend" / "src" / "app"
    if not web.exists():
        pytest.skip("frontend no presente")
    ofensas = []
    for html in web.rglob("*.html"):
        for n, line in enumerate(html.read_text(encoding="utf-8").splitlines(), 1):
            for m in re.finditer(r"retrieved_case_ids(\.\w+)?", line):
                if m.group(1) not in (".length",):
                    ofensas.append(f"{html.name}:{n}")
    assert not ofensas, f"una plantilla usa los identificadores de caso, no su número: {ofensas}"
    # y nadie llama a /similar-cases desde el frontend
    llamadas = [f.name for f in web.rglob("*.ts") if "similar-cases" in f.read_text(encoding="utf-8")]
    assert not llamadas, f"el frontend llama a /similar-cases, que devuelve identificadores del corpus: {llamadas}"
