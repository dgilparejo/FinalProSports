# Calidad de la base de casos SINTÉTICA

Generado el 2026-09-09T15:51:09+00:00 por `eval.synthetic_quality`. 216 propuestas (16 clientes de demostración + 200 de la rejilla).

La pregunta no es si son las dietas del profesional —no lo son, los casos son generados—, sino si son dietas CORRECTAS. Estas son las cuatro condiciones, medidas sobre lo que el motor entrega:

| puerta | resultado |
|---|---|
| violaciones de plausibilidad (envolvente REAL del corpus) | **1** |
| violaciones de reglas tras el validador | **0** |
| alimentos vetados por la restricción declarada | **0** |
| propuestas construidas con los 20 casos pedidos | 216 de 216 |

## Forma de lo que sale

| magnitud | sintético | banda real |
|---|---|---|
| franjas por dieta (media) | 8.2 (min 5, max 11) | [3.0, 11.0] |
| ítems por franja (media / mediana / max) | 3.92 / 4.0 / 9 | p05–p95 por franja en la envolvente |
| familias distintas por franja (media / max) | 3.39 / 7 | — |

## Por objetivo

| objetivo | propuestas | plausibilidad | reglas |
|---|---|---|---|
| `ayuno_intermitente` | 59 | 0 | 0 |
| `cetosis_keto` | 2 | 1 | 0 |
| `definicion_grasa` | 78 | 0 | 0 |
| `volumen_masa` | 77 | 0 | 0 |

Estrategias usadas: {'case_based_composer': 206, 'rotation_composer': 10}.

## Las diez peores

| quién | plausibilidad | reglas | vetados |
|---|---|---|---|
| golf | 1 | 0 | 0 |
| alfa | 0 | 0 | 0 |
| bravo | 0 | 0 | 0 |
| charlie | 0 | 0 | 0 |
| delta | 0 | 0 | 0 |
| echo | 0 | 0 | 0 |
| foxtrot | 0 | 0 | 0 |
| hotel | 0 | 0 | 0 |
| india | 0 | 0 | 0 |
| julieta | 0 | 0 | 0 |

## Contra el corpus REAL, misma rejilla y misma vara

La comparación honesta no es «cero violaciones» —el sistema entregado tampoco las tiene a cero con el corpus real, y así está medido en la memoria—, es **no ser peor que él**:

| | sintético | corpus real |
|---|---|---|
| propuestas | 216 | 216 |
| violaciones de plausibilidad | **1** | 8 |
| violaciones de reglas | **0** | 0 |
| alimentos vetados servidos | **0** | 0 |
| propuestas con 20 casos | 216 | 216 |
| franjas por dieta (media) | 8.2 | 6.67 |
| ítems por franja (media) | 3.92 | 5.1 |
| familias por franja (media) | 3.39 | 3.93 |

La diferencia que queda es de FORMA y está declarada: las dietas sintéticas salen algo más anchas y menos cargadas por franja que las suyas. Las dos caen dentro de las bandas reales de la envolvente.


---

**Qué NO dice este informe.** No dice que estas dietas sean las que el profesional escribiría: los casos son generados y la fidelidad se midió contra el corpus real, que no se publica. Dice que lo que la aplicación entrega cumple su criterio: sus reglas, sus bandas de cantidad, sus franjas y sus restricciones.
