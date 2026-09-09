# -*- coding: utf-8 -*-
"""
Phase 3 — Quality sanitisation of the anonymised diets.

Inputs (never modified):
  --diets      _dataset/anonymized/structured_diets.json   (English fields, new ids)
  --chunks     _dataset/anonymized/diet_chunks.jsonl       (meta: sex, age, ... per diet)
  --profiles   _meta/perfiles.json                         (height + raw intolerances -> booleans only)

Outputs (in --out-dir):
  diets.jsonl            one record per clean diet: {id, text, meta, meals, notes}
  meals.jsonl            one record per meal slot of every clean diet (regenerated, not copied)
  discarded_empty.jsonl  diets excluded because meals were empty / text < 80 chars (with reason)
  duplicates.json        groups of byte-identical `meals` (kept representative + dropped ids)
  sanitize_log.json      every transformation with the number of records affected

Transformations (in this order, per diet):
  1. Unicode NFC + RTF residue: decode \\'xx hex escapes (latin-1), drop control words, `{\\`, braces.
  2. Form lines `____` collapsed; commercial URLs / [EMAIL] / [TEL] markers stripped from meal items.
  3. Meal slot expansion: MEDIA MA -> MEDIA MAÑANA, DESPU -> DESPUES DE ENTRENAR (keys and text).
  4. Notes: strip signature boilerplate ([TEL], [EMAIL], mailto, URLs, professional domains);
     drop notes whose residual has < 15 alphabetic characters.
  5. Goal labels normalised to snake_case without accents/slashes; `goal_inferred` flag.
  6. Exclusion of empty diets (no meals or rebuilt text < 80 chars) -> discarded_empty.jsonl.
  7. Deduplication of identical `meals` (keep max diet_version, then longest text, then id).
  8. Flags: activity_level 0 -> null + activity_level_reported; suspicious_demographics
     (age outside 14-80 or height outside 140-210); shared_diet (heuristic, counted only);
     has_intolerances (boolean; the free text stays out of the dataset).
Data values remain in Spanish.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pii_common import custody_alternation, require_custody_patterns, load_records, require_file, strip_accents, write_json, write_jsonl  # noqa: E402

# --------------------------------------------------------------------------- #
# Dictionaries                                                                 #
# --------------------------------------------------------------------------- #

GOAL_MAP = {
    "volumen/masa": "volumen_masa",
    "definici[oó]n/grasa": "definicion_grasa",
    "ayuno intermitente": "ayuno_intermitente",
    "descarga/carga": "descarga_carga",
    "cetosis/keto": "cetosis_keto",
    "hipocal[oó]rica": "hipocalorica",
    "alta en fibra": "alta_en_fibra",
    "mantenimiento": "mantenimiento",
    "sin_clasificar": "sin_clasificar",
}
INFERRED_SUFFIX = " (inferido)"

# POST (5 sections: 3x "POST CENA...", 1x "POSTRE", 1x bare "POST") is not a real slot:
# it is mapped to OTHER so downstream parsers never meet an orphan value.
SLOT_MAP = {"MEDIA MA": "MEDIA MAÑANA", "DESPU": "DESPUES DE ENTRENAR", "POST": "OTHER"}

RTF_HEX = re.compile(r"\\'([0-9a-fA-F]{2})")
RTF_CTL = re.compile(r"\{\\[a-z]*|\\fldrslt|\\par\b|\\[a-z]{2,}\d*\b|\\(?=[\s|)])")
FORM_LINE = re.compile(r"_{4,}")

# El trozo que nombra al profesional viene de la CUSTODIA (ver pii_common.custody_patterns): un detector con el dato
# dentro publica el dato cada vez que se publica el código. Sin custodia, ese trozo simplemente no está y el resto
# —marcadores, URLs, correos— sigue funcionando; quien SANEA el corpus real exige la custodia más abajo.
_CUSTODIA = custody_alternation()
_PROF = rf"|\S*(?:{_CUSTODIA})\S*" if _CUSTODIA else ""
BOILER_TOKEN = re.compile(
    rf"\[TEL\]|\[EMAIL\]|mailto:\S*|https?://\S+|www\.\S+{_PROF}|\(\s*\)|\"\s*\"",
    re.I,
)
BOILER_LABEL = re.compile(r"\b(?:tel|tlf|tfno|telefono|teléfono|m[oó]vil|email|e-mail|mail|correo|web|www|http|https|com|es)\b\s*[:.]?", re.I)
ALPHA = re.compile(r"[A-Za-zÁÉÍÓÚÑáéíóúñ]")

# shared-diet indicators. Only EXPLICIT second-person markers are used: the
# client code followed by "y <name>" or a third-party [NOMBRE] marker. A phrase
# heuristic (por persona / cada uno / ambas / los dos / entre los dos ...) was
# tested and rejected: all 138 hits were "alternar entre ambas cosas"-style
# alternatives between food options, not two eaters.
SHARED_EXPLICIT = re.compile(r"CLIENTE_\d{3}\s+y\s+\S|\[NOMBRE\]")


def normalize_goal(label: str) -> tuple[str, bool]:
    inferred = label.endswith(INFERRED_SUFFIX)
    base = label[: -len(INFERRED_SUFFIX)] if inferred else label
    if base in GOAL_MAP:
        return GOAL_MAP[base], inferred
    s = strip_accents(base).lower()
    s = re.sub(r"\[[a-z]{2,}\]", "", s)          # any leftover raw regex class
    s = re.sub(r"[^a-z0-9]+", "_", s).strip("_")
    return s, inferred


def clean_rtf(s: str) -> tuple[str, bool]:
    if "\\" not in s and "{" not in s:
        return s, False
    orig = s
    s = RTF_HEX.sub(lambda m: bytes.fromhex(m.group(1)).decode("latin-1"), s)
    s = RTF_CTL.sub("", s)
    if "\\" in orig:                              # only touch braces in records that had RTF
        s = re.sub(r"[{}]", "", s)
    s = re.sub(r"[ \t]{2,}", " ", s).strip()
    return s, s != orig


def clean_form(s: str) -> tuple[str, bool]:
    if "____" not in s:
        return s, False
    return re.sub(r"[ \t]{2,}", " ", FORM_LINE.sub(" ", s)).strip(), True


LINK_TOKEN = re.compile(rf"https?://\S+|www\.\S+|mailto:\S*{_PROF}|\[EMAIL\]|\[TEL\]", re.I)


def clean_links(s: str) -> tuple[str, bool]:
    """Strip commercial URLs / contact markers embedded in meal items (1.584 items in
    606 diets in the source): they carry no dietary content and pull vectors together."""
    if not LINK_TOKEN.search(s):
        return s, False
    s = LINK_TOKEN.sub(" ", s)
    s = re.sub(r"\(\s*\)|\[\s*\]|\"\s*\"", "", s)
    s = re.sub(r"\s*([|,;:])\s*(?=[|,;:]|$)", "", s)
    s = re.sub(r"\s{2,}", " ", s).strip(" -–|,;:")
    return s, True


def nfc(s: str) -> str:
    """Unicode NFC: some RTF/ODT extractions left decomposed characters (n + combining tilde)."""
    return unicodedata.normalize("NFC", s)


def clean_note(note: str) -> tuple[str | None, str]:
    """Return (cleaned note or None, action) where action in {kept, trimmed, dropped_boilerplate, dropped_short}."""
    had_boiler = bool(BOILER_TOKEN.search(note))
    s = BOILER_TOKEN.sub(" ", note)
    if had_boiler:
        s = BOILER_LABEL.sub(" ", s)
    s = re.sub(r"\s*[|;,:.\-–]+\s*$", "", re.sub(r"^\s*[|;,:.\-–]+\s*", "", s))
    s = re.sub(r"\s{2,}", " ", s).strip()
    if len(ALPHA.findall(s)) < 15:
        return None, ("dropped_boilerplate" if had_boiler else "dropped_short")
    return s, ("trimmed" if had_boiler else "kept")


def expand_slot(slot: str) -> str:
    return SLOT_MAP.get(slot, slot)


def build_text(goal_text: str, meals: dict, notes: list) -> str:
    body = [f"OBJETIVO: {goal_text}"]
    for slot, items in meals.items():
        body.append(f"{slot}: " + " | ".join(items))
    if notes:
        body.append("NOTAS: " + " ".join(notes))
    return "\n".join(body)


def shared_diet_signals(meals: dict, notes: list) -> dict:
    blob = " \n ".join(it for items in meals.values() for it in items) + " \n " + " ".join(notes)
    sig = {}
    if SHARED_EXPLICIT.search(blob):
        sig["explicit_second_person"] = len(SHARED_EXPLICIT.findall(blob))
    return sig


# --------------------------------------------------------------------------- #
# main                                                                         #
# --------------------------------------------------------------------------- #

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--diets", required=True, type=Path)
    ap.add_argument("--chunks", required=True, type=Path)
    ap.add_argument("--profiles", required=True, type=Path)
    ap.add_argument("--out-dir", required=True, type=Path)
    ap.add_argument("--min-text-chars", type=int, default=80)
    args = ap.parse_args()
    # SIN LOS PATRONES DE CUSTODIA no se sanea: el saneador borra del corpus las menciones comerciales del
    # profesional, y sin ellos haría su trabajo a medias creyendo que lo ha hecho entero. Aborta con el motivo.
    require_custody_patterns("sanitize")

    diets = load_records(require_file(args.diets))
    chunks = {r["id"]: r for r in load_records(require_file(args.chunks))}
    profiles = {p["code"]: p for p in load_records(require_file(args.profiles))}
    if set(chunks) != {d["id"] for d in diets}:
        raise SystemExit("structured_diets and diet_chunks ids do not match")

    log = Counter()
    per_action = Counter()
    slot_counts_before, slot_counts_after = Counter(), Counter()
    notes_before, notes_after = [], []
    shared_breakdown = Counter()
    goal_before, goal_after = Counter(), Counter()
    cleaned = []

    for d in diets:
        meta_src = chunks[d["id"]]["meta"]
        prof = profiles.get(d["client_code"], {})
        rec_flags = Counter()

        # 1-3: meals
        meals = {}
        for slot, items in d["meals"].items():
            slot_counts_before[slot] += 1
            new_slot = expand_slot(slot)
            if new_slot != slot:
                rec_flags["slot_expanded"] += 1
            slot_counts_after[new_slot] += 1
            new_items = []
            for it in items:
                it, r1 = clean_rtf(nfc(it)); rec_flags["rtf"] += r1
                it, r2 = clean_form(it); rec_flags["form"] += r2
                it, r3 = clean_links(it); rec_flags["links"] += r3
                if it:
                    new_items.append(it)
                else:
                    rec_flags["items_emptied"] += 1
            rec_flags["items_before"] += len(items)
            rec_flags["items_after"] += len(new_items)
            if new_items:
                meals[new_slot] = new_items
            elif items:
                rec_flags["slots_lost"] += 1
        # goal text
        goal_text, r1 = clean_rtf(nfc(d.get("goal_text", ""))); rec_flags["rtf"] += r1
        goal_text, r2 = clean_form(goal_text); rec_flags["form"] += r2
        goal_text, r3 = clean_links(goal_text); rec_flags["links"] += r3
        if rec_flags["links"]:
            log["diets_with_links_in_items_cleaned"] += 1
        log["items_with_links_cleaned"] += rec_flags["links"]
        log["items_emptied_by_link_cleaning"] += rec_flags["items_emptied"]
        log["items_before_cleaning"] += rec_flags["items_before"]
        log["items_after_cleaning"] += rec_flags["items_after"]
        if rec_flags["slots_lost"]:
            log["diets_with_slot_lost_by_cleaning"] += 1
            log["slots_lost_by_cleaning"] += rec_flags["slots_lost"]
        emptied_by_cleaning = bool(d["meals"]) and not meals
        if emptied_by_cleaning:
            log["diets_emptied_by_cleaning"] += 1
        # 4: notes
        notes = []
        nb = len(d["notes"])
        for n in d["notes"]:
            n, r1 = clean_rtf(nfc(n)); rec_flags["rtf"] += r1
            n, r2 = clean_form(n); rec_flags["form"] += r2
            cleaned_note, action = clean_note(n)
            per_action[action] += 1
            if cleaned_note:
                notes.append(cleaned_note)
        notes_before.append(nb); notes_after.append(len(notes))
        if nb and len(notes) < nb:
            log["diets_with_notes_removed"] += 1
        if rec_flags["rtf"]:
            log["diets_with_rtf_residue_cleaned"] += 1
        if rec_flags["form"]:
            log["diets_with_form_lines_cleaned"] += 1
        if rec_flags["slot_expanded"]:
            log["diets_with_slots_expanded"] += 1
        log["slot_sections_expanded"] += rec_flags["slot_expanded"]

        # 5: goals
        goals, inferred_flags = [], []
        for g in d["classified_goals"]:
            goal_before[g] += 1
            ng, inf = normalize_goal(g)
            if ng not in goals:
                goals.append(ng)
            inferred_flags.append(inf)
        goal_inferred = any(inferred_flags)
        goal = goals[0]
        goal_after[goal] += 1
        if goal_inferred:
            log["diets_goal_inferred"] += 1

        # 8: flags
        activity = meta_src.get("activity_level")
        activity_reported = activity not in (None, 0)
        if activity == 0:
            log["activity_level_zero_to_null"] += 1
        age, height = prof.get("edad"), prof.get("altura_cm")
        suspicious = (age is not None and not 14 <= age <= 80) or (height is not None and not 140 <= height <= 210)
        if suspicious:
            log["diets_suspicious_demographics"] += 1
        has_intol = bool(prof.get("intolerancias"))
        signals = shared_diet_signals(meals, notes)
        shared = bool(signals)
        for k in signals:
            shared_breakdown[k] += 1
        if shared:
            log["diets_shared_diet_flag"] += 1

        text = build_text(goal_text, meals, notes)
        meta = {
            "client_code": d["client_code"],
            "sex": meta_src.get("sex"),
            "age": meta_src.get("age"),
            "age_bucket": meta_src.get("age_bucket"),
            "activity_level": activity if activity_reported else None,
            "activity_level_reported": activity_reported,
            "goal": goal,
            "goals": goals,
            "goal_inferred": goal_inferred,
            "goal_text": goal_text,
            "diet_version": meta_src.get("diet_version"),
            "has_intolerances": has_intol,
            "suspicious_demographics": suspicious,
            "shared_diet": shared,
            "shared_diet_signals": sorted(signals) if signals else [],
            "meal_count": len(meals),
            "item_count": sum(len(v) for v in meals.values()),
            "template_group_id": None,
            "template_clients": [],
            "note_count": len(notes),
        }
        cleaned.append({"id": d["id"], "text": text, "meta": meta, "meals": meals, "notes": notes,
                        "_emptied_by_cleaning": emptied_by_cleaning})

    # 6: empties
    kept, discarded = [], []
    for r in cleaned:
        if not r["meals"]:
            discarded.append({**r, "discard_reason": "empty_meals_after_link_cleaning" if r["_emptied_by_cleaning"] else "empty_meals"})
        elif len(r["text"]) < args.min_text_chars:
            discarded.append({**r, "discard_reason": f"text_shorter_than_{args.min_text_chars}"})
        else:
            kept.append(r)
    log["input_diets"] = len(diets)
    log["discarded_empty_meals"] = sum(1 for r in discarded if r["discard_reason"] == "empty_meals")
    log["discarded_empty_after_link_cleaning"] = sum(1 for r in discarded if r["discard_reason"] == "empty_meals_after_link_cleaning")
    log["discarded_short_text"] = len(discarded) - log["discarded_empty_meals"] - log["discarded_empty_after_link_cleaning"]
    for r in cleaned:
        r.pop("_emptied_by_cleaning", None)

    # 7: duplicates
    groups: dict[str, list[dict]] = defaultdict(list)
    for r in kept:
        key = hashlib.sha1(json.dumps(r["meals"], sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()
        groups[key].append(r)
    dup_groups, drop_ids = [], set()
    template_seq = 0
    for key, rs in sorted(groups.items()):          # sorted by sha1 -> deterministic template ids
        if len(rs) < 2:
            continue
        rs_sorted = sorted(rs, key=lambda r: (-(r["meta"]["diet_version"] if r["meta"]["diet_version"] is not None else -1),
                                              -len(r["text"]), r["id"]))
        keep, drop = rs_sorted[0], rs_sorted[1:]
        drop_ids.update(r["id"] for r in drop)
        clients = sorted({r["meta"]["client_code"] for r in rs})
        same_client = len(clients) == 1
        template_id = None
        if not same_client:
            # template diet: the same document delivered to several clients. The surviving
            # representative carries the group so a leave-one-out harness can control the leak.
            template_seq += 1
            template_id = f"tpl_{template_seq:03d}"
            keep["meta"]["template_group_id"] = template_id
            keep["meta"]["template_clients"] = clients
        dup_groups.append({"meals_sha1": key, "kept": keep["id"], "dropped": [r["id"] for r in drop],
                           "clients": clients, "same_client": same_client, "template_group_id": template_id})
    final = [r for r in kept if r["id"] not in drop_ids]
    log["duplicate_groups"] = len(dup_groups)
    log["duplicates_dropped"] = len(drop_ids)
    log["duplicate_groups_same_client"] = sum(1 for g in dup_groups if g["same_client"])
    log["template_groups_cross_client"] = sum(1 for g in dup_groups if not g["same_client"])
    log["output_diets"] = len(final)
    log["output_diets_with_template_group"] = sum(1 for r in final if r["meta"]["template_group_id"])

    # meals.jsonl (regenerated from the clean diets)
    meal_rows = []
    for r in final:
        m = r["meta"]
        for slot, items in r["meals"].items():
            meal_rows.append({"id": f"{r['id']}::{slot}",
                              "text": f"[Perfil {m['sex']} {m['age_bucket']}, objetivo {m['goal']}] {slot}: " + " | ".join(items),
                              "meta": {**{k: v for k, v in m.items() if k not in ("goal_text", "meal_count", "note_count", "item_count")},
                                       "diet_id": r["id"], "meal_slot": slot, "item_count": len(items)}})
    log["output_meals"] = len(meal_rows)

    # write
    write_jsonl(args.out_dir / "diets.jsonl", final)
    write_jsonl(args.out_dir / "meals.jsonl", meal_rows)
    write_jsonl(args.out_dir / "discarded_empty.jsonl", discarded)
    write_json(args.out_dir / "duplicates.json", dup_groups)

    lens = sorted(len(r["text"]) for r in final)
    log_out = {
        "counts": dict(log),
        "notes": {
            "total_before": sum(notes_before), "total_after": sum(notes_after),
            "diets_with_notes_before": sum(1 for n in notes_before if n), "diets_with_notes_after": sum(1 for n in notes_after if n),
            "actions": dict(per_action),
            "mean_per_diet_before": round(sum(notes_before) / len(notes_before), 3),
            "mean_per_diet_after": round(sum(notes_after) / len(notes_after), 3),
        },
        "slots_before": dict(slot_counts_before.most_common()),
        "slots_after": dict(slot_counts_after.most_common()),
        "goals_before": dict(goal_before.most_common()),
        "goals_after_main": dict(goal_after.most_common()),
        "goals_after_main_final": dict(Counter(r["meta"]["goal"] for r in final).most_common()),
        "goal_inferred_final": sum(1 for r in final if r["meta"]["goal_inferred"]),
        "shared_diet_signals": dict(shared_breakdown.most_common()),
        "text_length_final": {"min": lens[0], "p50": lens[len(lens) // 2], "max": lens[-1]},
        "items_per_diet_final": {"mean": round(sum(r["meta"]["item_count"] for r in final) / len(final), 2),
                                 "min": min(r["meta"]["item_count"] for r in final),
                                 "max": max(r["meta"]["item_count"] for r in final)},
        "items_per_diet_input_nonempty": round(log["items_before_cleaning"] / max(1, sum(1 for d in diets if d["meals"])), 2),
        "min_text_chars": args.min_text_chars,
    }
    write_json(args.out_dir / "sanitize_log.json", log_out)
    print(json.dumps(log_out, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
