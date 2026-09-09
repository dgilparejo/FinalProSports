# `seed/` — lo que viaja con el repositorio para que la aplicación arranque sola

`docker compose up` tiene que dejar la aplicación **funcionando y con datos**, sin ningún paso manual y sin `.env`.
El motor es **basado en casos**: sin base de casos, `POST /diets/propose` devuelve `422 no_similar_cases` y no hay
nada que enseñar. Por eso el corpus viaja aquí y el servicio `bootstrap` lo carga en el primer arranque.

```
seed/dataset/     el dataset que carga el arranque (docker/bootstrap.py -> pipeline/load_postgres.py)
                  MANIFEST.json lleva el tamaño y el sha1 de cada fichero, y quién lo lee
```

## Cómo se genera, y por qué no se copia a mano

```bash
python pipeline/src/data_tools/export_seed_dataset.py            # dice qué copiaría
python pipeline/src/data_tools/export_seed_dataset.py --apply    # lo copia
python pipeline/src/data_tools/audit_tree.py                     # obligatorio después: criterio 0
```

El exportador funciona con **lista blanca**: copia solo los 19 ficheros de su `MANIFEST` y nada más, y cada entrada
dice qué componente los lee. Un `cp -r` del dataset arrastraría dos cosas que no pueden publicarse:

- **`_private/`** — `id_map.json` y `client_files_map.json` mapean a los **nombres de fichero originales**, y
  `health_profiles.jsonl` es texto clínico. El exportador lo tiene en su lista de prohibidos y **aborta** si lo
  encuentra en el destino. Es la diferencia entre un corpus seudonimizado y uno reidentificable.
- los artefactos de evaluación (`composer_per_query.jsonl` y compañía, ~10 MB) que no hacen falta para funcionar.

Con lista blanca, un fichero nuevo en el dataset **no se cuela solo**: hay que añadirlo al manifiesto a mano.

## Qué es este corpus, y qué no es

Es el corpus **real** del preparador, **seudonimizado**: los clientes son `CLIENTE_NNN` y no hay un solo nombre en el
árbol — lo comprueba `audit_tree.py` en cada ejecución, con criterio **0**, y ahora recorre también estos ficheros
porque están dentro del árbol de código.

**Seudonimizado no es anónimo, y conviene tenerlo escrito.** Medido sobre estos mismos ficheros:

| | |
|---|---|
| perfiles únicos por sexo + edad + altura | 208 / 301 = **69,1 %** |
| únicos por su conjunto exacto de fechas | 237 / 257 = **92,2 %** |
| dietas con texto libre íntegro | 1.203 / 1.203 |

Reidentificar exige una **fuente externa** que enlace esos atributos con una persona, y esa fuente es
`_private/id_map.json`, que **no está aquí** y no sale de la máquina del titular. El repositorio es **privado** por
esa razón y no por costumbre.

## Cómo se usa

El compose enlaza este directorio en `/dataset` **de solo lectura** y el arranque carga desde ahí:

```yaml
source: ${FPS_DATASET_DIR:-./seed/dataset}   # sin .env -> este corpus; con .env -> el dataset de trabajo
target: /dataset
read_only: true
```

En la máquina del titular el `.env` apunta al dataset de trabajo (`FPS_DATASET_DIR`) y el mismo compose usa ese en su
lugar, sin tocar nada. `:ro` porque ni el arranque ni la API escriben en el corpus: quien escribe en el dataset son
los arneses de evaluación, y esos corren en el host.

## Los embeddings NO están, y no es un olvido

`diets.embedding` se queda a `NULL`. La estrategia de recuperación entregada es `attributes`, cuyo
`requires_embedding` es `False`: la columna **no la lee nadie** en la configuración que se entrega. Calcularla
obligaría a descargar 1,1 GB del modelo e5 en el primer arranque para llenar algo que la aplicación no consulta. Se
piden con `FPS_BOOTSTRAP_EMBED=1`, que es lo que hace falta para las estrategias `vector` e `hybrid` y para el arnés.
