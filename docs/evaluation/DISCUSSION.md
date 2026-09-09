# E5 · Discusión de resultados

Interpretación de `RESULTS.md` (generado por `eval.report` desde `_dataset/composer_per_query.jsonl` y `_dataset/recurrent_per_query.jsonl`;
recuperación por atributos, compositor k = 20, t = 0,35, degradación `copy_top1`, semilla 42). Las cifras de este texto se leen de
`results.json`; si se regenera el informe, revisar este fichero. **Las secciones 1–7 son el escenario de cliente nuevo (principal); la sección
8 es el escenario de cliente recurrente. Sus cifras no se mezclan.** Desde la Fase 9 (tarea A) el arnés mide también la **configuración
entregada** —estrategia → capa de plausibilidad (S2) → validador— que es la que sirve la API; hasta entonces medía el compositor crudo y la
aplicación ejecutaba compositor + plausibilidad, es decir, las cifras describían un sistema distinto del entregado. La sección 9 recoge lo
que la red de plausibilidad encontró y el plan no había previsto.

> **Procedencia de las cifras (2026-09-08T21:27:18, la ejecución que publica el repositorio).** Todo lo que hay en las secciones 0 a 6 y 8 se ha vuelto a medir con la
> **configuración entregada** —selección D3 (un caso por cliente, pureza primero) y los cinco pesos de similitud con
> `body_type = 0`, aprobados el 2026-08-30— sobre las mismas 815 consultas hold-out, con la envolvente de
> plausibilidad regenerada ese mismo día. La medición anterior de este fichero era del 2026-08-30 a las 00:07, es
> decir, del motor **previo** a esa aprobación: sus cifras describían un sistema que ya no es el que se entrega.
> Lo que NO se ha vuelto a medir y sigue siendo de estudios propios, con su fecha: §7.1 (la ceguera del Jaccard a la
> colocación, 200 consultas) y §9 (los hallazgos de la red de plausibilidad).

## 0. La corrección del techo

Las tablas de E4/E5 usaban como «techo» la autoconsistencia del profesional medida como Jaccard de la dieta oculta frente a **todas** las demás
dietas del mismo cliente (0,275 sin el vecino más cercano, 0,324 con él). El análisis de rotación (`docs/data/rotation_analysis.md`) muestra que
ese techo es **laxo**: mezcla v1 con v6 en una progresión gradual, mientras que entre versiones **consecutivas** el Jaccard es 0,525 (0,590 con el
mismo objetivo). La dieta oculta del arnés es casi siempre la siguiente de una serie, así que el techo relevante para «predecir la siguiente
dieta» es la versión inmediatamente anterior, y el compositor frío (0,302) queda bastante por debajo de él (0,457 en las 696 consultas con
versión anterior; §8).

Consecuencias, asumidas enteras: (1) la afirmación «supera la autoconsistencia del profesional» se retira como titular —el sistema entregado
vuelve a superar el techo laxo A (+0,033), pero superar un techo laxo no es superar al profesional, y frente al estricto queda muy por debajo—;
(2) el resultado sólido sigue en pie y es el bueno: **la configuración entregada bate a copiar el caso más parecido en +0,066 con IC 95 %
[+0,058, +0,074] y p = 5·10⁻⁵⁶**; (3) la dieta anterior del propio cliente es, con mucha diferencia, la mejor señal disponible (0,457 frente a
0,302 del consenso del arquetipo en las mismas consultas), lo que motiva el escenario recurrente.

**Configuración entregada.** La capa de plausibilidad no mueve el titular: la configuración entregada bate a copiar top-1 en **+0,066
[+0,058, +0,074]** (p = 5·10⁻⁵⁶), prácticamente lo mismo que el compositor crudo (+0,065), porque respecto al validador solo la capa cambia el
Jaccard `normalized_key` en +0,000 [+0,000, +0,001] (p = 0,004). Lo que sí cambia es lo que el Jaccard no mide (§3).

**Y con el motor entregado el techo laxo A se supera, no se iguala.** La configuración entregada queda **+0,033
[+0,024, +0,042]** por encima de la autoconsistencia sin el vecino más cercano (p = 1·10⁻¹⁵) en las 741 consultas que
lo tienen definido. Es un cambio de signo respecto a la medición del motor anterior (−0,002, IC que cruzaba el cero) y
**no se lee como «el sistema hace mejores dietas que el profesional»**: se lee como lo que ya decía el párrafo de
arriba, que ese techo es laxo. Frente al techo con vecino sigue por debajo en `normalized_key` (−0,018
[−0,029, −0,007]) y lo iguala en `food_id` (−0,001, IC que contiene el cero).

## 1. Lo que aguanta con intervalo de confianza (E5.1), cliente nuevo

Bootstrap de 10.000 remuestreos sobre diferencias emparejadas y Wilcoxon de rangos con signo, dos colas.

