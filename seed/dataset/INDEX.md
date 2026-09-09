# ÍNDICE MAESTRO — Corpus TFM Dietas (anonimizado y saneado)

- Clientes con dietas: **261** | Dietas limpias: **1203** | Comidas: **8837** | Arquetipos con ≥2 dietas: **48**

## Artefactos (`_dataset/`)

- `diets.jsonl` — una dieta por línea: `id`, `text` (listo para embeber), `meta`, `meals`, `notes`
- `meals.jsonl` — una comida por línea (`<id_dieta>::<FRANJA>`), regenerado desde `diets.jsonl`
- `profiles.jsonl` — perfiles con esquema uniforme (datos de salud solo como booleanos)
- `rules.json` / `rules.md` — notas del preparador agregadas (todas, sin corte)
- `rules_conditions.json` / `.md` — prevalencia y lift por objetivo / sexo / fase
- `archetypes.json` / `.md` — perfiles-tipo
- `foods.json` — catálogo canónico de alimentos (E1, `pipeline/src/pipeline/`); el vocabulario heredado se descartó
- `discarded_empty.jsonl`, `duplicates.json` — trazabilidad de exclusiones
- `_private/` — mapeos e historias clínicas; **fuera del índice vectorial**

## Distribución por objetivo principal

- definicion_grasa: 513
- volumen_masa: 482
- sin_clasificar: 94
- ayuno_intermitente: 72
- cetosis_keto: 24
- descarga_carga: 9
- hipocalorica: 6
- alta_en_fibra: 3

_Objetivo inferido por heurística (`goal_inferred = true`): 32 dietas (2.7 %)._
