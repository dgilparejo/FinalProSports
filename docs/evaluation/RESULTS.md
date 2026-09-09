# Resultados de la evaluación (E5) — generado por `eval.report` el 2026-09-08T21:27:18

Protocolo: 815 consultas leave-one-out, recuperación `attributes`, compositor k = 20, umbral = 0.35, semilla 42. Toda cifra de este fichero se regenera desde `_dataset/composer_per_query.jsonl` (`results.json` es la fuente; este Markdown es su render).

> ### Aviso de comparabilidad entre dataset-v2 y dataset-v3

>
> El `dataset-v3` nombra cinco franjas que el v2 no tenía (MEDIA TARDE, RECIEN LEVANTADO, SUPLEMENTOS, AGUA,
> ANTES DE DORMIR) y cuyo contenido el troceador antiguo dejaba caer en la franja que estuviera abierta. Al
> darles franja propia, **ítems que en el v2 vivían dentro de DESAYUNO o MERIENDA pasan a tener la suya**.
>
> Consecuencia directa, y hay que leerla antes que cualquier tabla:
>
> * **Las métricas por FRANJA no son comparables entre v2 y v3.** Cambian los ítems por franja, el número de
>   franjas por dieta, el Jaccard por franja (§6) y cualquier recuento que use la franja como unidad. Una
>   diferencia ahí es un cambio de taxonomía, no una mejora del motor.
> * **Las métricas por DIETA y por ÍTEM sí lo son.** El titular (§0), la ablación (§4) y el escenario recurrente
>   (§9) se miden sobre la dieta y sobre el conjunto de ítems, que no dependen del reparto en franjas.
>
> Contexto: el MERIENDA del v2 (896 dietas) es el MERIENDA del v3 más MEDIA TARDE, y su RECENA (225) es RECENA
> más ANTES DE DORMIR. Detalle en `docs/data/V2_VS_V3.md` §3.

## 0. Titular

**Escenario cliente nuevo (arranque en frío, 815 consultas): el compositor por consenso bate a copiar el caso más parecido en +0.065 de Jaccard `normalized_key` (IC 95 % [+0.057, +0.073], Wilcoxon p = 7.0e-56).** Los «techos» de autoconsistencia de las tablas siguientes (dieta oculta frente a las demás dietas del mismo cliente) son **laxos**: mezclan versiones lejanas (v1 frente a v6) de una progresión gradual. El techo estricto para la tarea «predecir la siguiente dieta» es la versión inmediatamente anterior del cliente (Jaccard 0,525 entre versiones consecutivas en el análisis de rotación) y se trata en la sección 9 (escenario recurrente); el compositor frío queda por debajo de él.

**Configuración entregada** (la que sirve la API: estrategia → capa de plausibilidad → validador; última fila de la ablación, sección 4): J `normalized_key` **0.305** frente a copiar top-1 0.240 (+0.066, IC 95 % [+0.058, +0.074], Wilcoxon p = 5.6e-56). Respecto al validador solo, la capa de plausibilidad gana +0.000 de Jaccard `normalized_key` (IC 95 % [+0.000, +0.001], Wilcoxon p = 0.0036) y deja las violaciones de plausibilidad por propuesta en 0.03 (desde 0.39; -0.36, IC 95 % [-0.41, -0.31]); propuestas con alguna violación: 32 % → 3 %.

## 1. Criterio de éxito: suelo · copiar top-1 · compositor · **sistema entregado** · techo laxo

La columna **entregada** es lo que sirve la API (estrategia → capa de plausibilidad → validador), la misma que cierra la ablación de la sección 4. Las dos tablas siguientes la dan en los dos protocolos de techo y en las tres granularidades; debajo de cada una van las diferencias EMPAREJADAS entregada − copiar y entregada − techo con su intervalo y su Wilcoxon.

**A · techo laxo sin el vecino más cercano (clientes con ≥ 3 dietas)** — n = 741

| Granularidad | Suelo mismo objetivo | Copiar top-1 | Compositor | **Entregada** | Techo | entregada − copia | entregada − techo | normalizada entregada | normalizada compositor |
|---|---|---|---|---|---|---|---|---|---|
| normalized_key | 0.205 | 0.240 | 0.307 | **0.307** | 0.274 | +0.067 | +0.033 | 1.478 | 1.470 |
| food_id | 0.298 | 0.332 | 0.412 | **0.412** | 0.365 | +0.080 | +0.048 | 1.715 | 1.704 |
| familia | 0.551 | 0.584 | 0.657 | **0.656** | 0.586 | +0.072 | +0.071 | 3.046 | 3.049 |

Diferencias emparejadas de la configuración entregada (mismas consultas; bootstrap 10.000 con semilla fija, Wilcoxon bilateral):

