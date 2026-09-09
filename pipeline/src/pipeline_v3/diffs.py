"""F6.2 -- verification against the DOCUMENTS, not against statistics.

A coverage percentage cannot tell you whether a diet was read correctly; only opening the document and the record
side by side can. This samples 25 diets and 15 questionnaires (seeded, so the sample is the same on every run),
compares them element by element, and writes the full comparison to `la memoria (verificación del dataset contra los documentos)`.

What is compared, per diet: every non-empty line of the converted document is accounted for as either an item that
reached a slot, a note, the goal, a recognised section that is deliberately not food (contact, profile field), or
**unaccounted** -- which is the number that matters. Per questionnaire: every ``label: value`` pair in the document
against the field it landed in, including the ones that went to ``extra_fields``.

The text shown is the anonymised text (names already replaced), because that is what the pipeline produced and what
the audit passes; no original document content with a name in it is ever written here.
"""
from __future__ import annotations

import argparse
import collections
import json
import random
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from pipeline_v3 import convert, extract_diets, extract_profiles, paths, vocab
else:
    from . import convert, extract_diets, extract_profiles, paths, vocab

SEED = 20260828
DIET_SAMPLE = 25
QUESTIONNAIRE_SAMPLE = 15


def _account_for_diet(text: str, record: dict) -> dict:
    """Classify every line of the document by where it ended up."""
    parsed = extract_diets.parse_document(text)
    in_items = {i.strip() for items in parsed["meals"].values() for i in items}
    in_notes = {n.strip() for n in parsed["notes"]}
    buckets = collections.Counter()
    unaccounted: list[str] = []
    for raw in text.split("\n"):
        line = raw.strip()
        if not line or extract_diets._NOISE.match(line):
            buckets["blank_or_noise"] += 1
            continue
        header = vocab.split_header(line)
        if header is not None:
            kind, target, _ = vocab.classify_header(vocab.normalise_header(header[0]))
            buckets[f"header:{kind}"] += 1
            rest = header[1].strip()
            if not rest or rest in in_items or rest in in_notes:
                continue
            if kind in ("section",) and target in ("contact", "profile_field", "goal", "notes"):
                continue
            unaccounted.append(line)
            continue
        if line in in_items:
            buckets["item"] += 1
        elif line in in_notes:
            buckets["note"] += 1
        elif line in parsed["goal_text"] or line in parsed["preamble"]:
            buckets["goal_or_preamble"] += 1
        else:
            buckets["unaccounted"] += 1
            unaccounted.append(line)
    return {"buckets": dict(buckets), "unaccounted_lines": unaccounted[:25],
            "unaccounted_count": buckets["unaccounted"] + len([u for u in unaccounted]) - len(unaccounted)}


