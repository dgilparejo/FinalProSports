# -*- coding: utf-8 -*-
"""Bloque 6 -- LA HOJA DE CIFRAS: un solo fichero con todo lo que el capitulo 4 cita.

Por que existe. Las cifras del capitulo estan hoy repartidas en `results.json`, `arms_report.json`,
`signal_correlations.json`, `weight_sweep_d3.json`, `discriminability*.json`, `body_signal_coverage.json`,
`lab_signal_coverage.json`, `weight_and_grams.json` y `learned_metric*.json`. Escribir un capitulo copiando de nueve
sitios es como se producen las incoherencias que este proyecto ya ha tenido que corregir dos veces.

**No calcula nada.** Lee los artefactos y los pone juntos, con la procedencia de cada bloque escrita al lado. Si un
artefacto falta, la seccion sale con la marca `(no disponible)` en vez de inventarse: una hoja de cifras que rellena
huecos es peor que una que los ensena.

Run:  python -m finalprosports.infrastructure.adapter.inbound.eval.figures_sheet
Out:  la hoja de cifras de la memoria
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from finalprosports.infrastructure.config.paths import dataset_dir, docs_dir

DATASET = dataset_dir()
DOCS = docs_dir() / "evaluation"


def load(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def pct(x, d=1):
    return "—" if x is None else f"{x*100:.{d}f} %".replace(".", ",")


def num(x, d=4):
    return "—" if x is None else f"{x:.{d}f}".replace(".", ",")


def signed(x, d=4):
    return "—" if x is None else f"{x:+.{d}f}".replace(".", ",")


def pval(x):
    """Notacion cientifica cuando hace falta: un p de 1,7e-07 escrito «0,00» no dice nada."""
    if x is None or x != x:
        return "—"
    return f"{x:.3f}".replace(".", ",") if x >= 0.001 else f"{x:.1e}"


def ci(d, key="ci95"):
    v = (d or {}).get(key)
    return "—" if not v else f"[{v[0]:+.4f}, {v[1]:+.4f}]".replace(".", ",")


def dig(d, *path, default=None):
    for p in path:
        if not isinstance(d, dict) or p not in d:
            return default
        d = d[p]
    return d


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", type=Path, default=DOCS / "HOJA_DE_CIFRAS.md")
    args = ap.parse_args()

    R = load(DOCS / "results.json") or {}
    A = load(DATASET / "arms_report.json") or {}
    S = load(DATASET / "signal_correlations.json") or {}
    W = load(DATASET / "weight_sweep_d3.json") or {}
    B = load(DATASET / "body_signal_coverage.json") or {}
    L = load(DATASET / "lab_signal_coverage.json") or {}
    G = load(DATASET / "weight_and_grams.json") or {}
    M = load(DATASET / "learned_metric.json") or {}
    MN = load(DATASET / "learned_metric_nodate.json") or {}
    MC = load(DATASET / "learned_metric_causal.json") or {}
    CR = load(DATASET / "causal_recency.json") or {}
    FP = load(DATASET / "food_preferences.json") or {}
    HR = load(DATASET / "his_check_rates.json") or {}
    D = load(DOCS / "discriminability.json") or {}
    D3 = load(DOCS / "discriminability_d3.json") or {}

    out: list[str] = []
    add = out.append
    add("# Hoja de cifras del capítulo 4")
    add("")
    add("_Generada por `eval.figures_sheet` desde los artefactos. **No calcula nada**: los reúne y dice de dónde sale")
    add("cada uno. Lo que falte aparece como `(no disponible)`, nunca relleno._")
    add("")
    add("| bloque | procedencia |")
    add("|---|---|")
    for etiqueta, path, ok in (("resultados del arnés", "docs/evaluation/results.json", bool(R)),
                               ("brazos A/B/D1/D3 y techos", "$FPS_DATASET_DIR/arms_report.json", bool(A)),
                               ("correlación de cada señal", "$FPS_DATASET_DIR/signal_correlations.json", bool(S)),
                               ("barrido de pesos", "$FPS_DATASET_DIR/weight_sweep_d3.json", bool(W)),
                               ("cobertura de báscula", "$FPS_DATASET_DIR/body_signal_coverage.json", bool(B)),
                               ("cobertura de analíticas", "$FPS_DATASET_DIR/lab_signal_coverage.json", bool(L)),
                               ("peso, sexo y gramos", "$FPS_DATASET_DIR/weight_and_grams.json", bool(G)),
                               ("métrica aprendida", "$FPS_DATASET_DIR/learned_metric*.json", bool(M)),
                               ("discriminador", "docs/evaluation/discriminability*.json", bool(D))):
        add(f"| {etiqueta} | `{path}` {'' if ok else '**(no disponible)**'} |")
    add("")

    # ------------------------------------------------------------------------------------ 1 · volumen y criterio
    add("## 1 · Volumen de consultas y criterio de éxito")
    add("")
    add("| | |")
    add("|---|---|")
    add(f"| dietas del corpus | {dig(B, 'corpus_diets', default='—')} |")
    add(f"| clientes con dietas | {dig(B, 'corpus_clients', default='—')} |")
    add(f"| **consultas del arnés (LOO)** | **{dig(B, 'queries', default='—')}** |")
    add(f"| clientes que aportan consultas | {dig(B, 'query_clients', default='—')} |")
    add("| criterio principal | Jaccard sobre `normalized_key` de la propuesta contra la dieta oculta |")
    add("| criterio secundario | `food_id` (especie) y `familia` (estructura) |")
    add("| protocolo | leave-one-out estricto: fuera la dieta oculta, todas las de su cliente y su grupo de plantilla |")
    add("")

    # ---------------------------------------------------------- 1-bis · el criterio de exito de LO QUE SE ENTREGA
    # La hoja citaba el volumen de consultas y saltaba a los brazos. La tabla titular del capitulo -- suelo, copiar,
    # sistema entregado y techo, en los dos protocolos y las tres granularidades -- no estaba en ninguna parte de este
    # fichero, asi que el capitulo tenia que ir a buscarla a RESULTS.md: exactamente la copia entre documentos que
    # esta hoja existe para evitar. Sale entera de `results.json`, que es el mismo arnes que mide los brazos.
    add("## 1-bis · Criterio de éxito de la CONFIGURACIÓN ENTREGADA")
    add("")
    if R:
        meta = R.get("meta") or {}
        add(f"Medido el {meta.get('measured_at', '—')} sobre {meta.get('queries', '—')} consultas · recuperación "
            f"`{meta.get('retrieval_strategy', '—')}` · k = {dig(meta, 'params', 'k', default='—')}, "
            f"t = {dig(meta, 'params', 'inclusion_threshold', default='—')} · semilla {meta.get('seed', '—')}.")
        add("")
        add(f"Variante entregada: `{meta.get('delivered_variant', '—')}` — {meta.get('pipeline', '—')}.")
        add("")
        for etiqueta, clave in (("A · techo laxo SIN el vecino más cercano", "A_excl_nearest_neighbour"),
                                ("B · techo laxo CON el vecino más cercano", "B_incl_nearest_neighbour")):
            tab = dig(R, "success", clave)
            if not tab:
                continue
            add(f"**{etiqueta}** — n = {tab.get('queries', '—')}")
            add("")
            add("| granularidad | suelo mismo objetivo | copiar el más parecido | compositor | **entregada** | techo | entregada − copiar | entregada − techo |")
            add("|---|---|---|---|---|---|---|---|")
            for g in ("normalized_key", "food_id", "familia"):
                c = tab.get(g) or {}
                add(f"| `{g}` | {num(c.get('floor_same_goal'))} | {num(c.get('copy_top1'))} | {num(c.get('composer'))} | "
                    f"**{num(c.get('delivered'))}** | {num(c.get('ceiling'))} | {signed(c.get('delivered_vs_copy'))} | {signed(c.get('delivered_vs_ceiling'))} |")
            add("")
        add("**Diferencias pareadas de la entregada** (bootstrap 10.000, semilla fija; Wilcoxon bilateral):")
        add("")
        add("| comparación | métrica | n | diferencia | IC 95 % | p | % consultas a favor |")
        add("|---|---|---|---|---|---|---|")
        for etiqueta, clave in (("entregada − copiar el más parecido", "entregada - copy_top1"),
                                ("entregada − techo laxo sin vecino", "entregada - ceiling_excl_nn (subset)"),
                                ("entregada − techo laxo con vecino", "entregada - ceiling_incl_nn"),
                                ("entregada − suelo del mismo objetivo", "composer - floor_same_goal"),
                                ("entregada − validador solo", "entregada (validador + plausibilidad) - validated_strict"),
                                ("validador − compositor (cumplimiento condicional)", "validated_strict - composer (conditional compliance)"),
                                ("validador − dieta oculta (cumplimiento condicional)", "validated_strict - hidden diet (conditional compliance)"),
                                ("entregada − validador (violaciones de plausibilidad)", "entregada - validated_strict (violaciones de plausibilidad por consulta)")):
            per = dig(R, "statistics", "pairs", clave) or {}
            for met, d in per.items():
                add(f"| {etiqueta} | `{met}` | {d['n']} | **{signed(d['mean_diff'])}** | {ci(d)} | {pval(d['wilcoxon_p'])} | {pct(d.get('share_positive'), 0)} |")
        add("")
        add("**Ablación acumulativa** — la última fila antes del techo es lo que sirve la API:")
        add("")
        add("| paso | J `normalized_key` | Δ | J `food_id` | J `familia` | cumpl. condicional | viol. plausibilidad | % con alguna |")
        add("|---|---|---|---|---|---|---|---|")
        for row in (R.get("ablation") or []):
            d = (row.get("delta") or {}).get("normalized_key")
            v = row.get("plausibility_violations")
            sh = row.get("share_with_violation")
            entregada = row.get("variant") == dig(R, "ablation_extra", "delivered_variant")
            paso = row["step"].replace("**", "")
            paso = f"**{paso}**" if entregada else paso
            add(f"| {paso} | {num(row.get('normalized_key'))} | {signed(d) if d is not None else '—'} | {num(row.get('food_id'))} | "
                f"{num(row.get('familia'))} | {num(row.get('compliance_cond'), 3)} | {'—' if v is None else num(v, 2)} | {'—' if sh is None else pct(sh, 0)} |")
        add("")
        rc = R.get("recurrent")
        if rc:
            t = dig(rc, "table", "routed_delivered") or {}
            cp = dig(rc, "table", "copy_previous") or {}
            add(f"**Escenario recurrente** ({rc.get('queries', '—')} consultas con versión anterior; variante entregada "
                f"`{dig(rc, 'meta', 'delivered_variant', default='—')}`): entregada J key {num(t.get('j_key'))} · familia {num(t.get('j_family'))} · "
                f"novedad {num(t.get('novelty_j_key'))} frente a la humana {num(dig(rc, 'human', 'novelty_j_key'))} · "
                f"violaciones {num(t.get('plausibility_violations'), 2)}. Copiar la versión anterior: J key {num(cp.get('j_key'))}, familia {num(cp.get('j_family'))}.")
            add("")
        av = R.get("availability") or {}
        add(f"**Disponibilidad**: k = {av.get('k', '—')} · consultas con menos de k dietas de su objetivo "
            f"{av.get('queries_with_fewer_than_k_same_goal_available', '—')} · consultas con algún gap "
            f"{av.get('queries_with_any_gap', '—')} · condiciones {av.get('gap_conditions', '—')} · "
            f"modos de degradación {av.get('degradation_modes', '—')}.")
        add("")
        cu = R.get("curves") or {}
        if cu.get("k_curve"):
            add("**Curva de k** (umbral por defecto, compositor crudo): "
                + " · ".join(f"k={c['k']} {num(c['j_key'])}" for c in cu["k_curve"]))
            add("")
        if cu.get("threshold_curve"):
            add("**Curva del umbral** (k por defecto, compositor crudo): "
                + " · ".join(f"t={c['t']:.2f} {num(c['j_key'])}".replace(".", ",", 1) for c in cu["threshold_curve"]))
            add("")
    else:
        add("_(no disponible)_")
        add("")

    # ------------------------------------------------------------------------------------------ 2 · los brazos
    add("## 2 · Tabla de brazos")
    add("")
    if A:
        add("| brazo | n | `normalized_key` | `food_id` | `familia` |")
        add("|---|---|---|---|---|")
        nombres = {"A": "A · motor actual", "B": "B · azar dentro del objetivo",
                   "D1": "D1 · un caso por cliente", "D3": "**D3 · un caso por cliente, pureza primero**"}
        for arm in ("A", "B", "D1", "D3"):
            d = dig(A, "arm_means", arm)
            if not d:
                continue
            add(f"| {nombres[arm]} | {d['n']} | {num(d['normalized_key'])} | {num(d['food_id'])} | {num(d['familia'])} |")
        add("")
        add("**Diferencias pareadas** (IC 95 % por remuestreo, Wilcoxon):")
        add("")
        add("| comparación | métrica | diferencia | IC 95 % | p |")
        add("|---|---|---|---|---|")
        for clave, d in (A.get("pairwise") or {}).items():
            if not d:
                continue
            comp, _, met = clave.partition(":")
            add(f"| {comp.replace('-', ' − ')} | `{met}` | **{signed(d.get('diff'))}** | {ci(d)} | {pval(d.get('wilcoxon_p'))} |")
    else:
        add("_(no disponible)_")
    add("")

    # ------------------------------------------------------------------------------- 3 · estratificación por objetivo
    add("## 3 · Estratificación por objetivo (D3 − A)")
    add("")
    if dig(A, "by_goal"):
        add("| objetivo | n | A | D3 | D3 − A | IC 95 % |")
        add("|---|---|---|---|---|---|")
        for goal, d in sorted(A["by_goal"].items(), key=lambda kv: -kv[1]["n"]):
            add(f"| {goal} | {d['n']} | {num(d.get('A'))} | {num(d.get('D3'))} | {signed(d.get('diff'))} | {ci(d)} |")
    else:
        add("_(no disponible)_")
    add("")

    # ------------------------------------------------------------------------------------------------ 4 · el techo
    add("## 4 · Contra el techo (autoconsistencia del profesional), MISMO conjunto")
    add("")
    hay = False
    add("| techo | n | D3 | techo | D3 − techo | IC 95 % | p | veredicto |")
    add("|---|---|---|---|---|---|---|---|")
    for clave, etiqueta in (("vs_techo_SIN_vecino", "sin vecino"), ("vs_techo_CON_vecino", "con vecino"),
                            ("vs_limpio", "limpio (sin casi-copias)"), ("vs_limpio_sin_nn", "limpio y sin vecino")):
        d = A.get(clave)
        if not d:
            continue
        hay = True
        veredicto = "**SUPERA**" if d["ci95"][0] > 0 else ("iguala" if d["ci95"][1] > 0 else "no alcanza")
        add(f"| {etiqueta} | {d['n']} | {num(d.get('d3'))} | {num(d.get('ceiling'))} | "
            f"**{signed(d.get('diff'))}** | {ci(d)} | {pval(d.get('p'))} | {veredicto} |")
    if not hay:
        out.pop(); out.pop()
        add("_(no disponible)_")
    add("")

    # ------------------------------------------------------------------- 5 · insuficiencia de casos y bandas
    add("## 5 · Insuficiencia de casos comparables · disponibilidad y degradación")
    add("")
    if dig(A, "bands"):
        add("| banda | consultas | % | objetivos |")
        add("|---|---|---|---|")
        total = sum(v["n"] for v in A["bands"].values()) or 1
        for banda in ("SERVIR", "SERVIR DECLARANDO", "NO SERVIR"):
            v = A["bands"].get(banda)
            if not v:
                continue
            add(f"| **{banda}** | {v['n']} | {pct(v['n']/total)} | {', '.join(f'{g} ({n})' for g, n in sorted(v['goals'].items(), key=lambda kv: -kv[1]))} |")
        add("")
        add("Criterio: **NO SERVIR** menos de 2 clientes distintos del objetivo o pureza < 0,50 · **SERVIR "
            "DECLARANDO** menos de k = 20 clientes distintos · **SERVIR** el resto.")
    add("")
    if dig(A, "purity"):
        add("**Pureza e independencia del vecindario entregado** (media sobre las consultas):")
        add("")
        add("| brazo | dietas del objetivo / k | clientes del objetivo / k |")
        add("|---|---|---|")
        for arm in ("A", "D1", "D3"):
            p = dig(A, "purity", f"{arm}:goal_diets_frac")
            c = dig(A, "purity", f"{arm}:goal_clients_frac")
            if p:
                add(f"| {arm} | {num(p.get('mean'), 3)} | **{num(c.get('mean'), 3)}** |")
    add("")

    # ------------------------------------------------------------------------------------ 6 · barrido de pesos
    add("## 6 · Barrido de pesos (bloque 1.1)")
    add("")
    if W:
        add(f"Partición por cliente: **{dig(W, 'partition', 'dev_clients')} clientes de desarrollo / "
            f"{dig(W, 'partition', 'hold_clients')} apartados**, intersección "
            f"**{dig(W, 'partition', 'overlap')}**. Brazo **{W.get('arm')}**, k = {W.get('k')}.")
        add("")
        add("| configuración (desarrollo) | J propuesta | J top-1 | std vecindario |")
        add("|---|---|---|---|")
        for nombre, d in sorted((W.get("dev") or {}).items(), key=lambda kv: -kv[1]["j_propuesta"]):
            add(f"| {nombre} | {num(d['j_propuesta'])} | {num(d['j_top1'])} | {num(d['std_vecindario'], 5)} |")
        h = W.get("holdout") or {}
        add("")
        add(f"**Elegida: «{W.get('chosen')}».** Sobre el apartado, medido una vez: "
            f"actual {num(dig(h, 'actual', 'j_propuesta'))} · elegida {num(dig(h, 'chosen', 'j_propuesta'))} · "
            f"**diferencia pareada {signed(h.get('paired_diff'))} IC {ci(h)}** (n = {h.get('n_paired')}).")
    else:
        add("_(no disponible)_")
    add("")

    # ------------------------------------------------------------------------------------ 7 · señales del cliente
    add("## 7 · Qué sabe el sistema de una persona (bloque 3.1)")
    add("")
    if S:
        add("Correlación de Spearman de cada señal con el Jaccard REAL entre dietas de clientes distintos, "
            "partición por cliente (apartado).")
        add("")
        add("| señal | pares | cobertura | r global | p | r mismo objetivo | p |")
        add("|---|---|---|---|---|---|---|")
        for nombre, d in sorted(((k, v) for k, v in S.items() if not k.startswith("_")),
                                key=lambda kv: -abs(kv[1]["r"])):
            rs = d.get("r_same_goal")
            rs_txt = "—" if rs is None or rs != rs else signed(rs)
            add(f"| {nombre} | {d['pairs']} | {pct(d['coverage'])} | **{signed(d['r'])}** | {pval(d['p'])} | "
                f"{rs_txt} | {pval(d.get('p_same_goal')) if rs == rs else '—'} |")
        t = S.get("_temporal_global")
        ts = S.get("_temporal_same_goal")
        if t:
            add("")
            add(f"**La prueba temporal (3.2)**: |días| entre dos dietas de clientes distintos contra su Jaccard, "
                f"r = **{signed(t['r'])}** (p {pval(t['p'])}, n = {t['n']}); condicionada al mismo objetivo, "
                f"r = **{signed(dig(ts, 'r'))}** (n = {dig(ts, 'n', default=0)}).")
    else:
        add("_(no disponible)_")
    add("")

    # ---------------------------------------------------------------------------------- 8 · peso, sexo y gramos
    add("## 8 · Peso, sexo y gramos (bloque 3.3)")
    add("")
    if G:
        add(f"Dietas con peso de báscula anterior y gramos: **{G.get('diets')}** de {G.get('queries')} · "
            f"**{G.get('rows'):,}** filas (dieta, alimento).".replace(",", "."))
        add("")
        add("**¿escala las raciones con el cuerpo?**")
        add("")
        add("| magnitud | celdas | r medio | IC 95 % | celdas con p<0,05 |")
        add("|---|---|---|---|---|")
        for nombre, d in (G.get("rations") or {}).items():
            add(f"| {nombre} | {d['cells']} | **{signed(d['mean_r'])}** | {ci(d)} | "
                f"{d['significant_cells']}/{d['cells']} ({pct(d['significant_frac'])}) |")
        sd = G.get("sex_difference") or {}
        ov = sd.get("overall") or {}
        if ov:
            add("")
            add(f"**Diferencia de gramos H − M**, mismo objetivo y mismo alimento, sobre {ov['cells']} celdas "
                f"comparables: **{ov['mean_diff']:+.1f} g** IC {ci(ov)} · el hombre lleva más en "
                f"**{ov['male_higher']} de {ov['cells']}**.".replace(".", ","))
    else:
        add("_(no disponible)_")
    add("")

    # ----------------------------------------------------------------------------------- 9 · métrica aprendida
    add("## 9 · La métrica aprendida (bloque 4)")
    add("")
    if M:
        add(f"Partición por cliente: {M.get('train_clients')} entrenamiento / {M.get('test_clients')} prueba. "
            f"Pares: {M.get('pairs_train'):,} + {M.get('pairs_test'):,}; **descartados por mixtos "
            f"{M.get('pairs_discarded_mixed'):,}**.".replace(",", "."))
        add("")
        add("| ordenador | Spearman r | R² |")
        add("|---|---|---|")
        add(f"| constante | — | {num(M.get('r2_constant'))} |")
        add(f"| similitud actual | {signed(M.get('spearman_current'))} | {num(M.get('r2_current'), 2)} |")
        add(f"| **aprendida CON la fecha** | **{signed(M.get('spearman_learned'))}** | {num(M.get('r2_learned'))} |")
        if MN:
            add(f"| **aprendida SIN la fecha** | **{signed(MN.get('spearman_learned'))}** | {num(MN.get('r2_learned'))} |")
        ot = M.get("oracle_table")
        if ot:
            add("")
            add("| ordenador | mejor de los k | media de los k |")
            add("|---|---|---|")
            for etiqueta, clave in (("similitud actual", "current"), ("**métrica aprendida**", "learned"),
                                    ("oráculo (cota no alcanzable)", "oracle")):
                v = ot.get(clave)
                add(f"| {etiqueta} | {num(v[0])} | {num(v[1])} |")
    else:
        add("_(no disponible)_")
    add("")

    # ------------------------------------------------------------------------------------- 10 · discriminador
    add("## 10 · Discriminador externo (bloque 2-bis)")
    add("")
    if D and D3:
        add("| brazo | control real-real (LR / GB) | veredicto | principal (LR) | principal (GB) |")
        add("|---|---|---|---|---|")
        for etiqueta, d in (("motor", D), ("**D3**", D3)):
            c = dig(d, "control", "models") or {}
            p = dig(d, "principal", "models") or {}
            add(f"| {etiqueta} | {num(dig(c, 'logistic_regression', 'auc'))} / {num(dig(c, 'gradient_boosting', 'auc'))} | "
                f"{dig(d, 'control', 'verdict')} | {num(dig(p, 'logistic_regression', 'auc'))} | "
                f"**{num(dig(p, 'gradient_boosting', 'auc'))}** |")
        imp = dig(D3, "principal", "models", "gradient_boosting", "permutation_importance") or []
        means = D3.get("descriptor_means") or {}
        if imp:
            add("")
            add("**Lo que delata, por tamaño** (AUC perdida al barajar el rasgo):")
            add("")
            add("| rasgo | AUC perdida | media real | media generada | signo |")
            add("|---|---|---|---|---|")
            for x in imp[:10]:
                m = means.get(x["feature"], {})
                r, g = m.get("real"), m.get("generated")
                signo = "—" if r is None else ("de más" if g > r else ("de menos" if g < r else "="))
                add(f"| `{x['feature']}` | {num(x['auc_drop'], 5)} | {num(r, 3)} | {num(g, 3)} | **{signo}** |")
    else:
        add("_(no disponible)_")
    add("")

    # -------------------------------------------------------------------------------- 11 · la recencia causal
    add("## 11 · La fecha en su versión causal (bloque 2 de la 2.ª ronda)")
    add("")
    if CR:
        add(f"Sobre {CR.get('queries')} consultas con al menos 25 candidatos ANTERIORES "
            f"(descartadas {CR.get('dropped_small_pool')}; conjunto causal de mediana {CR.get('pool_median'):.0f}).")
        add("")
        add("| ordenador | r medio DENTRO de cada consulta | r mediana | consultas con r < 0 |")
        add("|---|---|---|---|")
        for clave, etiqueta in (("within_query_recency", "**RECENCIA**"), ("within_query_similarity", "similitud actual")):
            d = CR.get(clave)
            if d:
                add(f"| {etiqueta} | **{signed(d['mean'])}** | {signed(d['median'])} | {d['negative']}/{d['n']} = "
                    f"{pct(d['negative']/d['n'])} |")
        ot = CR.get("oracle_table_causal")
        if ot:
            add("")
            add("| ordenador (conjunto causal) | mejor de los k | media de los k |")
            add("|---|---|---|")
            for clave, etiqueta in (("similarity", "similitud actual"), ("recency", "**recencia sola**"),
                                    ("oracle", "oráculo (cota no alcanzable)")):
                add(f"| {etiqueta} | {num(ot[clave][0])} | {num(ot[clave][1])} |")
            if CR.get("recency_gap_recovered_best") is not None:
                add("")
                add(f"**La recencia sola recupera el {pct(CR['recency_gap_recovered_best'])} del hueco hasta el "
                    "oráculo** en «mejor de los k», con UN rasgo disponible en producción.")
    if MC:
        add("")
        add(f"Métrica aprendida CAUSAL: Spearman **{signed(MC.get('spearman_learned'))}** frente a "
            f"{signed(MC.get('spearman_current'))} de la similitud actual.")
    add("")

    # -------------------------------------------------------------------------------- 12 · los gustos positivos
    add("## 12 · Los gustos positivos (bloque 8)")
    add("")
    if FP:
        add("| |  clientes | alimentos/cliente | pares | efecto (observada − base) | IC 95 % | veredicto |")
        add("|---|---|---|---|---|---|---|")
        for campo, etiqueta in (("liked_foods", "**gustos POSITIVOS**"), ("disliked_foods", "gustos NEGATIVOS (control)")):
            d = FP.get(campo)
            if d:
                add(f"| {etiqueta} | {d['clients']} | {d['foods_per_client_mean']:.1f} | {d['pairs']} | "
                    f"**{signed(d['effect'])}** | {ci(d)} | {d['verdict']} |")
        add("")
        add(f"Control (los negativos salen por debajo): **{'SÍ' if FP.get('control_passes') else 'NO'}**. "
            f"Efecto positivo confirmado: **{'SÍ' if FP.get('positive_effect_confirmed') else 'NO'}**.")
    else:
        add("_(no disponible)_")
    add("")
    if dig(A, "likes_tiebreak"):
        d = A["likes_tiebreak"]
        add("**El desempate en la composición**, medido donde puede verse (el Jaccard es sobre conjuntos y el "
            "desempate reordena dentro del conjunto ya seleccionado, así que no puede moverlo):")
        add("")
        add("| | acierto del LÍDER de cada grupo |")
        add("|---|---|")
        add(f"| con desempate | {num(d['with'])} |")
        add(f"| sin desempate | {num(d['without'])} |")
        add(f"| **diferencia pareada** | **{signed(d['diff'])}** {ci(d)} |")
        add(f"| consultas en que cambia algo | {d['changed']} de {d['queries']} |")
        add("")

    # ---------------------------------------------------------------- 13 · las comprobaciones contra su practica
    add("## 13 · Las comprobaciones, recalibradas contra su práctica (bloque 4)")
    add("")
    if HR:
        add(f"Medido sobre **{HR.get('diets_measured')} dietas suyas**. Regla: su tasa = 0 → violación; > 0 → "
            "calibración con SU tasa como objetivo.")
        add("")
        add("| comprobación | dietas suyas | su tasa |")
        add("|---|---|---|")
        for c, v in (HR.get("checks") or {}).items():
            add(f"| `{c}` | {v['diets']} | {pct(v['rate'])} |")
    else:
        add("_(no disponible)_")
    add("")

    # ------------------------------------------------------------------------- 14 · cobertura de los dos conjuntos de datos
    add("## 11 · Cobertura de báscula y analíticas (bloque 0)")
    add("")
    if B:
        add("| | |")
        add("|---|---|")
        add(f"| lecturas de báscula en el dataset | {B.get('scale_readings')} de {B.get('scale_clients')} clientes |")
        add(f"| clientes con dietas y alguna lectura | {B.get('clients_with_diets_and_a_reading')} de {B.get('corpus_clients')} |")
        add(f"| **consultas con lectura ANTERIOR utilizable** | **{B.get('queries_with_a_prior_reading')} de {B.get('queries')}** "
            f"({pct(B['queries_with_a_prior_reading']/B['queries'])}) |")
        add(f"| regla | {B.get('rule')} |")
        add("")
        add("| campo | consultas | % | % de pares evaluables |")
        add("|---|---|---|---|")
        for campo, d in (B.get("fields") or {}).items():
            add(f"| `{campo}` | {d['queries_with_value']} | {pct(d['queries_pct'])} | {pct(d['pairs_pct'])} |")
    add("")
    if L:
        add("| | |")
        add("|---|---|")
        add(f"| informes de analítica | {L.get('reports')} de {sum((L.get('by_namespace') or {}).values())} en {len(L.get('by_namespace') or {})} formatos |")
        add(f"| por espacio de nombres | {', '.join(f'{k} {v}' for k, v in (L.get('by_namespace') or {}).items())} |")
        add(f"| sin texto extraíble | {L.get('no_extractable_text')} · bajo el umbral: {L.get('below_threshold')} |")
        add(f"| **consultas con informe ANTERIOR** | **{L.get('queries_with_a_prior_report')} de {L.get('queries')}** "
            f"({pct(L['queries_with_a_prior_report']/L['queries'])}) |")
        for ns, inv in (L.get("inventory") or {}).items():
            usables = sum(1 for d in inv.values() if d["clients"] >= (L.get("min_clients_to_be_usable") or 30))
            add(f"| `{ns}` | {len(inv)} parámetros · {usables} con ≥ {L.get('min_clients_to_be_usable')} clientes |")
    add("")

    args.out.write_text("\n".join(out) + "\n", encoding="utf-8", newline="\n")
    print(f"-> {args.out}  ({len(out)} líneas)")
    faltan = [n for n, d in (("results.json", R), ("arms_report", A), ("signal_correlations", S),
                             ("weight_sweep_d3", W), ("body_signal_coverage", B), ("lab_signal_coverage", L),
                             ("weight_and_grams", G), ("learned_metric", M), ("discriminability", D)) if not d]
    print(f"artefactos ausentes: {faltan or '(ninguno)'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