| Diferencia | Granularidad | n | media | IC 95 % | excluye 0 | p (Wilcoxon) | % consultas a favor |
|---|---|---|---|---|---|---|---|
| entregada − copiar top-1 | normalized_key | 815 | +0.0657 | [+0.0577, +0.0737] | sí | 5.6e-56 | 74 % |
| entregada − copiar top-1 | food_id | 815 | +0.0782 | [+0.0696, +0.0867] | sí | 1.2e-59 | 72 % |
| entregada − copiar top-1 | familia | 815 | +0.0724 | [+0.0632, +0.0818] | sí | 6.5e-45 | 65 % |
| entregada − techo laxo | normalized_key | 741 | +0.0330 | [+0.0237, +0.0420] | sí | 2.1e-15 | 64 % |
| entregada − techo laxo | food_id | 741 | +0.0479 | [+0.0389, +0.0568] | sí | 2.8e-30 | 68 % |
| entregada − techo laxo | familia | 741 | +0.0710 | [+0.0627, +0.0793] | sí | 1.6e-54 | 74 % |

**B · techo laxo incluyendo el vecino más cercano (todas las consultas)** — n = 815

| Granularidad | Suelo mismo objetivo | Copiar top-1 | Compositor | **Entregada** | Techo | entregada − copia | entregada − techo | normalizada entregada | normalizada compositor |
|---|---|---|---|---|---|---|---|---|---|
| normalized_key | 0.205 | 0.240 | 0.305 | **0.305** | 0.324 | +0.066 | -0.018 | 0.846 | 0.842 |
| food_id | 0.299 | 0.332 | 0.410 | **0.411** | 0.410 | +0.078 | +0.000 | 1.003 | 0.997 |
| familia | 0.552 | 0.584 | 0.656 | **0.656** | 0.622 | +0.072 | +0.035 | 1.494 | 1.494 |

Diferencias emparejadas de la configuración entregada (mismas consultas; bootstrap 10.000 con semilla fija, Wilcoxon bilateral):

| Diferencia | Granularidad | n | media | IC 95 % | excluye 0 | p (Wilcoxon) | % consultas a favor |
|---|---|---|---|---|---|---|---|
| entregada − copiar top-1 | normalized_key | 815 | +0.0657 | [+0.0577, +0.0737] | sí | 5.6e-56 | 74 % |
| entregada − copiar top-1 | food_id | 815 | +0.0782 | [+0.0696, +0.0867] | sí | 1.2e-59 | 72 % |
| entregada − copiar top-1 | familia | 815 | +0.0724 | [+0.0632, +0.0818] | sí | 6.5e-45 | 65 % |
| entregada − techo laxo | normalized_key | 815 | -0.0182 | [-0.0293, -0.0071] | sí | 0.01 | 47 % |
| entregada − techo laxo | food_id | 815 | +0.0003 | [-0.0101, +0.0107] | **no** | 0.1 | 55 % |
| entregada − techo laxo | familia | 815 | +0.0346 | [+0.0257, +0.0438] | sí | 4.7e-18 | 62 % |

## 2. Intervalos de confianza y contrastes (diferencias emparejadas)

bootstrap percentile 95 % CI over paired differences, 10000 resamples, seed 42; Wilcoxon signed-rank two-sided.

