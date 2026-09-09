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

RNF-08: la API NO devuelve ningún identificador del corpus. Los `CLIENTE_NNN::vNN` no salen del servidor — ni en el
campo de trazabilidad de la propuesta, ni en la evidencia por alimento, ni en `/similar-cases`. Lo que la interfaz
recibe es el RECUENTO: cuántos de los k casos respaldan cada alimento y cuántos clientes distintos son
(comprobado sobre el JSON servido, en profundidad y por la FORMA de la cadena, en
`test_the_ui_never_renders_a_corpus_identifier`).

Ninguna aserción imprime un nombre: cuando encuentra uno lo nombra por la columna y por su longitud, nunca por su
contenido (regla 1 de las reglas de manejo de datos personales de la memoria).
"""
import os
import re

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


# ---------------------------------------------------------------------------------------------------------------- #
# RNF-08 · LA FORMA, NO EL NOMBRE DEL CAMPO.                                                                        #
# El control anterior vigilaba UN campo (`retrieved_case_ids`) y excluía a propósito el de la evidencia por          #
# alimento, así que pasaba en verde mientras la pantalla pintaba 312 identificadores del corpus por otra ruta.       #
# El criterio ahora es la FORMA de la cadena, se busque donde se busque: cualquier identificador con forma de caso   #
# del corpus, en cualquier profundidad de cualquier respuesta de la API, la rompe — incluida una cuarta ruta que     #
# nadie ha escrito todavía.                                                                                         #
# ---------------------------------------------------------------------------------------------------------------- #
UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.IGNORECASE)
# `EJEMPLO_007`: un seudónimo del corpus es un token en mayúsculas con sufijo numérico. La cartera no tiene ninguno:
# su clave es un UUID y su nombre es un nombre.
PSEUDONYM_RE = re.compile(r"[A-Z][A-Z_]{2,}_\d{1,6}")
TOKEN_RE = re.compile(r"[A-Za-z0-9_:.-]+")


def corpus_shaped(value: str) -> str | None:
    """El token con forma de identificador del corpus que haya en `value`, o None.

    Dos formas, y ninguna mira el nombre del campo:
      · `algo::algo` cuyo lado izquierdo NO es un UUID — un id de caso (`EJEMPLO_007::v03`). Las dietas de la
        cartera son `<uuid>::eNN` y sus versiones `<uuid>::vNN`, así que el UUID es lo que las distingue.
      · un seudónimo suelto (`EJEMPLO_007`), que es como viaja un código de caso sin versión.
    """
    for token in TOKEN_RE.findall(value):
        if "::" in token and not UUID_RE.match(token.split("::", 1)[0]):
            return token
        if PSEUDONYM_RE.fullmatch(token):
            return token
    return None


def _strings(node, path: str = "$"):
    """Recorrido en PROFUNDIDAD: toda cadena del JSON con la ruta en la que aparece."""
    if isinstance(node, str):
        yield path, node
    elif isinstance(node, dict):
        for k, v in node.items():
            yield from _strings(v, f"{path}.{k}")
    elif isinstance(node, list):
        for i, v in enumerate(node):
            yield from _strings(v, f"{path}[{i}]")


def _offences(label: str, payload) -> list[str]:
    out = []
    for path, s in _strings(payload):
        hit = corpus_shaped(s)
        if hit:
            out.append(f"{label} {path} -> {hit}")
    return out


def test_the_criterion_is_not_vacuous():
    """Si el criterio no dispara con un identificador del corpus puesto a mano, el control no vale nada.

    Los seudonimos de aqui son INVENTADOS (`EJEMPLO_NNN`), no codigos del corpus, y da igual: el criterio es la
    FORMA de la cadena. Poner uno real seria publicar informacion de una persona en el arbol publico -- un
    `::v03` dice que esa persona tiene al menos tres dietas, que es justo lo que el montador se molesta en
    borrar de los `.md` que publica (`tools/build_public_tree.sh`, paso 3d)."""
    assert corpus_shaped("EJEMPLO_007::v03") == "EJEMPLO_007::v03"
    assert corpus_shaped("EJEMPLO_012") == "EJEMPLO_012"
    assert corpus_shaped('["EJEMPLO_031::v02", "EJEMPLO_115::v01"]') == "EJEMPLO_031::v02"
    # ...y si dispara con lo que la aplicación sí puede servir, tampoco: sería un control que obliga a relajarlo.
    for legitimo in ("a6f0f814-f446-5944-b614-ce6a7b257008", "a6f0f814-f446-5944-b614-ce6a7b257008::e01",
                     "a6f0f814-f446-5944-b614-ce6a7b257008::v02", "volumen_masa", "agua_2.5L", "ayuno_16h",
                     "contains_gluten", "0a9e9dc9d703e8d5", "1990-06-15", "60 gr Avena", "Nora Ficticia Demo",
                     "cold_start", "case_based_composer", "copy_top1_empty_consensus"):
        assert corpus_shaped(legitimo) is None, legitimo


@pytest.fixture
def cliente_propio(ctx):
    """Un cliente de cartera REGISTRADO POR LA PRUEBA y borrado al salir, con su dieta guardada.

    Las dos comprobaciones que siguen necesitan una propuesta de verdad, y la primera versión las apoyó en los
    clientes de `make demo`. Eso las ataba al sembrador, y en un clon limpio la suite de infraestructura corre ANTES
    de `make demo`: la cartera está vacía, y el control fallaba por falta de datos, que es la otra manera de no
    comprobar nada (puerta de clon limpio, 2026-09-09). Así que se registra el suyo por la API, ejercita las DOS
    ramas del enrutado — arranque en frío y, con la versión guardada por delante, rotación — y lo borra en el
    `finally`, que es lo que la puerta de entrega exige: la cartera no puede quedar con un cliente que no es demo.
    """
    root, pid, client = ctx
    r = client.post("/api/v1/clients", json={"full_name": "Prueba Rnf08 Demo", "birth_date": "1992-03-11", "sex": "M",
                                             "height_cm": 178, "activity_level": 4, "goal": "volumen_masa"})
    assert r.status_code == 201, r.text
    cid = r.json()["id"]
    try:
        yield client, cid, "volumen_masa"
    finally:
        root.client_repository.delete(pid, cid)             # arrastra dietas guardadas, expediente, báscula y analítica
        assert root.client_repository.get(pid, cid) is None


def test_the_ui_never_renders_a_corpus_identifier(ctx, cliente_propio):
    """RNF-08 · NINGUNA respuesta de la API lleva un identificador del corpus, en ninguna parte de su JSON.

    No basta con que la plantilla no lo pinte: un payload que lo contiene lo expone igual — queda en la pestaña de
    red y en la memoria del navegador. Así que se comprueba en el ORIGEN, sobre el JSON servido, recorrido en
    profundidad, y el criterio es la forma de la cadena (`corpus_shaped`) y no el nombre del campo.
    """
    client, cid, goal = cliente_propio
    ofensas: list[str] = []
    ofensas += _offences("GET /clients", client.get("/api/v1/clients").json())
    ofensas += _offences("GET /rules", client.get("/api/v1/rules").json())
    ofensas += _offences("GET /catalog/foods", client.get("/api/v1/catalog/foods").json())
    # retrieval puro: es la ruta que devolvía `diet_id` por diseño
    ofensas += _offences("POST /similar-cases", client.post("/api/v1/similar-cases",
                                                            json={"sex": "M", "age": 30, "height_cm": 178, "activity_level": 4,
                                                                  "goal": "volumen_masa", "k": 8}).json())
    for ruta in ("/api/v1/clients/{c}", "/api/v1/clients/{c}/record", "/api/v1/clients/{c}/lab-results",
                 "/api/v1/clients/{c}/body-composition", "/api/v1/clients/{c}/diets"):
        r = client.get(ruta.format(c=cid))
        assert r.status_code == 200, (ruta, r.status_code)
        ofensas += _offences(f"GET {ruta}", r.json())

    # (a) arranque en frío: el consenso de los k casos, que es donde vivía la evidencia por alimento
    r = client.post("/api/v1/diets/propose", json={"client_id": cid, "goal": goal})
    assert r.status_code == 200, r.text
    fria = r.json()
    assert fria["routing"]["previous_version"] is None, "el cliente acaba de registrarse: no puede tener versión anterior"
    ofensas += _offences("POST /diets/propose (arranque en frío)", fria)

    # (b) la vuelta completa: guardar lo que el navegador puede devolver y volver a leerlo
    cuerpo = {k: v for k, v in fria.items() if k in ("profile", "strategy", "parameters", "meals", "notes", "validation")}
    r = client.post("/api/v1/diets", json={**cuerpo, "edited": False, "original": cuerpo})
    assert r.status_code == 201, r.text
    guardada = r.json()
    ofensas += _offences("POST /diets", guardada)
    r = client.get(f"/api/v1/diets/{guardada['id']}")
    assert r.status_code == 200, r.text
    ofensas += _offences("GET /diets/{id}", r.json())

    # (c) y la otra rama del enrutado: con la versión guardada por delante, la propuesta rota sobre ella
    r = client.post("/api/v1/diets/propose", json={"client_id": cid, "goal": goal})
    assert r.status_code == 200, r.text
    rotada = r.json()
    assert rotada["routing"]["previous_version"] == guardada["id"], rotada["routing"]
    ofensas += _offences("POST /diets/propose (rotación)", rotada)

    assert not ofensas, (f"{len(ofensas)} identificadores del corpus en la respuesta de la API "
                         f"(el navegador los recibe, se pinten o no):\n  - " + "\n  - ".join(ofensas[:15]))


def test_the_explainability_panel_survives_the_scrub(ctx, cliente_propio):
    """RF-09 · quitar los identificadores no deja al panel sin qué explicar.

    El requisito pide, PARA CADA ALIMENTO, tres cosas: en cuántos de los casos recuperados aparecía, qué reglas lo
    respaldan y su respaldo. Las tres siguen en la respuesta después de la proyección — la primera pasa de ser una
    lista de seudónimos a ser el número, que es lo que la pantalla pintaba ya («aparece en 15 de 20 casos»), más
    cuántos clientes distintos son, que antes no se daba.
    """
    client, cid, goal = cliente_propio
    r = client.post("/api/v1/diets/propose", json={"client_id": cid, "goal": goal})
    assert r.status_code == 200, r.text
    p = r.json()

    assert isinstance(p["retrieved_cases"], int) and p["retrieved_cases"] > 0                     # el total sobre el que se cuenta
    assert isinstance(p["retrieved_clients"], int) and p["retrieved_clients"] > 0
    opciones = [o for m in p["meals"] for g in m["groups"] for o in g["options"]]
    assert opciones, "una propuesta sin alimentos no prueba nada del panel"
    for o in opciones:
        ev = o["evidence"]
        assert set(ev) == {"support", "case_count", "client_count", "rules"}, ev.keys()
        assert isinstance(ev["case_count"], int) and 0 <= ev["case_count"] <= p["retrieved_cases"]
        assert 0 <= ev["client_count"] <= ev["case_count"]                                        # un caso, un cliente como máximo
        assert isinstance(ev["support"], (int, float)) and 0.0 <= ev["support"] <= 1.0
        assert isinstance(ev["rules"], list)
    # y el panel tiene algo que decir de verdad: hay alimentos respaldados por casos y alimentos respaldados por reglas
    assert any(o["evidence"]["case_count"] > 0 for o in opciones), "ningún alimento cita un caso: el panel quedaría vacío"
    assert any(o["evidence"]["rules"] for o in opciones), "ninguna regla respalda a ningún alimento"
    assert p["validation"] and p["validation"]["compliance"] is not None


def test_no_template_reaches_for_a_case_identifier():
    """La otra mitad: los dos campos que llevaban los ids ya no existen, y ninguna plantilla puede volver a pedirlos."""
    from pathlib import Path
    web = Path(__file__).resolve().parents[3] / "frontend" / "src" / "app"
    if not web.exists():
        pytest.skip("frontend no presente")
    ofensas = []
    for f in list(web.rglob("*.html")) + list(web.rglob("*.ts")):
        for n, line in enumerate(f.read_text(encoding="utf-8").splitlines(), 1):
            for campo in ("retrieved_case_ids", "evidence.cases", "similar-cases"):
                if campo in line:
                    ofensas.append(f"{f.name}:{n} ({campo})")
    assert not ofensas, ("el frontal pide un campo que la API ya no sirve, o llama al endpoint de recuperación "
                        f"pura: {ofensas}")
