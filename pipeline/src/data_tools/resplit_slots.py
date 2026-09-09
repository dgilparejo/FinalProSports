# -*- coding: utf-8 -*-
"""
dataset-v2 — put back the meal slots the legacy splitter lost.

The original extractor recognised twelve header prefixes. Every other label line the professional
writes — «Media Tarde:», «Antes de dormir:», «Mitad de entrenamiento:», «Observaciones:», his e-mail — was appended to whichever
slot was open, so 4.863 catalogue components (11,9 % of the corpus) sit in the wrong slot and 713 blocks of notes are parsed as
instructions and dropped. The defect is invisible to any aggregate: it was found by running one real client through the
application (la memoria (informe del dataset-v2)).

The surgery is exact because the lost header SURVIVES as an item inside the host slot, so the cut point is unambiguous. Blocks are
moved VERBATIM (parse_items.HEADER_LABELS already strips the label prefix, so E1 behaves exactly as before, in the right slot).

Classification: pipeline/src/pipeline/data/slot_labels.json (six categories; A moves, D goes to notes, E is dropped, B/C/F stay).

Input is dataset-v1, which is never modified. Output is a new dataset directory. A self-test refuses to run unless the text and
meals builders reproduce dataset-v1 byte for byte, and `--verify-tree` re-parses the reconstructed client documents
(`clientes/CLIENTE_NNN/DIETA__vNN.md`, which keep the original headers) as an INDEPENDENT check of every move.

Usage (from the repository root):
  python pipeline/src/data_tools/resplit_slots.py --in <v1>/diets.jsonl --out-dir <v2> --verify-tree
  python pipeline/src/data_tools/resplit_slots.py --in <v1>/diets.jsonl --out-dir <v2> --dry-run

Prints counts only (the corpus text carries no names).
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from pipeline.paths import data_dir, dataset_dir  # noqa: E402

LEXICON = Path(__file__).resolve().parents[1] / "pipeline" / "data" / "slot_labels.json"
NUMSTART = re.compile(r"^\s*(?:\d+[.,]?\d*|½|¼|¾|\d+/\d+)\b")
MD_HEADER = re.compile(
    r"^(DESAYUNO|MEDIA MANANA|MEDIA TARDE|ALMUERZO|COMIDA|MERIENDA|CENA|RECENA|ANTES DE ENTRENAR|DESPUES DE ENTRENAR|"
    r"DESPUES ENTRENAR|MITAD DE ENTRENAMIENTO|BATIDO|NOTAS?|OBJETIVO|DIETA)\b")


def norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", str(s))
    return "".join(c for c in s if not unicodedata.combining(c)).upper().strip()


def split_label(line: str) -> str | None:
    """Text before the first colon that is not inside parentheses (his times carry colons: «MEDIA TARDE (18:00):»)."""
    depth = 0
    for i, ch in enumerate(line):
        if ch in "([":
            depth += 1
        elif ch in ")]":
            depth = max(0, depth - 1)
        elif ch == ":" and depth == 0:
            return line[:i]
    return None


def group_key(label: str) -> str:
    s = re.sub(r"\([^)]*\)?", " ", label)
    s = re.sub(r"\[[^\]]*\]?", " ", s)
    s = re.sub(r"\b\d{1,2}[.:]\d{2}\b", " ", s)
    s = re.sub(r"[+\-]?\s*\d+\s*(?:H|HORAS?|MIN|MINUTOS?)?\b", " ", s)
    s = re.sub(r"^[^A-Z]+", " ", s)
    return re.sub(r"\s+", " ", s).strip(" .,-*")


class Lexicon:
    def __init__(self, path: Path):
        raw = json.loads(path.read_text(encoding="utf-8"))
        self.occasions = [(re.compile(o["pattern"]), o["target"]) for o in raw["occasions"]]
        self.signature = re.compile(raw["signature"])
        self.sublabel = re.compile(raw["sublabel"])
        self.variant = re.compile(raw["variant"])
        self.note = re.compile(raw["note"])
        self.known = tuple(raw["known_slots"])

    def classify(self, key: str, components: int, blocks: int) -> tuple[str, str | None]:
        for rx, target in self.occasions:
            if rx.search(key):
                return ("A", target) if target else ("B", None)
        if self.signature.search(key):
            return "E", None
        if self.sublabel.search(key):
            return "B", None
        if self.variant.search(key):
            return "C", None
        if self.note.search(key):
            return "D", None
        if components == 0 or components / max(1, blocks) < 1.0:
            return "D", None
        return "F", None


# --------------------------------------------------------------------------------------------------- builders (verified)

def build_text(d: dict) -> str:
    parts = []
    goal_text = d["meta"].get("goal_text")
    if goal_text is not None:
        parts.append("OBJETIVO: " + goal_text)
    for slot, items in d["meals"].items():
        parts.append(f"{slot}: " + " | ".join(items))
    if d["notes"]:
        parts.append("NOTAS: " + " ".join(d["notes"]))
    return "\n".join(parts)


MEAL_META_DROP = ("goal_text", "item_count", "meal_count", "note_count")


def build_meals(d: dict) -> list[dict]:
    m = d["meta"]
    head = f"[Perfil {m.get('sex') or '?'} {m.get('age_bucket')}, objetivo {m.get('goal')}]"
    base = {k: v for k, v in m.items() if k not in MEAL_META_DROP}
    out = []
    for slot, items in d["meals"].items():
        meta = dict(base)
        meta["diet_id"] = d["id"]
        meta["meal_slot"] = slot
        meta["item_count"] = len(items)
        out.append({"id": f"{d['id']}::{slot}", "text": f"{head} {slot}: " + " | ".join(items), "meta": meta})
    return out


def selftest(diets: list[dict], meals_v1: list[dict]) -> None:
    bad_text = [d["id"] for d in diets if build_text(d) != d["text"]]
    if bad_text:
        raise SystemExit(f"self-test failed: build_text does not reproduce dataset-v1 for {len(bad_text)} diets, e.g. {bad_text[:3]}")
    rebuilt = [m for d in diets for m in build_meals(d)]
    if len(rebuilt) != len(meals_v1):
        raise SystemExit(f"self-test failed: build_meals produced {len(rebuilt)} rows, dataset-v1 has {len(meals_v1)}")
    by_id = {m["id"]: m for m in meals_v1}
    bad = [m["id"] for m in rebuilt if m["id"] not in by_id or m["text"] != by_id[m["id"]]["text"]]
    if bad:
        raise SystemExit(f"self-test failed: build_meals text differs for {len(bad)} rows, e.g. {bad[:3]}")
    print(f"self-test OK: text and meals builders reproduce dataset-v1 exactly ({len(diets)} diets, {len(rebuilt)} meals)")


# ------------------------------------------------------------------------------------------------------------- surgery

def marks_of(items: list[str], lex: Lexicon) -> list[tuple[int, str]]:
    out = []
    for i, x in enumerate(items):
        lab = split_label(norm(x))
        if lab is None:
            continue
        lab = lab.strip()
        if not lab or NUMSTART.match(lab) or len(lab) > 60 or not re.search(r"[A-Z]", lab):
            continue
        key = group_key(lab)
        if not key or any(key.startswith(s) for s in lex.known):
            continue
        out.append((i, key))
    return out


def census(diets: list[dict], lex: Lexicon) -> dict[str, tuple[str, str | None]]:
    """Classify each label family once, over the whole corpus, so the decision does not depend on the diet."""
    blocks, comps = Counter(), Counter()
    for d in diets:
        for slot, items in d["meals"].items():
            ms = marks_of(items, lex)
            for j, (i, key) in enumerate(ms):
                end = ms[j + 1][0] if j + 1 < len(ms) else len(items)
                blocks[key] += 1
                comps[key] += sum(1 for x in items[i + 1:end] if NUMSTART.match(norm(x))) + (1 if NUMSTART.match(norm(split_label(norm(items[i])) or "")) else 0)
    return {k: lex.classify(k, comps[k], blocks[k]) for k in blocks}


def apply_to(d: dict, lex: Lexicon, decision: dict[str, tuple[str, str | None]], log: Counter, moved_detail: dict) -> dict:
    meals: dict[str, list[str]] = {s: list(v) for s, v in d["meals"].items()}
    notes: list[str] = list(d["notes"])
    pending: list[tuple[str, str, list[str]]] = []          # (host, target, block)
    for slot in list(meals):
        items = meals[slot]
        ms = marks_of(items, lex)
        if not ms:
            continue
        keep_until = len(items)
        for j, (i, key) in enumerate(ms):
            cat, target = decision.get(key, ("F", None))
            end = ms[j + 1][0] if j + 1 < len(ms) else len(items)
            block = items[i:end]
            if cat == "A" and target and target != slot:
                pending.append((slot, target, block))
                keep_until = min(keep_until, i)
                log[f"A:{target}"] += 1
                log["A_blocks"] += 1
                moved_detail.setdefault(d["id"], []).append((slot, target, len(block)))
            elif cat == "D":
                notes.extend(x.strip() for x in block if x.strip())
                keep_until = min(keep_until, i)
                log["D_blocks"] += 1
                log["D_notes_recovered"] += len([x for x in block if x.strip()])
            elif cat == "E":
                keep_until = min(keep_until, i)
                log["E_blocks"] += 1
            else:
                log[f"{cat}_blocks_untouched"] += 1
        if keep_until < len(items):
            meals[slot] = items[:keep_until]
    # insert the moved blocks right after their host, preserving document order
    for host, target, block in pending:
        if target in meals:
            meals[target].extend(block)
        else:
            rebuilt: dict[str, list[str]] = {}
            for s, v in meals.items():
                rebuilt[s] = v
                if s == host:
                    rebuilt[target] = list(block)
            if target not in rebuilt:                       # the host slot became empty and was dropped
                rebuilt[target] = list(block)
            meals = rebuilt
    meals = {s: v for s, v in meals.items() if v}
    out = dict(d)
    out["meals"] = meals
    out["notes"] = notes
    meta = dict(d["meta"])
    meta["item_count"] = sum(len(v) for v in meals.values())
    meta["meal_count"] = len(meals)
    meta["note_count"] = len(notes)
    out["meta"] = meta
    out["text"] = build_text(out)
    return out


# -------------------------------------------------------------------------------------- independent check: the .md tree

KNOWN_MD = {"DESAYUNO": "DESAYUNO", "MEDIA MANANA": "MEDIA MAÑANA", "ALMUERZO": "ALMUERZO", "COMIDA": "COMIDA",
            "MERIENDA": "MERIENDA", "CENA": "CENA", "RECENA": "RECENA", "ANTES DE ENTRENAR": "ANTES DE ENTRENAR",
            "DESPUES DE ENTRENAR": "DESPUES DE ENTRENAR", "DESPUES ENTRENAR": "DESPUES DE ENTRENAR", "BATIDO": "BATIDO"}


def tree_slots(md: Path, lex: Lexicon) -> dict[str, list[str]]:
    """Re-parse a reconstructed client document FROM SCRATCH with the corrected header lexicon (the same occasion patterns the
    surgery uses). This is the independent source: these documents keep the professional's original headers."""
    text = md.read_text(encoding="utf-8", errors="ignore")
    m = re.search(r"```\n(.*?)\n```", text, re.S)
    body = m.group(1) if m else text
    slots: dict[str, list[str]] = {}
    cur = None
    for line in body.splitlines():
        if not line.strip():
            continue
        n = norm(line)
        if re.match(r"^(NOTAS?|OBJETIVO|DIETA)\b", n):
            cur = None
            continue
        target = next((v for k, v in KNOWN_MD.items() if n.startswith(k)), None)
        if target is None:
            lab = split_label(n)
            if lab is not None:
                key = group_key(lab.strip())
                if key:
                    cat, tgt = lex.classify(key, 1, 1)
                    if cat == "A" and tgt:
                        target = tgt
                    elif cat in ("D", "E"):
                        cur = None
                        continue
        if target:
            cur = target
            rest = line.split(":", 1)[1].strip() if ":" in line else ""
            slots.setdefault(cur, [])
            if rest:
                slots[cur].append(rest)
            continue
        if cur:
            slots.setdefault(cur, []).append(line.strip())
    return slots