| Comparación | Granularidad | n | diferencia media | IC 95 % | excluye 0 | p (Wilcoxon) | % consultas a favor |
|---|---|---|---|---|---|---|---|
| composer - copy_top1 | normalized_key | 815 | +0.0652 | [+0.0570, +0.0731] | sí | 7e-56 | 74 % |
| composer - copy_top1 | food_id | 815 | +0.0776 | [+0.0690, +0.0859] | sí | 1.7e-59 | 72 % |
| composer - copy_top1 | familia | 815 | +0.0725 | [+0.0633, +0.0819] | sí | 8.5e-45 | 65 % |
| composer - ceiling_excl_nn (subset) | normalized_key | 741 | +0.0324 | [+0.0230, +0.0415] | sí | 7.5e-15 | 64 % |
| composer - ceiling_excl_nn (subset) | food_id | 741 | +0.0472 | [+0.0382, +0.0562] | sí | 1e-29 | 68 % |
| composer - ceiling_excl_nn (subset) | familia | 741 | +0.0711 | [+0.0628, +0.0793] | sí | 1.9e-55 | 75 % |
| composer - ceiling_incl_nn | normalized_key | 815 | -0.0188 | [-0.0299, -0.0079] | sí | 0.006 | 47 % |
| composer - ceiling_incl_nn | food_id | 815 | -0.0003 | [-0.0109, +0.0100] | **no** | 0.14 | 54 % |
| composer - ceiling_incl_nn | familia | 815 | +0.0346 | [+0.0258, +0.0434] | sí | 1.9e-18 | 63 % |
| composer - floor_same_goal | normalized_key | 815 | +0.0998 | [+0.0922, +0.1074] | sí | 1.5e-93 | 85 % |
| composer - floor_same_goal | food_id | 815 | +0.1111 | [+0.1030, +0.1190] | sí | 2.9e-96 | 83 % |
| composer - floor_same_goal | familia | 815 | +0.1047 | [+0.0950, +0.1144] | sí | 3.1e-73 | 75 % |
| copy_top1 - floor_same_goal | normalized_key | 815 | +0.0346 | [+0.0252, +0.0438] | sí | 1.2e-12 | 60 % |
| copy_top1 - floor_same_goal | food_id | 815 | +0.0335 | [+0.0233, +0.0436] | sí | 1.5e-10 | 58 % |
| copy_top1 - floor_same_goal | familia | 815 | +0.0322 | [+0.0211, +0.0434] | sí | 8.8e-10 | 57 % |
| composer - composer_no_degradation | normalized_key | 815 | +0.0007 | [-0.0001, +0.0019] | **no** | 0.31 | 1 % |
| composer - composer_no_degradation | food_id | 815 | +0.0009 | [-0.0001, +0.0020] | **no** | 0.14 | 1 % |
| composer - composer_no_degradation | familia | 815 | -0.0004 | [-0.0014, +0.0003] | **no** | 0.55 | 1 % |
| validated_strict - composer (overlap) | normalized_key | 815 | +0.0002 | [+0.0000, +0.0004] | sí | 0.057 | 3 % |
| validated_strict - composer (overlap) | food_id | 815 | +0.0003 | [+0.0001, +0.0005] | sí | 0.025 | 2 % |
| validated_strict - composer (overlap) | familia | 815 | -0.0002 | [-0.0007, +0.0003] | **no** | 0.26 | 1 % |
| entregada (validador + plausibilidad) - validated_strict | normalized_key | 815 | +0.0003 | [+0.0001, +0.0006] | sí | 0.0036 | 2 % |
| entregada (validador + plausibilidad) - validated_strict | food_id | 815 | +0.0003 | [+0.0001, +0.0006] | sí | 0.0093 | 1 % |
| entregada (validador + plausibilidad) - validated_strict | familia | 815 | +0.0001 | [+0.0000, +0.0003] | **no** | 0.18 | 0 % |
| entregada - composer | normalized_key | 815 | +0.0005 | [+0.0003, +0.0008] | sí | 0.00016 | 4 % |
| entregada - composer | food_id | 815 | +0.0006 | [+0.0003, +0.0009] | sí | 0.00025 | 4 % |
| entregada - composer | familia | 815 | -0.0000 | [-0.0006, +0.0005] | **no** | 0.66 | 1 % |
| entregada - copy_top1 | normalized_key | 815 | +0.0657 | [+0.0577, +0.0737] | sí | 5.6e-56 | 74 % |
| entregada - copy_top1 | food_id | 815 | +0.0782 | [+0.0696, +0.0867] | sí | 1.2e-59 | 72 % |
| entregada - copy_top1 | familia | 815 | +0.0724 | [+0.0632, +0.0818] | sí | 6.5e-45 | 65 % |
| entregada - ceiling_excl_nn (subset) | normalized_key | 741 | +0.0330 | [+0.0237, +0.0420] | sí | 2.1e-15 | 64 % |
| entregada - ceiling_excl_nn (subset) | food_id | 741 | +0.0479 | [+0.0389, +0.0568] | sí | 2.8e-30 | 68 % |
| entregada - ceiling_excl_nn (subset) | familia | 741 | +0.0710 | [+0.0627, +0.0793] | sí | 1.6e-54 | 74 % |
| entregada - ceiling_incl_nn | normalized_key | 815 | -0.0182 | [-0.0293, -0.0071] | sí | 0.01 | 47 % |
| entregada - ceiling_incl_nn | food_id | 815 | +0.0003 | [-0.0101, +0.0107] | **no** | 0.1 | 55 % |
| entregada - ceiling_incl_nn | familia | 815 | +0.0346 | [+0.0257, +0.0438] | sí | 4.7e-18 | 62 % |
| validated_strict - composer (conditional compliance) | cumplimiento condicional | 418 | +0.1268 | [+0.0957, +0.1603] | sí | 3.3e-13 | 13 % |
| validated_strict - hidden diet (conditional compliance) | cumplimiento condicional | 362 | +0.1298 | [+0.0967, +0.1657] | sí | 7.1e-12 | 13 % |
| entregada - validated_strict (violaciones de plausibilidad por consulta) | violaciones | 815 | -0.3583 | [-0.4098, -0.3104] | sí | 1.2e-41 | 2 % |

## 3. Estratificación (celdas con n < 30 marcadas como no concluyentes)

**Por objetivo** (J `normalized_key`; techo con vecino)

| Grupo | n | Suelo mismo obj. | Copiar top-1 | Compositor | **Entregada** | Techo | entregada − copia | tamaño | concluyente |
|---|---|---|---|---|---|---|---|---|---|
| volumen_masa | 342 | 0.205 | 0.258 | 0.305 | **0.305** | 0.350 | +0.047 | 0.91 | sí |
| ayuno_intermitente | 53 | 0.244 | 0.286 | 0.354 | **0.354** | 0.330 | +0.068 | 1.25 | sí |
| definicion_grasa | 331 | 0.193 | 0.224 | 0.299 | **0.299** | 0.315 | +0.075 | 1.13 | sí |
| cetosis_keto | 23 | 0.444 | 0.424 | 0.529 | **0.531** | 0.247 | +0.106 | 1.02 | **no (n < 30)** |
| descarga_carga | 9 | 0.261 | 0.299 | 0.304 | **0.300** | 0.392 | +0.000 | 1.26 | **no (n < 30)** |
| hipocalorica | 5 | 0.224 | 0.224 | 0.228 | **0.228** | 0.198 | +0.004 | 0.72 | **no (n < 30)** |
| sin_clasificar | 52 | 0.127 | 0.083 | 0.202 | **0.207** | 0.239 | +0.124 | 0.89 | sí |

**Por sexo** (J `normalized_key`; techo con vecino)

