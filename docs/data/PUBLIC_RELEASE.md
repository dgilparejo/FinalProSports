# La versión PÚBLICA: qué viaja, qué no, y cómo se reconstruye

Fecha: 2026-09-09. Decisión: el repositorio se publica; el corpus no.

## El problema, medido

El corpus con el que se construyó y midió el sistema son datos de salud de 301 personas reales (art. 9 RGPD).
Seudonimizado no es anónimo, y sobre los ficheros que viajaban en `seed/dataset` se midió:

```
sexo + edad + altura .................................. 69,1 % de perfiles ÚNICOS
sexo + edad + altura + fecha de 1ª consulta ........... 96,4 %
conjunto de fechas de pesaje (báscula) ................ 94,2 % de 171 personas
báscula ............... 1.318 lecturas con fecha exacta      analíticas ... 254 informes, 243 con valores
dietas ................ 1.203 documentos, 1,5 M de caracteres de texto libre, 1.132 fechados
personas con rastro deportivo público ................. 31, de las que 27 (87 %) son únicas por sexo+edad+altura
```

Y el motor es basado en casos: sin base de casos no hay dietas. Medido sobre una base vacía, 0 alimentos, 0 reglas
y ni se puede dar de alta un cliente (falla la clave ajena `client_profiles_professional_id_fkey`).

## La solución: el criterio es real, los casos son sintéticos

| | qué es | tamaño |
|---|---|---|
| **Criterio (REAL, publicable)** | 228 alimentos, 31 reglas validadas, 223 bandas de cantidad (n≥10), 14 temas de notas (soporte ≥15), pares de alternativas, colocación de suplementos, evaluabilidad, totales diarios | 0,6 MB, **0 personas dentro** |
| **Casos (SINTÉTICOS)** | 300 clientes `SINT_NNN`, ~830 dietas, ~18.000 componentes, ~1.400 pesajes, ~300 informes de laboratorio | 20 MB, generados |
| **Fuera (PRIVADO)** | `profiles/diets/meals/diet_items/archetypes/body_measurements/lab_results` del corpus + `rotation_analysis.per_client` + el expediente REAL del e2e | 47,2 MB = **98,7 % de los bytes** |

## Cómo se reconstruye (todo determinista)

```bash
make public-dataset    # lista blanca de agregados -> seed/dataset_public (aborta si ve datos por persona)
make public-params     # distribuciones gruesas del corpus privado, celda mínima 10 -> synthetic_params.json
make public-synth      # la base de casos sintética (semilla fija: mismos ficheros byte a byte)
make public-quality    # mide si las dietas salen bien -> docs/evaluation/SYNTHETIC_QUALITY.md
make public-fixture    # el expediente sintético del e2e
make public-check      # LA PUERTA: ningún dato personal en el árbol, buscado por FORMA
make public-tree       # monta el árbol público, regenera sus dorados y le pasa la puerta
```

Lo que el generador muestrea y de dónde (nada se inventa a ojo): franjas y su número, de `slot_mix_by_goal` y
`slots_per_diet_by_goal`; ítems por franja, de `items_per_slot_by_goal`; qué alimento en qué franja, de
`foods_by_goal_slot`; unidad y cantidad, de la envolvente (`units_per_food` + p05/p50/p95); grupos de alternativas,
de los tamaños medidos; notas, de las canónicas; suplementos, de su franja modal.

Cuatro correcciones que salieron de medir y que están dentro del generador, cada una con su motivo escrito:

1. **Repertorio por cliente** (8–14 alimentos por franja, sorteados una vez). Sin él, el muestreo proporcional
   desparrama la elección entre 228 canónicos y el compositor —que conserva lo que aparece en ≥35 % de los 20
   vecinos— entregaba franjas de dos líneas: 2,93 ítems por franja frente a 5,10 del corpus real.
2. **Concentración del reparto** (exponente 2,0), por lo mismo.
3. **Estructura garantizada**: las familias que él pone en más de la mitad de las veces, y los grupos que exige el
   dominio (`REQUIRED_GROUPS`: proteína y verdura en la cena, proteína en la comida, hidrato en el desayuno). Sin
   esto, las cenas keto salían sin verdura y la plausibilidad lo cantaba con razón.
4. **Techo de las unidades que se cuentan**, copiado de `quantity_policy.UNIT_CEILING`. El corpus tiene artefactos de
   extracción (`cafeína|unidad` con p50 = 100) y el motor reinterpreta un recuento imposible como gramos, así que la
   propuesta acababa sirviendo «cafeína en g». Una base sintética no tiene por qué reproducir los artefactos.

## Las puertas, medidas

216 propuestas (16 clientes de demostración + rejilla de 200: 4 objetivos × 2 sexos × 4 edades × 2 actividades × 9
restricciones), con la envolvente del corpus REAL como juez. Detalle en `docs/evaluation/SYNTHETIC_QUALITY.md`.

| | sintético | corpus real (misma rejilla) |
|---|---|---|
| violaciones de plausibilidad | **1** | 8 |
| violaciones de reglas tras el validador | **0** | 0 |
| alimentos vetados servidos | **0** | 0 |
| propuestas con los 20 casos pedidos | 216 / 216 | 216 / 216 |
| franjas por dieta (media) | 8,20 | 6,67 |
| ítems por franja (media) | 3,92 | 5,10 |

Dorados: **21/21** en el árbol público contra su propia base (las instantáneas se regeneran al montarlo; las del
árbol privado son las medidas contra el corpus y no se tocan). E2E con el expediente sintético: 3 pasan y 2 se
**saltan declarando el motivo** — las bandas de renovación son las del profesional y solo se pueden medir contra su
expediente real.

## Lo que la versión pública NO puede afirmar

No reproduce la evaluación de la memoria (Jaccard contra sus dietas, arnés leave-one-out, `RESULTS.md`,
`DISCUSSION.md`): esas cifras se midieron contra el corpus. `pipeline/tests/test_dataset.py` se salta con el motivo
escrito cuando no hay corpus privado, en vez de fallar 21 veces y tapar la única señal que importa allí.

Y un dato que evita un malentendido: ni con el corpus real existe «la dieta única». Partiéndolo en dos mitades
disjuntas y pidiendo la dieta del mismo cliente con cada una, la coincidencia de alimentos es **0,593** y la de
familias **0,721**; el propio profesional, con la misma persona, se repite menos que eso (su techo medido de
autoconsistencia en alimentos es 0,416).

## La puerta que faltaba

`backend/tests/architecture/test_public_tree_has_no_personal_data.py` busca **formas** de dato personal, no nombres:
filas con `client_code` cuyos valores no sean `SINT_NNN`, expedientes con identidad y salud en el mismo objeto, y
seudónimos del corpus. Existe porque la auditoría por diccionario de nombres (`audit_tree.py`) tenía un punto ciego
demostrado: el expediente REAL del e2e —481 parámetros de laboratorio de un cliente de 2026, con la identidad
cambiada— la pasaba con 0 aciertos, porque su nombre no está en el diccionario del corpus.

Dos modos: en el árbol privado exige que lo encontrado esté DECLARADO (`DECLARED_PRIVATE`), así que un fichero nuevo
con datos personales falla hasta que alguien lo declare a mano; con `FPS_PUBLIC_TREE=1` exige que no haya nada.