| Comparación (J `normalized_key`) | n | diferencia | IC 95 % | Wilcoxon p | lectura |
|---|---|---|---|---|---|
| **compositor − copiar top-1** | 815 | **+0,065** | [+0,057, +0,073] | 7·10⁻⁵⁶ | componer aporta sobre copiar el caso más parecido |
| **entregada − copiar top-1** | 815 | **+0,066** | [+0,058, +0,074] | 5·10⁻⁵⁶ | **titular**: el margen del sistema que se entrega |
| entregada − validador solo (solapamiento) | 815 | **+0,000** | [+0,000, +0,001] | 4·10⁻³ | la capa de plausibilidad no toca la fidelidad |
| **entregada − techo laxo sin vecino (subconjunto)** | 741 | **+0,033** | [+0,024, +0,042] | 1·10⁻¹⁵ | **SUPERA** el techo laxo A (que es laxo, §0) |
| entregada − techo laxo con vecino | 815 | **−0,018** | [−0,029, −0,007] | 1·10⁻² | queda por debajo del techo laxo B |
| compositor − techo laxo sin vecino (subconjunto) | 741 | **+0,032** | [+0,023, +0,042] | 4·10⁻¹⁵ | idem para el compositor crudo |
| compositor − techo laxo con vecino | 815 | **−0,019** | [−0,030, −0,008] | 8·10⁻³ | queda por debajo del techo laxo B |
| compositor − suelo mismo objetivo | 815 | **+0,100** | [+0,092, +0,107] | 7·10⁻⁹¹ | — |
| copiar top-1 − suelo mismo objetivo | 815 | **+0,035** | [+0,025, +0,044] | 5·10⁻¹⁴ | la recuperación sola ya es un resultado |
| compositor − compositor sin degradación | 815 | **+0,001** | [−0,000, +0,002] | 3·10⁻¹ | la degradación no cambia la media; el IC contiene el cero |
| validado − compositor (solapamiento) | 815 | **+0,000** | [+0,000, +0,000] | 6·10⁻² | el validador no cuesta solapamiento (ni lo aporta) |
| validado − compositor (cumplimiento condicional) | 418 | **+0,127** | [+0,096, +0,158] | 3·10⁻¹³ | el validador sí cambia la validez |
| validado − dieta oculta (cumplimiento condicional) | 362 | **+0,122** | [+0,088, +0,155] | 3·10⁻¹¹ | aplica con consistencia lo que él aplica de forma variable |

**Dos afirmaciones publicadas cambian con el corpus reconstruido, y se reescriben en lugar de relajarse.**

1. **El sistema entregado vuelve a superar el techo laxo sin vecino, y eso dice más del techo que del sistema.** La
   serie completa: +0,039 en dataset-v2, +0,005 (IC con el cero) en el v3 con el motor anterior y **+0,033
   [+0,024, +0,042], p = 1·10⁻¹⁵** con el motor entregado. La lectura que se publica no cambia de fondo: ese techo
   mezcla la v1 con la v6 del mismo cliente y por eso se puede pasar; el techo que importa es el estricto —la versión
   inmediatamente anterior— y ahí el sistema en frío sigue muy por debajo (§8). Lo que sí se afirma con el intervalo
   es que la propuesta se parece a la dieta oculta **más de lo que se parecen entre sí dos dietas cualesquiera del
   mismo cliente**, que es exactamente lo que se espera de un consenso: produce la dieta central de su estilo.
2. **El cumplimiento condicional del compositor deja de ser 1,000 y vuelve a ser medible: 0,873 frente al 0,879 del
   profesional.** El 1,000 de la medición anterior no era cumplimiento, era un artefacto: la reconstrucción leía el
   propósito («perder grasa») donde el v2 leía el método («ayuno intermitente»), los grupos de condición se hundían
   —`sin_hidratos_cena` de 300 dietas a 98— y quedaba **una sola** regla condicional con antecedente medible, que el
   compositor satisface por construcción. Con `method` como campo propio hay 418 consultas con antecedente y el
   efecto del validador reaparece, mayor que en el v2: **+0,127 [+0,096, +0,158]** sobre el compositor y **+0,122**
   sobre la propia dieta del profesional. El 1,000 de las filas «validador» y «entregada» sí es real y es por
   construcción: el validador EXIGE las reglas prescriptivas, así que cumple el 100 % por definición; lo informativo
   es la fila del compositor, que es la que mide sin imposición.

**El titular del corpus reconstruido, comparado con el del v2.** Con el motor anterior era +0,036 frente a +0,054, y
la comparación que sigue —hecha entonces— explicaba esa caída por el corpus. Con el motor entregado el margen sube a
**+0,066** sobre las mismas 815 consultas, así que la caída ya no existe; el párrafo se conserva porque su conclusión
metodológica (que dos medias sobre poblaciones de consulta distintas no se comparan) sigue valiendo y porque las
cifras de la intersección v2/v3 son del motor anterior y no se han vuelto a medir.

**[Medido con el motor anterior, 2026-08-30] El titular baja de +0,054 a +0,036, y la caída es del CORPUS, no del motor.** Las dos cifras se miden sobre
poblaciones de consulta distintas (738 y 815 dietas), así que no son comparables tal cual. Restringidas a las **514
dietas que existen en AMBOS corpus** (emparejadas por contenido a través del cruce de códigos; J de conjuntos de
ítems mediana 0,938), el margen sobre copiar top-1 es **+0,0595 en el corpus anterior y +0,0475 en el reconstruido:
diferencia −0,0120, IC 95 % [−0,0262, +0,0027], que cruza el cero**. A nivel de **familia** —la granularidad que la
fragmentación de franjas no toca— el reconstruido es incluso algo mejor: **+0,0534 antes, +0,0598 ahora**. Sobre esas
mismas dietas el objetivo oculto es más fino (6,12 franjas por dieta frente a 5,28), de modo que el mismo motor
acierta menos sobre un objeto más difícil, no peor.

## 2. Estratificación (E5.2)

- **Sexo.** 87 % hombres (708 frente a 107). La entregada da 0,311 en hombres y 0,270 en mujeres, con ganancia sobre copiar en las dos
  (+0,067 / +0,058) y techo laxo casi idéntico (0,325 / 0,318): las dietas de mujeres son algo más difíciles de predecir para el sistema **y
  también para el propio profesional**. No hay una degradación específica del sistema en mujeres: menos casos y más dispersión. Ambas celdas
  son concluyentes (n ≥ 30).
- **Objetivo.** Gana a copiar en los cuatro objetivos con n ≥ 30: `definicion_grasa` +0,076, `ayuno_intermitente` +0,068, `volumen_masa` +0,048
  y `sin_clasificar` +0,125. En los no concluyentes, `cetosis_keto` (n = 23) da el mayor margen (+0,106) y `descarga_carga` (n = 9) e
  `hipocalorica` (n = 5) empatan con copiar (+0,000 / +0,004); ése es el subconjunto que activa la degradación.