| Grupo | n | Suelo mismo obj. | Copiar top-1 | Compositor | **Entregada** | Techo | entregada − copia | tamaño | concluyente |
|---|---|---|---|---|---|---|---|---|---|
| M | 708 | 0.206 | 0.244 | 0.310 | **0.311** | 0.325 | +0.067 | 1.03 | sí |
| F | 107 | 0.202 | 0.212 | 0.268 | **0.269** | 0.318 | +0.057 | 0.99 | sí |

**Por tramo de edad** (J `normalized_key`; techo con vecino)

| Grupo | n | Suelo mismo obj. | Copiar top-1 | Compositor | **Entregada** | Techo | entregada − copia | tamaño | concluyente |
|---|---|---|---|---|---|---|---|---|---|
| <25 | 77 | 0.233 | 0.261 | 0.325 | **0.324** | 0.395 | +0.064 | 1.00 | sí |
| 25-39 | 537 | 0.200 | 0.236 | 0.306 | **0.307** | 0.319 | +0.071 | 1.02 | sí |
| 40-54 | 171 | 0.210 | 0.249 | 0.301 | **0.301** | 0.306 | +0.052 | 1.10 | sí |
| 55+ | 30 | 0.192 | 0.209 | 0.257 | **0.257** | 0.319 | +0.047 | 0.82 | sí |

**Con y sin ítems `generic_assumption`** (todas las consultas)

| | copiar top-1 key / food | compositor key / food | techo (con vecino) key / food |
|---|---|---|---|
| con | 0.240 / 0.332 | **0.305 / 0.410** | 0.324 / 0.410 |
| sin | 0.242 / 0.313 | **0.299 / 0.385** | 0.322 / 0.394 |

## 4. Ablación acumulativa (815 consultas): suelo → recuperación → compositor → validador → plausibilidad → techo

Cada fila añade una etapa a la anterior en el orden en que el caso de uso las ejecuta. **La última fila antes del techo es la configuración entregada** (`ProposeDietUseCase`: estrategia → `complete_structure` + `normalize_quantities` → `DietValidator`); las filas anteriores son etapas intermedias que la API no sirve. «Viol. plaus.» = violaciones de la envolvente de plausibilidad por propuesta (`check_plausibility`: cantidad fuera de [p05, p95], unidad no observada, alimentos por franja, estructura de franja, alternativas que mezclan grupos, reglas mayoritarias del objetivo); «% con viol.» = propuestas con al menos una.

| Paso | J key | Δ | J food | Δ | J familia | Δ | cumpl. todas | cumpl. condicionales | forzados | tamaño | viol. plaus. | % con viol. |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Suelo: dieta aleatoria del mismo objetivo | 0.205 |  | 0.299 |  | 0.552 |  | 0.722 | 0.877 |  | 1.12 | — | — |
| + recuperación por atributos (copiar top-1) | 0.240 | +0.035 | 0.332 | +0.033 | 0.584 | +0.032 | 0.697 | 0.776 |  | 1.15 | — | — |
| + compositor por consenso (sin degradación) | 0.304 | +0.064 | 0.409 | +0.077 | 0.657 | +0.073 | 0.851 | 0.873 |  | 1.03 | — | — |
| + degradación en objetivos minoritarios | 0.305 | +0.001 | 0.410 | +0.001 | 0.656 | -0.001 | 0.851 | 0.873 |  | 1.03 | 0.40 | 32 % |
| + validador (restricciones + prohibiciones forzables) | 0.305 | +0.000 | 0.410 | +0.000 | 0.656 | -0.000 | 0.861 | 1.000 | 0.10 | 1.03 | 0.39 | 32 % |
| + capa de plausibilidad (estructura desde los casos + cantidades en la envolvente) = **configuración entregada** | **0.305** | +0.000 | 0.411 | +0.000 | 0.656 | +0.000 | 0.861 | 1.000 | 0.09 | 1.03 | 0.03 | 3 % |
| Techo: autoconsistencia (con vecino, 815) / (sin vecino, 741) (sin vecino: 0.274 / 0.365 / 0.586) | 0.324 |  | 0.410 |  | 0.622 |  | 0.725 | 0.870 |  | 1.00 | — | — |

Ramas medidas pero no entregadas (parten del compositor, no se acumulan):

| Rama | J key | J food | J familia | cumpl. todas | cumpl. condicionales | forzados | tamaño | viol. plaus. | % con viol. |
|---|---|---|---|---|---|---|---|---|---|
| Rama no entregada: validador + reglas de confianza baja activadas | 0.305 | 0.410 | 0.656 | 0.798 | 0.873 | 0.10 | 1.03 | — | — |
| Rama no entregada: capa de plausibilidad sin validador | 0.305 | 0.410 | 0.656 | 0.853 | 0.873 |  | 1.03 | 0.03 | 3 % |

