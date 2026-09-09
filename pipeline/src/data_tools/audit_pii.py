# -*- coding: utf-8 -*-
"""
PII audit over .json / .jsonl corpus files. Produces COUNTS ONLY.

Usage:
  python _tools/audit_pii.py --name-map _dataset/_private/name_map.json \
      --false-positives _dataset/_private/reviewed_false_positives.json \
      --out _dataset/_private/initial_audit.json --label before \
      _meta/chunks_dietas.jsonl _meta/dietas_estructuradas.json _meta/perfiles.json ...

For every file and every (flattened) field it counts:
  - name_dict            : tokens present in the real-name dictionary (name map),
                           excluding STOPWORDS (food / diet lexicon) and the
                           private list of reviewed false positives.
  - name_dict_raw        : same without any exclusion (upper bound).
  - id_token_not_allowed : in identifier fields (id / archivo / md / file), any
                           alphabetic token that is not CLIENTE / DIETA / md / v / s / meal slot.
  - email, phone, dni, nie, iban, full_date, birth_year, url_or_domain,
    professional_domain, marker_*, rtf_residue, form_line, raw_regex_label.
  - medical_term         : in profile free-text fields.

Never writes tokens or text to stdout or to the output JSON: only affected
records, number of occurrences and number of distinct tokens.
"""
from __future__ import annotations

import argparse
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pii_common import (  # noqa: E402
    require_custody_patterns,
    DETECTORS, MEDICAL_RE, PROFILE_FREE_TEXT, alpha_tokens_not_allowed, iter_strings,
    load_name_tokens, load_records, load_reviewed_false_positives, name_tokens_in, write_json,
)

ID_FIELDS = {"id", "meta.archivo", "archivo", "docs[].md", "docs[].file", "docs[].desc",
             "code", "client_code", "meta.cliente", "meta.client_code", "cliente", "diet_id"}
TEXT_FIELDS = {"text", "objetivo", "goal_text", "notas[]", "notes[]", "comidas.<items>", "meals.<items>",
               "comidas.<key>", "meals.<key>"} | set(PROFILE_FREE_TEXT)