- **Edad.** 25–39 (n = 537), 40–54 (n = 171), < 25 (n = 77) y 55+ (n = 30) son todas concluyentes y consistentes: +0,072, +0,053, +0,063 y
  +0,051 sobre copiar.
- **`generic_assumption`.** Sin las interpretaciones genéricas el compositor baja de 0,305 a 0,299 y copiar sube de 0,240 a 0,242: la ventaja
  (+0,057) no depende de ellas.

## 3. Ablación (E5.3): la última fila es la configuración entregada

Cada fila añade una etapa a la anterior en el orden en que `ProposeDietUseCase` las ejecuta. «Viol.» = violaciones de la envolvente de
plausibilidad por propuesta (`check_plausibility`); «% viol.» = propuestas con al menos una.

| Paso | J key | Δ | cumpl. condicional | viol. | % viol. |
|---|---|---|---|---|---|
| Suelo: dieta aleatoria del mismo objetivo | 0,205 |  | 0,877 | — | — |
| + recuperación por atributos (copiar top-1) | 0,240 | +0,035 | 0,776 | — | — |
| + compositor por consenso (sin degradación) | 0,304 | +0,064 | 0,873 | — | — |
| + degradación en objetivos minoritarios | 0,305 | +0,001 | 0,873 | 0,40 | 32 % |
| + validador (restricciones + prohibiciones forzables) | 0,305 | +0,000 | 1,000 | 0,39 | 32 % |
| **+ capa de plausibilidad = configuración entregada** | **0,306** | +0,000 | 1,000 | **0,03** | **3 %** |
| Techo: autoconsistencia (con vecino, 815) / (sin vecino, 741) | 0,324 |  | 0,870 | — | — |

La recuperación aporta 0,035 y el compositor otros 0,064 (el paso mayor, y con la selección D3 casi el doble de lo
que aportaba antes), la degradación mueve 0,001 y el validador no toca la fidelidad. La capa de plausibilidad es lo
que más cambia y no es en el solapamiento: baja las violaciones de 0,39 a **0,03** por propuesta (32 % → 3 % de
propuestas con alguna), el mejor valor medido hasta ahora.

**Aviso de procedencia: esta sección se ha retranscrito de la ejecución del 2026-09-08 a las 21:27, no de la de las
20:45.** Las dos midieron las mismas 815 consultas con la misma envolvente (minada a las 20:35 y sin tocar desde
entonces) y dan el mismo solapamiento hasta el tercer decimal, pero cuentan las violaciones de forma distinta:
`quantity_out_of_range` 788 → **128** y `unseen_unit` 673 → **17** en el compositor crudo. Que la referencia de
calibrado también se moviera —las cantidades de las dietas ocultas fuera de su propia envolvente, 1.719 de 28.052
(6,1 %) → **1.211 de 29.245 (4,1 %)**— con la envolvente y las dietas ocultas idénticas prueba que lo que cambió es
el **comprobador**, no el motor ni las bandas: `check_plausibility` pasó a resolver el nombre del alimento por el
CATÁLOGO en vez de por el propio ítem, y con ello dejó de saltarse la exención de las raciones curadas en gramos.
Se elige la de las 21:27 porque es la única cuyas filas por consulta sobreviven en `_dataset/composer_per_query.jsonl`
—de donde se regeneran estas cifras y las de `RESULTS.md`— y es la que publica el repositorio.

**La fila del compositor crudo, leída entera.** 0,40 violaciones por propuesta y 32 % de propuestas con alguna: por
debajo del 0,70 y el 52 % de la medición anterior al motor entregado, y no por mérito del vecindario D3 sino porque
el comprobador dejó de contar como violación la ración curada en gramos. Las dos comprobaciones que dominan siguen
siendo las mismas: `items_per_slot` 171 y `quantity_out_of_range` 128 en las 815 propuestas crudas. **La capa las
deja en 0 y 24**, que es su trabajo y la razón por la que se entrega activada. Parte de esa mejora es la exclusión
del cajón genérico `OTHER` de la composición: la mitad de las violaciones estructurales de la medición anterior eran
franjas construidas dentro de él.

**Límite declarado del corpus: el cajón `OTHER`.** El sistema NO compone dentro de la franja genérica —su contenido
es heterogéneo entre vecinos, y componer por consenso ahí producía 24 alimentos distintos en una sola franja— ni la
puntúa, porque medir contra algo que no se puede proponer no dice nada. El censo del cajón
(`_dataset/other_slot_census.json`, 2026-08-29 11:27, sobre una compilación intermedia de **1.208** dietas): 4.578 de
50.437 componentes (9,1 %) viven en él, agrupando 568 encabezados que el vocabulario no supo mapear; 617 dietas
(51 %) tienen algo dentro, con una mediana del 10,4 % de su contenido; **41 dietas (3,4 %) están más de la mitad
dentro y se declaran irrepresentables**, 23 de ellas por completo. Sobre el corpus FINAL de 1.203 dietas
(`_dataset/declared_figures.json`, 2026-09-09) las cifras equivalentes son **38 irrepresentables (3,2 %), 22 de ellas
por completo**, 3.730 componentes en el cajón y 552 dietas con algo dentro; el censo no se ha vuelto a pasar sobre la
compilación final, así que se citan las dos con su fecha en vez de mezclarlas.