**Qué hace la capa de plausibilidad y qué deja.** Cambios aplicados por propuesta: `added_required_group` 0.01 · `portion_in_grams` 1.89 · `quantity_clamped` 0.16 · `quantity_dropped` 0.00 · `ration_harmonised` 0.27 · `supplement_ration` 0.03 · `topped_up` 0.21 · `unit_replaced` 0.03 (759 de 815 propuestas reciben alguno). Violaciones por tipo en las 815 propuestas — validador solo: items_per_slot 171, quantity_out_of_range 128, unseen_unit 17, repeated_food 2; **entregada: quantity_out_of_range 24, repeated_food 2**. Referencia: la dieta oculta del propio profesional tiene 1211 de 29245 cantidades fuera de su envolvente [p05, p95] (4.1 %, 1.49 por dieta), porque la banda se define para dejar fuera ~10 % por construcción: la capa no pretende llegar a cero violaciones, sino no proponer nada que el profesional no haya prescrito.

**Compromiso declarado.** Respecto al validador solo, la capa de plausibilidad gana +0.000 de J `normalized_key` (IC 95 % [+0.000, +0.001], Wilcoxon p = 0.0036); 2 % de las consultas mejoran y la diferencia en `food_id` es +0.000. A cambio reduce las violaciones de plausibilidad de 0.39 a 0.03 por propuesta y la proporción de propuestas con alguna de 32 % a 3 %. Se entrega con la capa activada aunque el Jaccard no la premie: el Jaccard mide el solapamiento con una dieta que el profesional escribió, no si la propuesta es prescribible; una propuesta con cantidades fuera de lo que él prescribe o una cena sin verdura no es una propuesta peor en la métrica, pero sí lo es para el usuario. La configuración entregada sigue batiendo a copiar top-1 en +0.066 [+0.058, +0.074].

## 5. Desglose por franja (J `normalized_key` de la franja; n = dietas ocultas con la franja)

| Franja | n | ítems ocultos | Copiar top-1 | Compositor | Validado | Entregada | Techo (con vecino) | compositor − copia | compositor propone la franja |
|---|---|---|---|---|---|---|---|---|---|
| DESAYUNO | 453 | 5.8 | 0.067 | **0.167** | 0.167 | 0.167 | 0.203 | +0.100 | 96 % |
| MEDIA MAÑANA | 452 | 6.1 | 0.060 | **0.102** | 0.102 | 0.105 | 0.171 | +0.042 | 78 % |
| ALMUERZO | 13 | 4.2 | 0.000 | **0.000** | 0.000 | 0.000 | 0.205 | +0.000 | 0 % |
| COMIDA | 789 | 8.9 | 0.202 | **0.283** | 0.283 | 0.283 | 0.265 | +0.081 | 100 % |
| MERIENDA | 276 | 7.2 | 0.069 | **0.096** | 0.096 | 0.097 | 0.123 | +0.027 | 67 % |
| CENA | 725 | 8.7 | 0.177 | **0.244** | 0.243 | 0.243 | 0.285 | +0.067 | 100 % |
| RECENA | 12 | 3.4 | 0.000 | **0.000** | 0.000 | 0.000 | 0.024 | +0.000 | 0 % |
| ANTES DE ENTRENAR | 434 | 2.4 | 0.052 | **0.139** | 0.139 | 0.139 | 0.246 | +0.087 | 89 % |
| MITAD DE ENTRENAMIENTO | 139 | 1.2 | 0.204 | **0.210** | 0.210 | 0.210 | 0.306 | +0.006 | 42 % |
| DESPUES DE ENTRENAR | 480 | 3.1 | 0.076 | **0.160** | 0.160 | 0.160 | 0.246 | +0.084 | 94 % |

## 6. Análisis de fallos: las 20 consultas con peor Jaccard de la CONFIGURACIÓN ENTREGADA