def audit_file(path: Path, name_set: set[str], fp_set: set[str]) -> dict:
    rows = load_records(path)
    per_field: dict[str, dict[str, dict]] = defaultdict(lambda: defaultdict(lambda: {"occurrences": 0, "_tok": set()}))
    rec_hits: dict[str, dict[str, set]] = defaultdict(lambda: defaultdict(set))

    def bump(field, det, idx, n_occ, toks=()):
        cell = per_field[field][det]
        cell["occurrences"] += n_occ
        cell["_tok"].update(toks)
        rec_hits[field][det].add(idx)

    for idx, rec in enumerate(rows):
        for field, s in iter_strings(rec):
            if not s:
                continue
            base = field.split("[]")[0] if field.endswith("[]") else field
            toks = name_tokens_in(s, name_set, use_stop=True, extra_stop=fp_set)
            if toks:
                bump(field, "name_dict", idx, len(toks), toks)
            toks_raw = name_tokens_in(s, name_set, use_stop=False)
            if toks_raw:
                bump(field, "name_dict_raw", idx, len(toks_raw), toks_raw)
            if base in ID_FIELDS or field in ID_FIELDS:
                bad = alpha_tokens_not_allowed(s)
                if bad:
                    bump(field, "id_token_not_allowed", idx, len(bad), bad)
            for det, rx in DETECTORS.items():
                m = rx.findall(s)
                if m:
                    bump(field, det, idx, len(m))
            if base in PROFILE_FREE_TEXT or field in PROFILE_FREE_TEXT:
                mm = MEDICAL_RE.findall(s)
                if mm:
                    bump(field, "medical_term", idx, len(mm))

    fields_out = {}
    for field, dets in per_field.items():
        fields_out[field] = {}
        for det, cell in dets.items():
            fields_out[field][det] = {
                "records": len(rec_hits[field][det]),
                "occurrences": cell["occurrences"],
                "distinct_tokens": len(cell["_tok"]) if cell["_tok"] else None,
            }
    tot_rec: dict[str, set] = defaultdict(set)
    tot_occ: Counter = Counter()
    tot_tok: dict[str, set] = defaultdict(set)
    for field, dets in per_field.items():
        for det, cell in dets.items():
            tot_rec[det] |= rec_hits[field][det]
            tot_occ[det] += cell["occurrences"]
            tot_tok[det] |= cell["_tok"]
    totals = {det: {"records": len(tot_rec[det]), "occurrences": tot_occ[det],
                    "distinct_tokens": len(tot_tok[det]) if tot_tok[det] else None}
              for det in sorted(tot_rec)}

    id_like = [f for f in fields_out if f in ID_FIELDS or f.split("[]")[0] in ID_FIELDS]
    acceptance = {
        "names_in_identifiers_by_field": {f: fields_out[f].get("name_dict", {}).get("records", 0) for f in id_like},
        "not_allowed_tokens_in_identifiers_by_field": {f: fields_out[f].get("id_token_not_allowed", {}).get("records", 0) for f in id_like},
        "names_in_non_text_metadata_by_field": {f: v["name_dict"]["records"] for f, v in fields_out.items()
                                                 if "name_dict" in v and f not in TEXT_FIELDS and f not in id_like},
        "names_in_free_text_by_field": {f: v["name_dict"]["records"] for f, v in fields_out.items()
                                        if "name_dict" in v and f in TEXT_FIELDS},
    }
    acceptance["max_names_in_identifiers"] = max(acceptance["names_in_identifiers_by_field"].values(), default=0)
    acceptance["max_not_allowed_tokens_in_identifiers"] = max(acceptance["not_allowed_tokens_in_identifiers_by_field"].values(), default=0)
    acceptance["max_names_in_non_text_metadata"] = max(acceptance["names_in_non_text_metadata_by_field"].values(), default=0)
    return {"file": path.name, "records": len(rows), "fields": fields_out, "totals": totals, "acceptance": acceptance}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("inputs", nargs="+", type=Path, help=".json/.jsonl files to audit")
    ap.add_argument("--name-map", required=True, type=Path, help="name_map.json (dictionary; never printed)")
    ap.add_argument("--false-positives", type=Path, help="private JSON list of reviewed non-personal dictionary hits")
    ap.add_argument("--out", required=True, type=Path, help="output JSON with the counts")
    ap.add_argument("--label", default="", help="free label (e.g. 'before' / 'after')")
    args = ap.parse_args()
    # Una auditoría sin su diccionario no dice «limpio», dice «no he podido mirar». Aborta.
    require_custody_patterns("audit_pii")

    name_set = load_name_tokens(args.name_map)
    fp_set = load_reviewed_false_positives(args.false_positives)
    report = {"label": args.label, "dictionary_tokens": len(name_set), "reviewed_false_positives": len(fp_set), "files": []}
    for p in args.inputs:
        r = audit_file(p, name_set, fp_set)
        report["files"].append(r)
        print(f"[{r['file']}] records={r['records']}")
        for det, v in r["totals"].items():
            print(f"    {det:26s} records={v['records']:5d} occurrences={v['occurrences']:6d}"
                  + (f" distinct_tokens={v['distinct_tokens']}" if v["distinct_tokens"] is not None else ""))
        a = r["acceptance"]
        print(f"    >> ACCEPTANCE names in identifiers (max by field): {a['max_names_in_identifiers']} {a['names_in_identifiers_by_field']}")
        print(f"    >>            not-allowed tokens in identifiers:   {a['max_not_allowed_tokens_in_identifiers']} {a['not_allowed_tokens_in_identifiers_by_field']}")
        print(f"    >>            names in non-text metadata:          {a['max_names_in_non_text_metadata']} {a['names_in_non_text_metadata_by_field']}")
        print(f"    >>            names in free text (to review):      {a['names_in_free_text_by_field']}")
    write_json(args.out, report)
    print(f"\nReport written to {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