La cadena de elegibilidad, en cambio, sí es de la compilación final (`_dataset/loo_eligibility.json`, 2026-08-29
22:30, y `retrieval_benchmark.eligible_queries`): 1.203 dietas de 261 clientes → 1.173 de 260 al excluir las 30
dietas-plantilla → 167 clientes y 1.080 consultas al exigir ≥ 2 dietas → 121 clientes y 835 consultas al exigir sexo,
edad y altura → **120 clientes y 815 consultas** al excluir las irrepresentables. Las consultas hold-out pasan por
tanto de **835 a 815** por esa exclusión, no de 839 a 817: esas dos cifras eran de la compilación intermedia.

**El compromiso de la capa de plausibilidad, declarado.** La capa (`complete_structure` + `normalize_quantities`, envolvente minada del corpus:
`docs/data/plausibility_envelope.md`) toca 759 de las 815 propuestas (por propuesta: 1,89 raciones
pasadas a gramos, 0,27 raciones armonizadas, 0,21 franjas completadas hasta su mínimo, 0,16 cantidades acotadas a [p05, p95], 0,03 raciones de suplemento,
0,03 unidades no observadas sustituidas, 0,01 grupos obligatorios añadidos, 0,004 cantidades retiradas) y no cambia el Jaccard de forma medible:
+0,000 [+0,000, +0,001] en `normalized_key`, +0,000 en `food_id`, +0,000 en familia. A cambio elimina las violaciones que dependen del ítem
—alimentos por franja 171 → 0, cantidad fuera de banda 128 → 24, unidad no observada 17 → 0,
estructura de franja 10 → 0— y deja un residuo de 2 repeticiones de alimento en franja. Referencia de calibrado:
las 815 dietas ocultas del propio profesional tienen el 4,1 % de sus cantidades fuera de su propia envolvente (1.211 de 29.245; 1,49 por dieta),
por construcción de una banda p05–p95: la configuración entregada (0,03 por propuesta) es **más** conservadora que el propio profesional.

**Las dos capas interactúan y el orden importa, y con el motor entregado la interacción se apaga.** En esta medición la rama
«plausibilidad sin validador» y la configuración entregada dejan **exactamente las mismas violaciones** (0,032 por propuesta, 24
`quantity_out_of_range` y 2 `repeated_food` en las dos): el validador ya no introduce implausibilidad que la capa no pueda limpiar, porque
`items_per_slot` baja a 0 antes de que él actúe. El defecto declarado en la medición anterior —los sustitutos forzados empujaban la franja por
encima de su p95 y, como el caso de uso ejecuta **estrategia → capa → validador**, esa implausibilidad entraba después de la capa y no se
limpiaba— **no aparece en la configuración entregada**. La mejora que quedó declarada y no aplicada (acotar la franja también tras el validador)
sigue sin aplicarse, y ahora además no tiene coste medible que justificarla.

Se entrega con la capa activada aunque el Jaccard no la premie. El Jaccard mide el solapamiento con la dieta que el profesional escribió; no
mide si la propuesta es prescribible. Una propuesta con «300 g de almendras» o una cena sin verdura no es peor en la métrica y sí lo es para
el profesional que la va a firmar. Preferir la dieta plausible a la que puntúa igual es la decisión de ingeniería correcta en este dominio;
lo que no valía era no medirla. Si hubiera costado Jaccard, la tabla lo diría y el compromiso se defendería igual: aquí, además, no cuesta.

## 4. Franjas (E5.4)

La hipótesis «el desayuno es fácil y la cena es donde muerden las reglas» **no se confirma**: COMIDA 0,283 y CENA 0,243 son las franjas donde
la configuración entregada mejor acierta y más gana a copiar (+0,081 / +0,066); DESAYUNO 0,167 (+0,100, la mayor ganancia relativa); las franjas
pequeñas (MEDIA MAÑANA 0,106, MERIENDA 0,097) son las peores para todos: pocos ítems y vocabulario disperso. La cena es **más** predecible
gracias a las reglas de colocación. ALMUERZO (n = 13) y RECENA (12) no se proponen nunca: no alcanzan el umbral de franja. La configuración
entregada reproduce el perfil por franja del compositor (columna «entregada» de la tabla de franjas), con la única diferencia apreciable en
MERIENDA (0,097 frente a 0,096) y CENA (0,243 frente a 0,244).

## 5. Análisis de fallos (E5.5)

Las 20 peores se ordenan ahora por el Jaccard de la **configuración entregada**, no por el del compositor crudo: una consulta que el validador
o la capa arreglan no es un fallo del sistema que se entrega. **No** son de objetivos minoritarios (0/20) ni gaps (0/20) ni mujeres (1/20). Lo
que comparten: (1) son dietas que el propio profesional tampoco reproduce (techo laxo con vecino de esas consultas **0,149** frente a 0,324 del
total); (2) dietas cortas: 26,4 ítems de media frente a 29,5, y 35 % de ellas por debajo de 15 ítems frente al 2,6 % del corpus, sobre 4,1
franjas frente a 6,3; (3) **`sin_clasificar` sobrerrepresentado (11 de 20)**, el objetivo cuyo `goal_text` agrupa propósitos heterogéneos;
(4) copiar gana a la entregada en 10 de las 20. El sistema falla donde el profesional es menos consistente consigo mismo, no donde faltan datos.

## 6. Disponibilidad, degradación y gaps (E5.6)

k efectivo = 20 en las 815; **19 consultas** de objetivos minoritarios sin 20 dietas de su objetivo: ahí copiar el mejor caso del mismo objetivo
(0,317) sigue por encima de componer sin degradación (0,288), y la degradación `copy_top1` las deja en 0,320 (0,320 tras la capa y el validador)
→ se mantiene como defecto. En el subconjunto mayoritario (n = 796) la entregada da 0,306 frente a 0,238 de copiar. Gaps con k = 20:
**26 consultas (3,2 %)**, todas por arquetipo pobre (12) o escasez de candidatos (19); con el motor anterior eran 29, y las 3 que desaparecen son
las de `low_score`: la selección D3 sube la similitud del mejor caso por encima del umbral de 0,80.