def verify_tree(v2: list[dict], moved_detail: dict, tree: Path, lex: Lexicon) -> dict:
    """Independent check: re-parse each affected document with the corrected lexicon and confirm that every slot the surgery
    created for that diet is also a slot of the document."""
    res = Counter()
    mismatches = []
    for d in v2:
        if d["id"] not in moved_detail:
            continue
        client, _, version = d["id"].partition("::")
        md = tree / client / f"DIETA__{version}.md"
        if not md.exists():
            res["no_document"] += 1
            continue
        res["diets_checked"] += 1
        doc = tree_slots(md, lex)
        for host, target, size in moved_detail[d["id"]]:
            res["moves_checked"] += 1
            if target in doc:
                res[f"confirmed:{target}"] += 1
            else:
                res[f"NOT_in_document:{target}"] += 1
                if len(mismatches) < 20:
                    mismatches.append({"diet": d["id"], "host": host, "target": target, "lines": size, "document_slots": sorted(doc)})
    ok = sum(v for k, v in res.items() if k.startswith("confirmed:"))
    bad = sum(v for k, v in res.items() if k.startswith("NOT_in_document:"))
    res["agreement_pct"] = round(100 * ok / max(1, ok + bad), 2)
    return {"counts": dict(res), "examples": mismatches[:8]}