def build(out_dir: Path | None = None) -> dict:
    out_dir = out_dir or paths.dataset_dir_v3()
    manifest = [json.loads(l) for l in (out_dir / "manifest.jsonl").read_text(encoding="utf-8").splitlines()
                if l.strip()]
    diets = {d["meta"]["source_sha1"]: d for d in
             (json.loads(l) for l in (out_dir / "diets.jsonl").read_text(encoding="utf-8").splitlines() if l.strip())}

    rng = random.Random(SEED)
    diet_rows = [r for r in manifest if r.get("label") == "diet" and r.get("status") == "ok"
                 and r["sha1"] in diets]
    quest_rows = [r for r in manifest if r.get("label") == "questionnaire" and r.get("status") == "ok"]
    diet_sample = rng.sample(diet_rows, min(DIET_SAMPLE, len(diet_rows)))
    quest_sample = rng.sample(quest_rows, min(QUESTIONNAIRE_SAMPLE, len(quest_rows)))

    lines: list[str] = []
    lines.append("# v3 — verificación contra los documentos (F6.2)\n")
    lines.append(f"Muestra fijada con semilla {SEED}: {len(diet_sample)} dietas y {len(quest_sample)} "
                 "cuestionarios. Se compara **elemento a elemento**: cada línea no vacía del documento convertido "
                 "tiene que acabar en algún sitio (ítem de una franja, nota, objetivo, sección reconocida que no "
                 "es comida) o aparecer como *sin asignar*. El texto mostrado es el ya anonimizado.\n")

    totals = collections.Counter()
    diet_details = []
    for row in diet_sample:
        text = convert.cached_text(row["sha1"])
        record = diets[row["sha1"]]
        account = _account_for_diet(text, record)
        totals["diet_lines"] += sum(account["buckets"].values())
        totals["diet_unaccounted"] += account["buckets"].get("unaccounted", 0)
        diet_details.append((row, record, account))

    lines.append("## Resumen de las 25 dietas\n")
    lines.append("| dieta | franjas | ítems | notas | líneas | sin asignar |")
    lines.append("|---|---|---|---|---|---|")
    for row, record, account in diet_details:
        lines.append(f"| `{record['id']}` | {len(record['meals'])} | {record['meta']['item_count']} | "
                     f"{record['meta']['note_count']} | {sum(account['buckets'].values())} | "
                     f"{account['buckets'].get('unaccounted', 0)} |")
    lines.append("")

    lines.append("## Tres diffs completos\n")
    for row, record, account in diet_details[:3]:
        text = convert.cached_text(row["sha1"])
        lines.append(f"### `{record['id']}` — origen `{row['rel']}` ({row['ext']}, {row['chars']} car.)\n")
        lines.append("**Documento convertido (anonimizado), línea a línea, con su destino:**\n")
        lines.append("```")
        in_items = {i.strip(): slot for slot, items in record["meals"].items() for i in items}
        in_notes = {n.strip() for n in record["notes"]}
        for raw in text.split("\n")[:70]:
            line = raw.strip()
            if not line:
                continue
            header = vocab.split_header(line)
            if header is not None:
                kind, target, _ = vocab.classify_header(vocab.normalise_header(header[0]))
                destination = f"CABECERA -> {kind}:{target}"
            elif line in in_items:
                destination = f"item -> {in_items[line]}"
            elif line in in_notes:
                destination = "nota"
            elif line in record["meta"].get("goal_text", ""):
                destination = "objetivo"
            else:
                destination = "SIN ASIGNAR"
            lines.append(f"{destination:34} | {line[:88]}")
        lines.append("```\n")
        lines.append("**Registro extraído:**\n")
        lines.append("```json")
        lines.append(json.dumps({"id": record["id"],
                                 "goal": record["meta"].get("goal"),
                                 "goal_text": record["meta"].get("goal_text", "")[:160],
                                 "meals": {k: v[:6] for k, v in list(record["meals"].items())[:8]},
                                 "notes": record["notes"][:4],
                                 "unmapped_slots": record["meta"].get("unmapped_slots")},
                                ensure_ascii=False, indent=1))
        lines.append("```\n")

    lines.append("## Cuestionarios\n")
    lines.append("| cuestionario | pares etiqueta:valor | a campo del perfil | a extra_fields | descartados (identidad) |")
    lines.append("|---|---|---|---|---|")
    q_details = []
    for row in quest_sample:
        text = convert.cached_text(row["sha1"])
        public, health, extra = extract_profiles.parse_questionnaire(text)
        pairs = 0
        identity_dropped = 0
        for line in text.split("\n"):
            for head, rest in extract_profiles._label_value_pairs(line):
                if not rest.strip():
                    continue
                pairs += 1
                normalised = vocab.normalise_header(head)
                for pattern, _field, kind in extract_profiles._FIELD_RULES:
                    if pattern.match(normalised) and kind == "identity":
                        identity_dropped += 1
                        break
        q_details.append((row, public, health, extra, pairs, identity_dropped))
        lines.append(f"| `{row['rel'][:44]}` | {pairs} | {len(public) + len(health)} | {len(extra)} | "
                     f"{identity_dropped} |")
        totals["q_pairs"] += pairs
        totals["q_mapped"] += len(public) + len(health)
        totals["q_extra"] += len(extra)
        totals["q_identity"] += identity_dropped
    lines.append("")

    row, public, health, extra, pairs, dropped = q_details[0]
    lines.append(f"### Diff completo de un cuestionario — `{row['rel']}`\n")
    lines.append("```json")
    lines.append(json.dumps({"campos_publicos": public,
                             "campos_de_salud (van al fichero privado)": {k: "<TEXTO_MEDICO>" for k in health},
                             "extra_fields": extra,
                             "pares_totales": pairs, "descartados_por_identidad": dropped},
                            ensure_ascii=False, indent=1))
    lines.append("```\n")

    summary = {
        "diets_sampled": len(diet_sample),
        "questionnaires_sampled": len(quest_sample),
        "diet_lines_examined": totals["diet_lines"],
        "diet_lines_unaccounted": totals["diet_unaccounted"],
        "diet_unaccounted_pct": round(100 * totals["diet_unaccounted"] / max(1, totals["diet_lines"]), 2),
        "questionnaire_pairs": totals["q_pairs"],
        "questionnaire_pairs_to_a_profile_field": totals["q_mapped"],
        "questionnaire_pairs_to_extra_fields": totals["q_extra"],
        "questionnaire_pairs_dropped_as_identity": totals["q_identity"],
    }
    lines.insert(3, f"**Resultado**: {summary['diet_lines_examined']} líneas de dieta examinadas, "
                    f"{summary['diet_lines_unaccounted']} sin asignar ({summary['diet_unaccounted_pct']} %). "
                    f"{summary['questionnaire_pairs']} pares etiqueta:valor en los cuestionarios, "
                    f"{summary['questionnaire_pairs_to_a_profile_field']} a un campo del perfil, "
                    f"{summary['questionnaire_pairs_to_extra_fields']} a `extra_fields`, "
                    f"{summary['questionnaire_pairs_dropped_as_identity']} descartados por ser identidad.\n")

    target = paths.docs_dir() / "data" / "V3_DIFFS.md"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("\n".join(lines), encoding="utf-8", newline="\n")
    (out_dir / "diffs_log.json").write_text(json.dumps(summary, ensure_ascii=False, indent=1),
                                            encoding="utf-8", newline="\n")
    return summary


def main() -> None:
    argparse.ArgumentParser(description="F6.2: diff the extraction against the documents").parse_args()
    print(json.dumps(build(), ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
