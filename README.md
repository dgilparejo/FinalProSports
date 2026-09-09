# finalprosports

Asistente de prescripción dietética **basado en casos**, construido por ingeniería inversa sobre el trabajo de un
preparador físico: recupera los casos más parecidos por atributos, compone una propuesta por consenso, rota la versión
anterior de un cliente recurrente y la valida con las reglas del profesional. TFM del Máster en Ingeniería de Software
(UNIR).

## Arranque: un comando

```bash
git clone https://github.com/dgilparejo/FinalProSports.git && cd FinalProSports
docker compose up -d --build          # ~8 min la primera vez; después, segundos
```

Y ya está: **http://localhost:4200**, con datos y con dieciséis clientes de demostración. No hace falta `.env`, ni
Python, ni Node, ni ejecutar migraciones a mano. Entra con `entrenador` / `entrenador`.

Cinco servicios, y el orden lo impone el propio compose (`db` → `bootstrap` → `api` → `web`): PostgreSQL 16 +
pgvector, Keycloak (importa el realm con el rol y los usuarios de prueba), un servicio de arranque de un solo uso que
migra, carga los datos y siembra la demostración, la API FastAPI y un nginx que sirve el SPA y hace de proxy.

### Recorrido de tres pasos hasta un PDF

1. **Clientes** — los dieciséis de demostración, con expediente, báscula y analítica.
2. Abre uno y **genera la propuesta**: 20 casos recuperados, franjas con sus alternativas, cantidades en gramos, notas
   por tema y el panel de evidencia con las reglas que se aplicaron.
3. **Guarda** y **exporta el PDF** (o el ODT). Pídele otra al mismo cliente y verás la **rotación** contra su versión
   anterior.

## Lo que estos datos son, y lo que no

Esto importa más que cualquier otra cosa del repositorio, así que va antes que la arquitectura.

El sistema se construyó y se midió sobre un corpus real: **467 clientes y 1.183 dietas** de un preparador físico, con
báscula y analíticas. Ese corpus **no se publica y no está aquí**. Son datos de salud de personas reales (art. 9 RGPD)
y, aunque estén seudonimizados, siguen siendo identificables: medido sobre él, **96,4 %** de los perfiles son únicos
por sexo + edad + altura + fecha de primera consulta, y **94,2 %** por su conjunto de fechas de pesaje.

Lo que sí viaja en este repositorio son dos cosas distintas:

| | qué es | de dónde sale |
|---|---|---|
| **El criterio** | 228 alimentos canónicos con sus banderas, **31 reglas** validadas, **223 bandas** de cantidad p05/p50/p95 (n≥10), 14 temas de notas canónicas (soporte ≥15 dietas), pares de alternativas y colocación de suplementos | **REAL**: minado del corpus. Son agregados: ninguna fila por persona |
| **La base de casos** | 300 clientes, ~830 dietas, báscula y analíticas | **SINTÉTICA**: generada con `pipeline/src/data_tools/synthesize_case_base.py` a partir de ese criterio. Los casos se llaman `SINT_NNN`, nunca `CLIENTE_NNN` |

Los dieciséis clientes de demostración son **inventados** (nombres con «Demo», teléfonos con un prefijo que ningún
número español tiene, correos bajo el TLD reservado `.invalid`).

### Qué significa eso para lo que la aplicación entrega

Las dietas que verás **son correctas**: cumplen sus reglas, caen dentro de sus bandas de cantidad, respetan las
restricciones duras y llevan sus notas. Medido sobre 216 propuestas (`docs/evaluation/SYNTHETIC_QUALITY.md`):

```
violaciones de reglas tras el validador ............  0
alimentos vetados por la restricción declarada .....  0
violaciones de plausibilidad .......................  1   (con el corpus REAL, misma rejilla: 8)
propuestas construidas con los 20 casos pedidos ....  216 de 216
```

Lo que **no** se puede hacer desde este repositorio es reproducir la evaluación de la memoria (Jaccard contra las
dietas reales, arnés leave-one-out, `RESULTS.md`, `DISCUSSION.md`): esas cifras se midieron contra el corpus, que no
está aquí. Las suites que lo necesitan están marcadas y no corren. **No son sus dietas; son dietas construidas con su
criterio**, y la diferencia está declarada en cada informe.

Y una nota que evita un malentendido fácil: ni con el corpus real existe «la dieta única». Partiéndolo en dos mitades
y pidiendo la dieta del mismo cliente con cada una, la coincidencia de alimentos es 0,593 y la de familias 0,721 — el
propio profesional, con la misma persona, se repite menos que eso.

## Componentes

| Carpeta | Qué es |
|---|---|
| `backend/` | API FastAPI con arquitectura hexagonal (`domain` → `application` → `infrastructure`), migraciones Alembic, arnés de evaluación y tests. Contratos de capa verificados con import-linter y con tests AST |
| `frontend/` | Angular 21 (standalone + señales, envoltorios propios sobre Material, i18n): clientes, alta, expediente, propuesta editable con evidencia, dieta guardada con *diff* y PDF |
| `pipeline/` | ETL del corpus y herramientas de datos: exportador público con lista blanca, derivador de parámetros y generador de la base de casos sintética |
| `docs/` | decisiones de arquitectura, informes de datos y evaluación |
| `seed/dataset/` | el criterio agregado (real) + la base de casos (sintética) |

## Credenciales de prueba (locales)

Son credenciales de un despliegue local, en claro a propósito para que un clon limpio funcione sin pasos manuales. No
sirven fuera de esa máquina y no deben reutilizarse en ningún entorno real.

| usuario | contraseña | rol | para qué |
|---|---|---|---|
| `entrenador` | `entrenador` | `entrenador` | el usuario de trabajo |
| `sinrol` | `sinrol` | ninguno | comprobar que la API responde **403** a un token válido sin el rol |
| `admin` | `admin` | admin de Keycloak | consola en http://localhost:8080 (solo local) |

## Calidad

```bash
make test            # tests que no necesitan pytest ni base de datos (arquitectura, dominio, aplicación)
make lint            # contratos de capas (import-linter) + AST
make test-infra      # pytest contra la base de datos: humo, no exposición, PDF
make golden          # dietas modelo: envolvente de plausibilidad + instantáneas
make public-check    # LA PUERTA: ningún dato personal en el árbol, buscado por FORMA y no por nombre
make public-quality  # vuelve a medir si las dietas salen bien y reescribe SYNTHETIC_QUALITY.md
make web-test        # specs de Angular
```

`make public-check` merece una frase: no busca nombres, busca **formas** de dato personal (filas con `client_code`,
expedientes con identidad y salud, seudónimos del corpus). Se escribió porque la auditoría por diccionario de nombres
tenía un punto ciego —un expediente real con la identidad cambiada la pasaba— y en un repositorio público eso no es un
detalle.

## Licencia

Código: **PolyForm Noncommercial 1.0.0** (uso no comercial). Documentos: **CC BY-NC-ND 4.0**. Ver `LICENSE`.

La marca y el logotipo de Final Pro Sports aparecen con permiso de su titular. El corpus con el que se construyó el
sistema no se publica ni se licencia.