def mark_new_template_groups(v2: list[dict], duplicates: list[dict]) -> tuple[list[dict], list[dict], dict]:
    """Putting the slots back makes visible duplicate meal sets that the fusion was hiding: two clients whose diets differ only in
    where the lost header fell turn out to be the same shared template.

    `sanitize` DROPS a duplicate and keeps one. Doing that here would change the diet set and break comparability with dataset-v1
    (the leave-one-out protocol must stay at the same 746 queries), so v2 keeps both and marks ALL members of the group with a
    template id. That is what matters for the measurement: retrieval excludes the client's own diets AND their template groups, so
    a held-out diet can never be answered with an identical copy belonging to somebody else."""
    import hashlib
    seen: dict[str, list[dict]] = defaultdict(list)
    for d in v2:
        h = hashlib.sha1(json.dumps(d["meals"], sort_keys=True, ensure_ascii=False).encode()).hexdigest()
        seen[h].append(d)
    known = {g["meals_sha1"] for g in duplicates}
    next_id = max((int(g["template_group_id"].split("_")[1]) for g in duplicates if g.get("template_group_id")), default=0)
    added = []
    by_id = {g["template_group_id"]: g for g in duplicates if g.get("template_group_id")}
    for h, group in sorted(seen.items()):
        if len(group) < 2 or h in known:
            continue
        # A member may already belong to a v1 group (its twin was dropped back then). Merge into THAT group instead of minting a
        # new id: overwriting it would drop the old membership and let the dropped twin's client be answered with this diet.
        existing = next((d["meta"]["template_group_id"] for d in group if d["meta"].get("template_group_id")), None)
        if existing:
            tpl = existing
            clients = sorted({d["meta"]["client_code"] for d in group} | set(by_id.get(tpl, {}).get("clients", [])))
            by_id[tpl]["clients"] = clients
            by_id[tpl].setdefault("merged_v2", []).append(h)
        else:
            next_id += 1
            tpl = f"tpl_{next_id:03d}"
            clients = sorted({d["meta"]["client_code"] for d in group})
            added.append({"meals_sha1": h, "kept": [d["id"] for d in group], "dropped": [], "clients": clients,
                          "same_client": len(clients) == 1, "template_group_id": tpl,
                          "resolution": "kept_all_marked_v2", "note": "revealed by the dataset-v2 slot re-split; kept to preserve the LOO protocol"})
        for d in group:
            d["meta"]["template_group_id"] = tpl
            d["meta"]["template_clients"] = clients
    stats = {"new_template_groups": len(added), "diets_marked": sum(len(g["kept"]) for g in added),
             "cross_client": sum(1 for g in added if not g["same_client"])}
    return v2, duplicates + added, stats


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--in", dest="src", type=Path, required=True, help="dataset-v1 diets.jsonl (never modified)")
    ap.add_argument("--out-dir", type=Path, help="directory for the dataset-v2 artefacts")
    ap.add_argument("--tree", type=Path, default=None, help="reconstructed client tree (default: FPS_DATA_DIR/clientes)")
    ap.add_argument("--verify-tree", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    src_dir = args.src.parent
    diets = [json.loads(l) for l in args.src.read_text(encoding="utf-8").splitlines() if l.strip()]
    meals_v1 = [json.loads(l) for l in (src_dir / "meals.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
    selftest(diets, meals_v1)

    lex = Lexicon(LEXICON)
    decision = census(diets, lex)
    cats = Counter(c for c, _ in decision.values())
    print(f"label families: {len(decision)} -> " + ", ".join(f"{k}:{v}" for k, v in sorted(cats.items())))

    log = Counter()
    moved_detail: dict = {}
    v2 = [apply_to(d, lex, decision, log, moved_detail) for d in diets]
    duplicates_v1 = json.loads((src_dir / "duplicates.json").read_text(encoding="utf-8")) if (src_dir / "duplicates.json").exists() else []
    v2, duplicates_v2, dup_stats = mark_new_template_groups(v2, duplicates_v1)
    print("template groups revealed by the re-split:", json.dumps(dup_stats, ensure_ascii=False))

    slots_v1 = Counter(s for d in diets for s in d["meals"])
    slots_v2 = Counter(s for d in v2 for s in d["meals"])
    items_v1 = Counter()
    items_v2 = Counter()
    for d in diets:
        for s, v in d["meals"].items():
            items_v1[s] += len(v)
    for d in v2:
        for s, v in d["meals"].items():
            items_v2[s] += len(v)
    print("\nslot                         diets v1 -> v2        raw items v1 -> v2")
    for s in sorted(set(slots_v1) | set(slots_v2), key=lambda x: -max(slots_v1.get(x, 0), slots_v2.get(x, 0))):
        print(f"  {s:24} {slots_v1.get(s, 0):5} -> {slots_v2.get(s, 0):5}   {items_v1.get(s, 0):7} -> {items_v2.get(s, 0):7}")
    notes_v1 = sum(len(d["notes"]) for d in diets)
    notes_v2 = sum(len(d["notes"]) for d in v2)
    zero_v1 = sum(1 for d in diets if not d["notes"])
    zero_v2 = sum(1 for d in v2 if not d["notes"])
    print(f"\nnotes: {notes_v1} -> {notes_v2} (mean {notes_v1 / len(diets):.2f} -> {notes_v2 / len(v2):.2f}) | diets with zero notes: {zero_v1} -> {zero_v2}")
    print("blocks:", json.dumps({k: v for k, v in sorted(log.items())}, ensure_ascii=False))

    report = {"source": Path(args.src).name,          # name only: an absolute path carries the owner name (see build_validated_rules) "diets": len(v2), "label_families": len(decision),
              "categories": dict(cats), "blocks": dict(log),
              "slots_diets_v1": dict(slots_v1), "slots_diets_v2": dict(slots_v2),
              "slots_items_v1": dict(items_v1), "slots_items_v2": dict(items_v2),
              "notes_v1": notes_v1, "notes_v2": notes_v2, "diets_zero_notes_v1": zero_v1, "diets_zero_notes_v2": zero_v2,
              "decision": {k: {"category": c, "target": t} for k, (c, t) in sorted(decision.items())}}

    if args.verify_tree:
        tree = args.tree or (data_dir() / "clientes")
        v = verify_tree(v2, moved_detail, tree, lex)
        print("\ncross-check against the reconstructed documents:", json.dumps(v["counts"], ensure_ascii=False))
        for ex in v["examples"]:
            print("   mismatch:", ex)
        report["tree_verification"] = v["counts"]

    if args.dry_run or not args.out_dir:
        print("\n(dry run: nothing written)")
        return 0
    args.out_dir.mkdir(parents=True, exist_ok=True)
    (args.out_dir / "diets.jsonl").write_text("\n".join(json.dumps(d, ensure_ascii=False) for d in v2) + "\n", encoding="utf-8", newline="\n")
    meals = [m for d in v2 for m in build_meals(d)]
    (args.out_dir / "meals.jsonl").write_text("\n".join(json.dumps(m, ensure_ascii=False) for m in meals) + "\n", encoding="utf-8", newline="\n")
    (args.out_dir / "duplicates.json").write_text(json.dumps(duplicates_v2, ensure_ascii=False, indent=1), encoding="utf-8", newline="\n")
    report["template_groups_revealed"] = dup_stats
    (args.out_dir / "resplit_slots_log.json").write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8", newline="\n")
    print(f"\nwritten: {args.out_dir / 'diets.jsonl'} ({len(v2)} diets), meals.jsonl ({len(meals)} meals), resplit_slots_log.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