## 7. Límites del escenario principal

El techo laxo sin vecino solo existe para 634 consultas; las restricciones estructuradas no existen en el corpus (los dos modos de lactosa
coinciden en el LOO); el catálogo E1 con marcas genericadas movió las cifras ≤ 0,0003. Las violaciones de plausibilidad se miden con la misma
envolvente que la capa aplica: son una medida de consistencia interna con el corpus, no una validación externa de la dieta.

### 7.1 · Amenaza a la validez: la métrica titular NO mide la colocación

**El instrumento principal es ciego a en qué franja va cada alimento.** `j_key` — la cifra que sostiene el titular
«compositor − copiar top-1 +0,040» — se calcula sobre un CONJUNTO PLANO: `key_set()` recorre todas las comidas y
vuelca cada `normalized_key` en un único `frozenset`, sin la franja. Lo mismo hacen `j_food`, `j_family` y sus
variantes `no_generic`. Consecuencia formal: **mover un alimento del desayuno a la cena no cambia el valor de la
métrica en absoluto**, ni un decimal. La única métrica que sí ve la franja, `per_slot`, es secundaria y no decide
ninguna de las conclusiones publicadas.

No es una objeción teórica. Medido sobre 200 consultas de la configuración entregada:

| | |
|---|---|
| `j_key` (titular, plano) | **0,3117** |
| `per_slot` (franja a franja) | **0,1660** |
| aciertos que el titular cuenta | 2.670 |
| **de ellos, colocados en OTRA franja que la suya** | **929 = 34,8 %** |
| por dieta: media / mediana | 35,9 % / 35,1 % |

Es decir: **uno de cada tres aciertos que la cifra titular apunta a favor del sistema está en una comida distinta de
aquella en la que el profesional lo escribió**, y la métrica los cuenta igual que si estuvieran en su sitio. Por eso
`per_slot` es aproximadamente la mitad: no es una métrica «más exigente», es la misma pregunta con la colocación
dentro.

**Por qué importa especialmente en este trabajo.** Buena parte de las observaciones del preparador al leer una dieta
generada (§10 y `EXPERT_REVIEW.md`) son de COLOCACIÓN, no de composición: qué va antes de entrenar y qué después,
que la fruta no va en la cena, dónde se toma cada suplemento, qué franja pide hidratos. El instrumento con el que se
mide la fidelidad **no puede ver la dimensión sobre la que el dominio hizo la mitad de sus reparos**. Cuando una
corrección de colocación mejora la dieta a ojos del profesional, `j_key` no se mueve; y una regresión de colocación
tampoco la penaliza.

**Alcance exacto de la ceguera**, para no exagerarla:

- **Afecta** a `j_key`, `j_food`, `j_family`, `j_key_no_generic` y `j_food_no_generic` — es decir, al titular, al
  suelo, al techo, a la ablación, a la estratificación y a la comparación de la intersección v2/v3, porque todos se
  derivan de estas cinco.
- **No afecta** a `per_slot` ni a `slot_jaccard` (por franja, en `composer_per_query.jsonl`), que sí la ven.
- **No afecta** a las tres redes que sí vigilan la colocación por otra vía, y que por eso no son redundantes: el
  motor de reglas (`fruta_no_en_cena`, `desayuno_avena_cereales`, `suplementacion_pre_post` son condiciones sobre
  la franja), la envolvente de plausibilidad (`items_per_slot`, alimentos por franja, repeticiones por franja) y las
  comprobaciones de conformidad (`17_franja_no_suya`, `20_sin_post_entreno`, `11_franja_de_entreno_vacia`,
  `7b_comida_cena_dos_alimentos`).

De modo que el sistema no está sin control sobre la colocación: lo que está sin control es **la cifra titular**. La
lectura honesta es que el número que encabeza los resultados mide *qué alimentos* propone el sistema, no *cómo los
reparte por el día*, y que la evidencia sobre lo segundo hay que buscarla en `per_slot`, en las reglas y en las
comprobaciones — nunca en `j_key`.

Reproducible: `key_set` / `slot_sets` en
`backend/src/finalprosports/infrastructure/adapter/inbound/eval/loo_harness.py`. La cifra del 34,8 % se obtiene
contando, sobre `$FPS_DATASET_DIR/composer_per_query.jsonl`, cuántos aciertos de `key_set` caen en una franja distinta
de la que ocupan en la dieta oculta.

## 8. Escenario cliente recurrente (2.3–2.5): la métrica por especie no representa el requisito

696 consultas con al menos una versión estrictamente anterior del mismo cliente; historial = versiones anteriores (aserción); las versiones
anteriores **sí** entran como candidatos de recuperación (0,9 de los 20 casos de media con la selección D3, que deja un caso por cliente);
ninguna versión posterior ni re-emisión entra. Historial mediano: 5 versiones. Novedad = Jaccard frente a la versión anterior, con **objetivo
humano 0,457** en estas consultas (0,547 con el mismo objetivo, 0,305 al cambiar).

| Variante | J `normalized_key` | J `food_id` | **J familia** | novedad (J vs anterior; humano 0,457) | viol. plaus. |
|---|---|---|---|---|---|
| Copiar la versión anterior (línea base) | **0,457** | **0,530** | 0,705 | 1,000 | — |
| Compositor frío (protocolo E5) | 0,302 | 0,406 | 0,653 | 0,294 | — |
| Compositor con versiones anteriores como candidatos | 0,310 | 0,414 | 0,660 | 0,305 | — |
| RotationComposer conservador (solo consenso; renueva 6 %) | 0,433 | 0,502 | 0,705 | 0,887 | — |
| RotationComposer completo (renueva el 23 % medido) | 0,326 | 0,377 | **0,705** | **0,588** | — |
| Enrutado: mismo objetivo → rotación completa; cambio → arquetipo | 0,356 | 0,419 | **0,720** | **0,489** | 4,28 |
| Enrutado + validador | 0,355 | 0,418 | 0,719 | 0,485 | 4,14 |
| **Enrutado + capa de plausibilidad + validador = configuración entregada** | **0,355** | 0,418 | **0,717** | **0,484** | **2,01** |