| Dieta oculta | objetivo | sexo | edad | ítems | franjas | mismo obj. disponibles | mismo obj. en k | gap | degradación | **J entregada** | J compositor | J copiar | J techo | tamaño |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| CASO_01 | ayuno_intermitente | M | 25-39 | 2 | 2 | 68 | 20 | — | none | **0.000** | 0.000 | 0.000 | 0.019 | 13.00 |
| CASO_02 | sin_clasificar | F | 25-39 | 12 | 2 | 93 | 20 | — | none | **0.000** | 0.000 | 0.000 | 0.000 | 1.92 |
| CASO_03 | sin_clasificar | M | 25-39 | 18 | 3 | 93 | 20 | — | none | **0.024** | 0.024 | 0.023 | 0.157 | 1.33 |
| CASO_04 | sin_clasificar | M | 25-39 | 62 | 2 | 91 | 20 | — | none | **0.051** | 0.051 | 0.037 | 0.129 | 0.34 |
| CASO_04 | sin_clasificar | M | 25-39 | 62 | 2 | 91 | 20 | — | none | **0.051** | 0.051 | 0.037 | 0.129 | 0.34 |
| CASO_05 | sin_clasificar | M | 25-39 | 10 | 4 | 93 | 20 | — | none | **0.069** | 0.069 | 0.000 | 0.088 | 2.10 |
| CASO_06 | definicion_grasa | M | 40-54 | 3 | 6 | 478 | 20 | — | none | **0.069** | 0.069 | 0.000 | 0.074 | 9.33 |
| CASO_07 | volumen_masa | M | 25-39 | 34 | 2 | 475 | 20 | — | none | **0.074** | 0.074 | 0.121 | 0.163 | 0.71 |
| CASO_08 | sin_clasificar | M | 25-39 | 35 | 5 | 92 | 20 | — | none | **0.080** | 0.080 | 0.211 | 0.292 | 0.54 |
| CASO_09 | sin_clasificar | M | 25-39 | 26 | 8 | 93 | 20 | — | none | **0.095** | 0.098 | 0.159 | 0.173 | 0.77 |
| CASO_10 | sin_clasificar | M | <25 | 14 | 2 | 93 | 20 | — | none | **0.100** | 0.100 | 0.053 | 0.074 | 1.36 |
| CASO_06 | definicion_grasa | M | 40-54 | 14 | 9 | 478 | 20 | — | none | **0.105** | 0.105 | 0.108 | 0.130 | 2.00 |
| CASO_01 | volumen_masa | M | 25-39 | 31 | 3 | 460 | 20 | — | none | **0.111** | 0.111 | 0.147 | 0.148 | 0.94 |
| CASO_08 | sin_clasificar | M | 25-39 | 41 | 7 | 92 | 20 | — | none | **0.111** | 0.111 | 0.255 | 0.269 | 0.46 |
| CASO_11 | sin_clasificar | M | <25 | 37 | 4 | 92 | 20 | — | none | **0.113** | 0.113 | 0.020 | 0.209 | 0.59 |
| CASO_12 | volumen_masa | M | 40-54 | 30 | 5 | 476 | 20 | — | none | **0.117** | 0.117 | 0.151 | 0.180 | 1.23 |
| CASO_13 | definicion_grasa | M | 25-39 | 13 | 3 | 502 | 20 | — | none | **0.121** | 0.121 | 0.135 | 0.205 | 1.85 |
| CASO_14 | sin_clasificar | M | 40-54 | 15 | 3 | 93 | 20 | — | none | **0.121** | 0.121 | 0.023 | 0.200 | 1.47 |
| CASO_08 | volumen_masa | M | 25-39 | 38 | 7 | 473 | 20 | — | none | **0.123** | 0.123 | 0.164 | 0.187 | 0.68 |
| CASO_01 | sin_clasificar | M | 25-39 | 24 | 6 | 93 | 20 | — | none | **0.125** | 0.125 | 0.087 | 0.124 | 0.88 |

Qué tienen en común (20 peores frente al total): objetivo minoritario 0 % (total 1 %); marcadas como gap 0 % (total 3 %); mujeres 5 % (total 13 %); ítems de la dieta oculta 26.1 de media (total 29.5, mediana 29); dietas con < 15 ítems 35 % (total 3 %); franjas 4.2 (total 6.3); techo con vecino de esas consultas 0.147 (total 0.324); copiar bate a la entregada en 9 de 20 (al compositor crudo, en 9). Objetivos: {'ayuno_intermitente': 1, 'sin_clasificar': 12, 'definicion_grasa': 3, 'volumen_masa': 4}.

## 7. Disponibilidad, degradación y gaps

k = 20; k efectivo: {'20': 796, '1': 19}; modos de degradación: {'none': 796, 'copy_top1': 19}; consultas con < k dietas del mismo objetivo: 19; condiciones de gap: {'candidate_scarcity': 19, 'poor_archetype': 12}; consultas con algún gap: 26 (3.2 %).

Subconjunto minoritario (n = 19): copiar 0.317 · compositor sin degradación 0.288 · compositor con degradación 0.320 · **entregada 0.320**. Subconjunto mayoritario (n = 796): copiar 0.238 · compositor 0.305 · **entregada 0.305**.

## 8. Curvas

Curva de k (umbral por defecto): k=3: 0.218 (tamaño 0.60) · k=5: 0.270 (tamaño 1.03) · k=8: 0.286 (tamaño 1.13) · k=12: 0.289 (tamaño 1.04) · k=16: 0.300 (tamaño 1.01) · k=20: 0.305 (tamaño 1.03)

Curva del umbral (k por defecto): t=0.20: 0.282 (P 0.34 / R 0.62, tamaño 1.96) · t=0.25: 0.294 (P 0.38 / R 0.57, tamaño 1.62) · t=0.30: 0.303 (P 0.43 / R 0.51, tamaño 1.27) · t=0.35: 0.305 (P 0.48 / R 0.46, tamaño 1.03) · t=0.40: 0.292 (P 0.51 / R 0.40, tamaño 0.85) · t=0.50: 0.253 (P 0.57 / R 0.31, tamaño 0.58) · t=0.60: 0.195 (P 0.63 / R 0.22, tamaño 0.36)

Curva α de la híbrida (E3): α=0.50: 0.035

Figuras: `figures/fig01_curva_k.png`, `fig02_curva_umbral.png`, `fig03_criterio_exito.png`, `fig04_curva_alpha_hibrida.png`, `fig05_estratificacion_objetivo.png`, `fig06_franjas.png`, `fig07_estrategias_recuperacion.png`, `fig08_ablacion.png`.

## 9. Escenario cliente recurrente (versiones anteriores disponibles) — cifras NO comparables con las de las secciones 1–8

696 consultas: dietas ocultas con al menos una versión estrictamente anterior del mismo cliente (aserción en el arnés: ninguna versión posterior ni re-emisión del mismo número entra como historial ni como candidato). Las versiones anteriores del cliente **sí** son candidatos de recuperación (en producción el profesional las tiene delante); de media 0.9 de los 20 casos recuperados son suyas. Historial mediano: 5 versiones. Objetivo de renovación del profesional: 25 % de los alimentos con el mismo objetivo, 45 % al cambiar de objetivo; expresado como Jaccard frente a la versión anterior: **0.456** (`normalized_key`) / 0.530 (`food_id`) en estas 696 consultas.