### La limitación de la métrica, declarada

Copiar la versión anterior es lo que mejor puntúa por especie y tiene novedad 1,000: **el óptimo de la métrica es exactamente el fracaso del
producto** que motivó este escenario (la misma dieta que el mes pasado). La causa está medida en `rotation_analysis.md`: el profesional rota
dentro de la familia, pero hacia qué especie no es predecible desde el consenso ni desde su repertorio; si él pasa de una especie a otra y el
sistema a una tercera de la misma familia, el Jaccard por especie lo cuenta como fallo total. Cualquier sistema que rote pierde fidelidad por
especie **por construcción**, y cualquier sistema que maximice esa fidelidad no rota. En este escenario la comparación válida es **familia +
novedad**; la fidelidad por especie se reporta pero no decide.

### Lo que dicen las cifras con intervalos

1. **Fidelidad estructural conservada.** A nivel de familia la rotación completa es idéntica a copiar (0,705 = 0,705; diferencia **exactamente
   0,000** en las 696 consultas, por construcción de la política: cada sustituto es de la misma familia) y el enrutado la **supera**
   (+0,016 [+0,008, +0,023], p 8·10⁻⁵). Por franja, la estructura de comidas se mantiene (misma franja, misma posición, mismo grupo de
   alternativas).
2. **Novedad por encima de la del profesional, y algo más cerca que antes.** Rotación completa 0,588 frente a 0,457 (más conservadora que él); el
   enrutado entregado **0,484 frente a 0,457** (+0,027 [+0,008, +0,046]): renueva casi como él, un punto y medio por debajo de su ritmo. El
   compositor frío es *menos* repetitivo que él (0,294; −0,163 [−0,182, −0,145]): la rotación no corrige monotonía, corrige la falta de anclaje
   en la dieta anterior.
3. **El coste se concentra en la especie**, que el profesional también elige de forma arbitraria: rotación completa −0,130 [−0,140, −0,121]
   frente a copiar en `normalized_key`, −0,153 en `food_id`, 0,000 en familia.
4. **El enrutado por cambio de objetivo funciona en la dirección prevista**: mismo objetivo (n = 437) → rotación de la anterior (0,393; familia
   0,757); cambio de objetivo (n = 259) → arquetipo con historial como candidatos (0,294 frente a 0,214 de rotar la anterior y 0,305 de
   copiarla). Combinado: **+0,030 [+0,022, +0,038]** sobre la rotación completa sin enrutado, con familia y novedad intactas.
5. **La configuración entregada no cambia el solapamiento y sí lo que la métrica no ve.** Respecto al enrutado validado: J key −0,000
   [−0,001, +0,000] (p 0,76), familia 0,717 frente a 0,719, novedad 0,484; violaciones de plausibilidad **4,14 → 2,01 por propuesta**
   (−2,13 [−2,23, −2,03]). La capa actúa en 678 de las 696 propuestas y aquí trabaja mucho más que en el cliente nuevo (1,10 cantidades acotadas
   y 1,00 unidades sustituidas por propuesta frente a 0,97 y 0,83): corrige lo que la rotación hereda de la versión anterior —una cantidad y una
   unidad pensadas para el alimento al que sustituye— y las cenas sin verdura (estructura de franja 81 → 0).
   **El residuo de 2,01 es alto y hay que decirlo:** 590 cantidades fuera de banda y 605 unidades no observadas que la capa NO consigue limpiar
   (frente a 23 y 0 en el cliente nuevo), más 111 franjas por encima de su p95 de alimentos distintos, 64 repeticiones de alimento en franja,
   20 recuentos de franjas y 11 grupos de alternativas que mezclan macrogrupos. Es el precio de rotar: al sustituir la especie, la banda de
   cantidad del sustituto muchas veces no existe en la envolvente y la capa no puede acotar contra nada. El escenario de cliente nuevo no tiene
   ese problema porque no hereda líneas.

**Conclusión (tercera contribución, formulada con precisión):** la política de rotación **conserva la fidelidad estructural —familias y
estructura de comidas, idéntica a la de copiar la dieta anterior— mientras alcanza el nivel de renovación del profesional**; el coste se
concentra en la elección de especie, que no es predecible y que el profesional también hace de forma arbitraria. Por eso el defecto para el cliente
recurrente es la **rotación completa con enrutado por cambio de objetivo** (`recurrent_strategy = rotation`, `rotation_use_repertoire = true`,
`route_goal_change_to_archetype = true`) seguida de la capa de plausibilidad y el validador; la rotación conservadora (novedad 0,889: «la misma
dieta que el mes pasado») queda seleccionable pero no representa el requisito. Las versiones anteriores como candidatos aportan +0,026
[+0,021, +0,031] al consenso; la legitimidad es trivial (el profesional las tiene delante).

## 9. Lo que la red de plausibilidad encontró y el plan no había previsto (Fase 9)

Tres resultados sobre el método, no incidencias de implementación: los dos primeros refutan aserciones del plan; el tercero muestra que una
suite minada del corpus detecta defectos que los tests unitarios no ven.

### 9.1 Tres defectos que 119 tests no vieron

La suite golden de S2 (20 perfiles ficticios × envolvente minada del corpus, `make golden`) se escribió con el motor ya evaluado (E4/E5) y con
119 tests sin dependencias en verde (`def test_` en `backend/tests` y `pipeline/tests` en el commit anterior a S2). Encontró tres defectos
que ninguno de ellos cubría, todos visibles hoy en las columnas de violaciones del arnés:

1. **Cantidades y unidades heredadas en la rotación.** `RotationComposer` sustituía la especie conservando la línea de la versión anterior:
   «3 dientes de sacarina» (la unidad del ajo con la cantidad del ajo). Los tests comprobaban familia, posición y novedad, no la cantidad del sustituto. Medida en el
   arnés recurrente: 769 cantidades fuera de banda y 477 unidades no observadas en las 455 propuestas enrutadas (1,7 y 1,0 por propuesta), que la
   capa deja en 0 (§8.5). Corrección: `normalize_quantities` (mediana del sustituto en su unidad más frecuente; retirada de la unidad heredada si el
   alimento no tiene envolvente).
2. **Compuestos tratados como alternativas.** El compositor agrupaba como alternativas componentes que en el corpus van en una misma línea como un plato
   (por ejemplo «pollo con arroz» leído como «pollo / arroz»): la evidencia por ítem cuadraba y ningún test distinguía los dos casos. Lo detectó la comprobación `alternative_groups_mixed`
   de la envolvente (grupos sin macrogrupo común por encima del p95 de su objetivo). Corrección: el compositor agrupa solo alternativas explícitas y
   deja los conjuntos de alimentos intactos; residuo 3 grupos en 738 propuestas.
3. **Cenas sin verdura.** El consenso por franja podía producir una cena con proteína y grasa y sin verdura, plausible ítem a ítem y contraria a la
   regla de colocación `cena_proteina_grasa_verdura` (prevalencia 0,86). Medido como `slot_structure`: 55 propuestas de 746 en el cliente nuevo,
   68 de 455 en el recurrente, 0 tras `complete_structure` (grupo obligatorio añadido desde los casos recuperados; 0,07 y 0,15 por propuesta).

La lectura de método: los tests unitarios fijan el comportamiento que el autor imaginó; una envolvente minada de 40.871 componentes fija el que el
profesional tiene. Lo segundo encontró lo que lo primero no podía buscar.

### 9.2 Las alternativas mezclan familias: la unidad de intercambiabilidad es el papel en la comida

El plan asumía que las alternativas que el profesional escribe en una línea pertenecen a la misma familia y quería exigirlo. El corpus lo refuta
(`docs/data/rotation_analysis.md` §7, misma medida en `plausibility_envelope.md`): de **7.125 grupos de alternativas** con ≥ 2 alimentos canónicos,
**el 63 % mezcla familias**; de esos grupos mixtos el **67 % comparte un macrogrupo del catálogo** (proteína, hidrato, grasa…), y solo el 21 % del
total no comparte ninguno. Los pares más frecuentes lo dicen solos: ave / pescado blanco (736 grupos, 98 % con macrogrupo común), arroz / pasta
(638, 84 %), ave / carne (611, 97 %), ave / pescado azul (527, 88 %), arroz / legumbre (466, 82 %). Por objetivo la cuota de mezcla va del 55 %
(`descarga_carga`) al 74 % (`hipocalorica`), con `volumen_masa` 62 % (3.178 grupos), `definicion_grasa` 60 % y `ayuno_intermitente` 69 %. Para él
«alternativa» no significa «misma familia» sino **mismo papel en la comida**: pollo o atún son intercambiables como proteína aunque sean ave y
pescado. Consecuencias: la envolvente no exige misma familia sino la cuota por dieta de grupos sin macrogrupo común con el p95 de cada objetivo como
límite; y el hallazgo «la rotación es intra-familia» se matiza: la familia es la unidad que se **conserva entre versiones**, el macrogrupo la que
se **intercambia dentro de una comida** —la política de rotación, que sustituye dentro de la familia, es un subconjunto conservador de lo que él
considera intercambiable.

### 9.3 Reglas prescriptivas frente a descriptivas

El plan pedía exigir el 100 % de las reglas condicionales del objetivo cuando una fuera aplicable. Una regla sostenida con lift 2,4 puede estar
presente en el 27 % de las dietas de su grupo (`ansiedad_chocolate_o_gelatina`) o en el 15 % (`sustituir_pescado_por_pollo`): discrimina el
objetivo, pero exigirla a cada propuesta produciría dietas que el profesional no escribe en tres de cada cuatro casos. La constitución distingue
desde la Fase 9 dos naturalezas (campo `nature` en `validated_rules.json`, tabla `rules`, migración 0009; corte `MAJORITY_PREVALENCE = 0,5`
compartido con la envolvente): **11 reglas prescriptivas** —sostenidas o de política y seguidas en la mayoría de su grupo (patrón evitado ≤ 0,5 en
las de evitación): `agua_2.5L`, `prohibido_azucar_procesados`, `ayuno_16h`, `sin_hidratos_cena`, `suplementacion_pre_post`,
`hidratos_primera_mitad_dia`, `fruta_no_en_cena`, `cena_proteina_grasa_verdura`, `desayuno_avena_cereales`, `mujeres_prohibicion_azucar`,
`respetar_intolerancias_alergias`— y **22 descriptivas**, de las que 10 están sostenidas pero son minoritarias en su grupo (`sal_himalaya` 0,49,
`hombres_suplementacion` 0,44, `mujeres_sal_himalaya` 0,36, `ansiedad_chocolate_o_gelatina` 0,27, `saltarse_comidas_fases_tempranas` 0,26,
`ayuno_estable_por_fase` 0,21, `mujeres_chocolate_gelatina` 0,20, `sustituir_pescado_por_pollo` 0,15, `hidratos_en_cena` 0,12 y la regla de
comportamiento sobre lácteos) y 12 lo son por estado (retiradas, descriptivas o de comportamiento). Solo las prescriptivas cuentan como violación
(`goal_rule_unsatisfied`); las descriptivas sostenidas se muestran como evidencia con su prevalencia. El reparto está en
`docs/data/NORMALIZATION_REPORT.md` §3 y en `_dataset/validated_rules.md`.

### 9.4 Alimentos repetidos en la franja: la tercera aserción refutada, y el patrón

La envolvente de S2 incluía «ningún alimento repetido en la misma franja» como comprobación dura. El corpus la refuta como a las otras dos: el
profesional repite un alimento dentro de una franja **3,46 veces por dieta** (componentes menos alimentos distintos, alternativas incluidas) y lo
hace en el **65 % de sus dietas** —«aceite» en dos líneas, «pollo» como plato y como alternativa, y las comidas desglosadas por día de la semana en
algunos documentos—. Recalibrada como el resto de la envolvente (p95 de repeticiones por franja y objetivo, `docs/data/plausibility_envelope.md`:
COMIDA 10, CENA 2, DESAYUNO 3, MEDIA MAÑANA y MERIENDA 1; por objetivo, `cetosis_keto` casi no repite y `descarga_carga`/`volumen_masa` son los que
más), la medida del escenario recurrente cambia de arriba abajo: las violaciones del enrutado validado pasan de 5,50 a 3,40 por propuesta y las de la
configuración entregada de **2,47 a 0,38** (38 franjas en 455 siguen por encima de su p95). En el cliente nuevo no cambia nada (0,21 y 18 %): el
compositor por consenso no repetía. La cifra publicada antes de la recalibración estaba inflada por una regla falsa; esta es la buena.

**El patrón, que es un resultado sobre el método.** Tres aserciones del plan sobre cómo debía ser una dieta las ha refutado el comportamiento
observado del profesional:

| Aserción del plan | Lo que dice el corpus | Regla que quedó |
|---|---|---|
| Las alternativas de una línea son de la misma familia | el 63 % de 7.125 grupos mezclan familias; el 67 % de esos comparten macrogrupo | cuota por dieta de grupos sin macrogrupo común ≤ p95 del objetivo |
| Toda regla condicional aplicable se exige al 100 % | 10 reglas sostenidas están presentes en el 12–49 % de su grupo | prescriptiva solo si prevalencia ≥ 0,5 (11 de 33) |
| Ningún alimento repetido en la franja | 3,46 repeticiones por dieta, 65 % de las dietas | repeticiones ≤ p95 por franja y objetivo |

La envolvente de plausibilidad hay que **minarla del comportamiento observado, no derivarla de cómo uno supone que debería ser una dieta**: las tres
veces que se hizo lo segundo, la regla resultante habría penalizado al propio profesional (el 4,1 % de sus cantidades caen fuera de su banda p05–p95
por construcción; con las tres aserciones del plan, la mayoría de sus dietas habrían sido «implausibles»). Lo que sí encontró la envolvente minada
(§9.1) eran defectos reales del generador, no rasgos del profesional: esa es la diferencia entre una regla derivada y una medida.

## 10. La voz del dominio: lo que el profesional confirmó al leer una dieta generada

La evaluación de este trabajo se apoya en el corpus, que es una fuente indirecta: dice lo que él **hizo**, no lo que
**piensa**. El 28-08-2026 leyó una dieta que la aplicación generó para un cliente real suyo y dio dieciséis observaciones.
El análisis completo está en [EXPERT_REVIEW.md](EXPERT_REVIEW.md); aquí quedan las tres consecuencias que afectan a las
decisiones de este documento.

**Confirma la decisión D7 de alcance — macros y calorías fuera.** Hasta ahora se sostenía solo sobre evidencia del corpus
(él no escribe macros en ninguna de las 1.033 dietas). Ahora tiene la formulación del propio dominio: «los alimentos no hace
falta pesarlos al límite, se buscan las cantidades más o menos para buscar el cambio hormonal y digestivo, no contar
calorías, este entrenador no cuenta calorías». Lo que importa de una cantidad no es su exactitud sino su **coherencia** con
las demás de la misma comida, que es una propiedad distinta y que el sistema no miraba.

**Valida el método del discriminador externo.** El clasificador de §4.1 no sabe nada de nutrición y el preparador no sabe
nada del clasificador, y sin embargo señalaron los mismos defectos: cantidades ausentes (`share_with_quantity`,
`unit_share_none`), pérdida de especificidad al normalizar (5.446 clases a 785, −34 % de poder discriminante) y alternativas
mal emparejadas (`alternatives_per_group_max`). Que dos instrumentos independientes converjan es la mejor evidencia de que
el discriminador mide algo real y no un artificio de ingeniería.

**Y expone su límite.** En un punto discrepan, y el corpus explica por qué: él se queja de que los batidos salen sin gramos,
mientras el descriptor `share_with_quantity` dice que el sistema cuantifica MÁS que él (0,984 contra 0,930). Los dos tienen
razón sobre cosas distintas — el clasificador mide la unidad que el parseo guardó («1 batido»), el experto mira la página,
donde él siempre escribe los gramos dentro del texto. **Un descriptor estructural puede medir fielmente un artefacto del
parseo y no la propiedad que se pretendía medir.** Es una limitación del método, no un fallo de esta ejecución.

### Limitaciones declaradas que salieron de la revisión

Tres de sus peticiones son **asociaciones clínicas que el corpus no respalda** y no se han implementado: elegir la variante
de un alimento según la analítica del cliente, elegir el suplemento por marcadores, y personalizar las especias. Después de
demostrar en §9 que la precisión condicional tiene techo porque sus decisiones caso a caso no son función del perfil,
fabricar una correlación entre un marcador analítico y un alimento sería el peor error posible en una aplicación de salud:
tendría la forma de una recomendación clínica sin ninguna evidencia detrás. Quedan como trabajo futuro, citadas con su frase.