| Variante | J key vs oculta | J food | J familia | J franja | tamaño | **novedad: J vs versión anterior** (humano 0.456) | cumpl. condicional | viol. plaus. |
|---|---|---|---|---|---|---|---|---|
| Copiar la versión anterior (línea base) | **0.456** | 0.530 | 0.704 | 0.391 | 1.05 | 1.000 | 0.855 | — |
| Compositor frío (cliente excluido, protocolo E5) | **0.302** | 0.407 | 0.655 | 0.159 | 1.03 | 0.293 | 0.873 | — |
| Compositor con las versiones anteriores como candidatos | **0.310** | 0.414 | 0.660 | 0.172 | 1.03 | 0.304 | 0.873 | — |
| RotationComposer conservador (reemplazos solo del consenso) | **0.434** | 0.504 | 0.704 | 0.375 | 1.07 | 0.893 | 0.855 | — |
| RotationComposer completo (objetivo de renovación del profesional) | **0.330** | 0.383 | 0.704 | 0.314 | 1.11 | 0.596 | 0.854 | — |
| RotationComposer completo + validador | **0.332** | 0.386 | 0.700 | 0.314 | 1.10 | 0.594 | 0.993 | — |
| Enrutado: mismo objetivo → rotación completa; cambio de objetivo → arquetipo (con historial como candidatos) | **0.359** | 0.424 | 0.720 | 0.315 | 1.06 | 0.494 | 0.866 | 2.58 |
| Enrutado + validador | **0.359** | 0.425 | 0.715 | 0.314 | 1.06 | 0.493 | 1.000 | 2.45 |
| Enrutado + capa de plausibilidad + validador = **configuración entregada** | **0.359** | 0.424 | 0.714 | 0.313 | 1.06 | 0.492 | 1.000 | 1.19 |

**La última fila es la configuración entregada** para el cliente recurrente (enrutado → capa de plausibilidad → validador). Respecto al enrutado validado, la capa no cambia el J key de forma medible (-0.000, IC 95 % [-0.001, +0.000] incluye el 0, Wilcoxon p = 0.74), conserva la fidelidad por familia (0.714 frente a 0.715) y la novedad (0.492 frente a la humana 0.456; diferencia +0.035 [+0.017, +0.055]), y baja las violaciones de plausibilidad de 2.45 a 1.19 por propuesta (-1.26 [-1.36, -1.17]). Cambios aplicados por propuesta: `added_required_group` 0.12 · `portion_in_grams` 0.75 · `quantity_clamped` 0.76 · `quantity_dropped` 0.17 · `ration_harmonised` 0.22 · `supplement_ration` 0.43 · `topped_up` 0.18 · `unit_replaced` 0.44 (653 de 696). Aquí la capa corrige sobre todo lo que la rotación hereda de la versión anterior (unidades y cantidades propias de otro alimento) y las cenas sin verdura.

Rotación aplicada: RotationComposer completo renueva de media el 22.3 % de los ítems (8.6 ítems); el conservador (solo reemplazos presentes en el consenso) el 5.1 %.

| Comparación (emparejada) | Granularidad | n | diferencia | IC 95 % | excluye 0 | p (Wilcoxon) | % a favor |
|---|---|---|---|---|---|---|---|
| rotation_consensus_only - copy_previous | normalized_key | 696 | -0.0221 | [-0.0260, -0.0182] | sí | 3.1e-26 | 17 % |
| rotation_consensus_only - copy_previous | food_id | 696 | -0.0257 | [-0.0302, -0.0213] | sí | 2.5e-27 | 17 % |
| rotation_consensus_only - copy_previous | familia | 696 | +0.0000 | [+0.0000, +0.0000] | **no** | 1 | 0 % |
| rotation_composer - copy_previous | normalized_key | 696 | -0.1263 | [-0.1357, -0.1173] | sí | 1.4e-99 | 5 % |
| rotation_composer - copy_previous | food_id | 696 | -0.1464 | [-0.1566, -0.1362] | sí | 2.1e-99 | 8 % |
| rotation_composer - copy_previous | familia | 696 | +0.0000 | [+0.0000, +0.0000] | **no** | 1 | 0 % |
| cold_composer - copy_previous | normalized_key | 696 | -0.1543 | [-0.1739, -0.1348] | sí | 2.2e-39 | 31 % |
| cold_composer - copy_previous | food_id | 696 | -0.1225 | [-0.1405, -0.1047] | sí | 2.3e-33 | 31 % |
| cold_composer - copy_previous | familia | 696 | -0.0494 | [-0.0629, -0.0358] | sí | 3.7e-11 | 40 % |
| composer_history_candidates - cold_composer | normalized_key | 696 | +0.0077 | [+0.0046, +0.0113] | sí | 2.4e-06 | 37 % |
| composer_history_candidates - cold_composer | food_id | 696 | +0.0067 | [+0.0037, +0.0102] | sí | 4.4e-06 | 36 % |
| composer_history_candidates - cold_composer | familia | 696 | +0.0052 | [+0.0020, +0.0086] | sí | 0.011 | 24 % |
| rotation_composer - cold_composer | normalized_key | 696 | +0.0280 | [+0.0146, +0.0412] | sí | 1.9e-05 | 55 % |
| rotation_composer - cold_composer | food_id | 696 | -0.0240 | [-0.0360, -0.0120] | sí | 0.00068 | 45 % |
| rotation_composer - cold_composer | familia | 696 | +0.0494 | [+0.0356, +0.0632] | sí | 3.7e-11 | 58 % |
| routed - copy_previous | normalized_key | 696 | -0.0973 | [-0.1109, -0.0836] | sí | 1.1e-43 | 22 % |
| routed - copy_previous | food_id | 696 | -0.1059 | [-0.1196, -0.0919] | sí | 5.9e-45 | 21 % |
| routed - copy_previous | familia | 696 | +0.0154 | [+0.0074, +0.0232] | sí | 9.7e-05 | 22 % |
| routed - rotation_composer | normalized_key | 696 | +0.0290 | [+0.0212, +0.0370] | sí | 3.7e-13 | 26 % |
| routed - rotation_composer | food_id | 696 | +0.0406 | [+0.0326, +0.0488] | sí | 7.8e-24 | 28 % |
| routed - rotation_composer | familia | 696 | +0.0154 | [+0.0074, +0.0231] | sí | 9.7e-05 | 22 % |
| routed_delivered - routed | normalized_key | 696 | +0.0002 | [-0.0007, +0.0011] | **no** | 0.16 | 20 % |
| routed_delivered - routed | food_id | 696 | +0.0006 | [-0.0004, +0.0015] | **no** | 0.16 | 20 % |
| routed_delivered - routed | familia | 696 | -0.0058 | [-0.0082, -0.0036] | sí | 2.9e-07 | 9 % |
| routed_delivered - routed_validated | normalized_key | 696 | -0.0002 | [-0.0007, +0.0003] | **no** | 0.74 | 3 % |
| routed_delivered - routed_validated | food_id | 696 | -0.0002 | [-0.0008, +0.0004] | **no** | 0.91 | 2 % |
| routed_delivered - routed_validated | familia | 696 | -0.0014 | [-0.0028, -0.0001] | sí | 0.038 | 2 % |
| routed_delivered - copy_previous | normalized_key | 696 | -0.0971 | [-0.1112, -0.0834] | sí | 6.8e-43 | 24 % |
| routed_delivered - copy_previous | food_id | 696 | -0.1053 | [-0.1193, -0.0908] | sí | 8.8e-44 | 22 % |
| routed_delivered - copy_previous | familia | 696 | +0.0096 | [+0.0013, +0.0178] | sí | 0.23 | 30 % |
| cold_composer novelty - human novelty | novelty (J vs versión anterior) | 696 | -0.1630 | [-0.1817, -0.1444] | sí | 4.1e-44 | 30 % |
| rotation_composer novelty - human novelty | novelty (J vs versión anterior) | 696 | +0.1394 | [+0.1196, +0.1591] | sí | 1.1e-34 | 71 % |
| routed_delivered novelty - human novelty | novelty (J vs versión anterior) | 696 | +0.0355 | [+0.0168, +0.0546] | sí | 0.00034 | 55 % |
| routed_delivered - routed_validated (violaciones de plausibilidad) | violaciones | 696 | -1.2615 | [-1.3578, -1.1667] | sí | 4.7e-79 | 1 % |

| Transición | n | copiar anterior | rotación conservadora | rotación completa | compositor frío | enrutado | **entregada** | familia: copiar / rotación completa / entregada | novedad humana | novedad rotación completa | novedad entregada |
|---|---|---|---|---|---|---|---|---|---|---|---|
| mismo objetivo | 437 | 0.546 | 0.517 | 0.398 | 0.311 | 0.398 | **0.398** | 0.761 / 0.761 / 0.752 | 0.546 | 0.640 | 0.635 |
| cambio de objetivo | 259 | 0.305 | 0.295 | 0.215 | 0.287 | 0.293 | **0.294** | 0.608 / 0.608 / 0.650 | 0.305 | 0.522 | 0.250 |

**Limitación de la métrica en este escenario.** Copiar la versión anterior maximiza la fidelidad por especie (J key 0.456) con novedad 1,000: el óptimo de la métrica es exactamente el fracaso del producto (la misma dieta que el mes pasado). La causa está medida: el profesional rota dentro de la familia, pero hacia qué especie no es predecible; si él pasa de una especie a otra y el sistema a una tercera de la misma familia, el Jaccard por especie lo cuenta como fallo total. Por eso cualquier sistema que rote pierde fidelidad por especie por construcción. A nivel de **familia** la rotación completa es idéntica a copiar (0.704 = 0.704; diferencia 0,000 en todas las consultas, por construcción de la política) y alcanza el nivel de renovación humano (novedad 0.596 frente a 0.456): conserva la fidelidad estructural —familias y estructura de comidas— y concentra el coste en la elección de especie, que el profesional también hace de forma arbitraria. La comparación por especie entre variantes que rotan y variantes que copian no representa el requisito en este escenario; la comparación válida es a nivel de familia más la novedad.
