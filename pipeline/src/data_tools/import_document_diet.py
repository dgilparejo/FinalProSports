"""Import a diet the professional wrote himself, from his own document, into a portfolio client's history.

Why this is a repository tool and not a throwaway script: the two diets of the real client were imported once with an
ad-hoc script that was never committed, and when the extractor was fixed there was nothing to re-run -- their history
kept the OLD extraction (a `Recién levantado` block sitting in the generic bucket and no post-workout slot at all) and
the rotation composer was routing on it. A saved diet that came from a document has to be reproducible from the
document, or the corpus can be rebuilt while the client's own history silently stays at the previous vocabulary.

It reuses the v3 extractor (`pipeline_v3.extract_diets.parse_document`) and the E1 item parser, so an imported diet is
read with exactly the same vocabulary as a corpus diet: the same slot rules, the same alternative splitting, the same
canonical foods. Nothing about the document is re-interpreted here.

Personal data. The input IS an original document: it carries the client's name and the professional's contact details.
Neither is read into the payload. Only the meal blocks and the notes are, and both pass a redaction pass first:

  * the pharmacological guard (`pipeline.excluded.must_drop`) drops a note that PRESCRIBES an excluded substance;
  * a contact line -- phone, e-mail, postal address -- is dropped wherever it appears, because the professional's
    footer sits at the end of the last page and the splitter reads it as one more component of the last slot. In the
    corpus this never shows up (those documents were anonymised upstream); from an original it does, and it did: the
    second document contributed a phone number as a food item.

Usage (needs the document, so it only runs on the owner's machine):

    python pipeline/src/data_tools/import_document_diet.py --document "<path>.odt" \
        --client-code <uuid> --edition 2 [--apply]
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "pipeline" / "src"))
sys.path.insert(0, str(ROOT / "backend" / "src"))

from pipeline import excluded, parse_items                          # noqa: E402
from pipeline.normalize_diets import DESCRIPTOR_ONLY, normalize_key, resolve  # noqa: E402
from pipeline_v3 import convert, extract_diets, paths               # noqa: E402

# A line that is contact information rather than food. Deliberately generous: a false positive costs one component of
# a diet, a false negative writes the professional's phone number into the database as a food item, which is what
# happened. Every pattern is anchored on a shape (digits, @, street prefix), never on a literal value.
_CONTACT = (
    re.compile(r"(?:\+\s*\d{2}\s*)?\d[\d\s().-]{7,}\d"),                       # phone, with or without country code
    re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+"),                                    # e-mail
    re.compile(r"\b(?:c/|calle|avda|avenida|pza)\b", re.I),                    # postal address
    re.compile(r"\bwww\.|https?://", re.I),
)


def is_contact(text: str) -> bool:
    """True when the line is contact information. A quantity is not: '250-300-350 GR. DE PESCADO' has digits but its
    letters are food, so a line only counts as contact when what is left after removing the digits is too short to be
    a food component."""
    for pattern in _CONTACT[1:]:
        if pattern.search(text):
            return True
    if _CONTACT[0].search(text) and len(re.sub(r"[\d\s().+-]", "", text)) < 12:
        return True
    return False


def build_payload(document: Path, *, edition: int, profile: dict, catalog: dict) -> dict:
    parsed = extract_diets.parse_document(convert.from_odt(document))
    case_id = f"DOC::e{edition:02d}"
    by_name = {f["canonical_name"]: f for f in catalog["foods"]}
    key_index = {k: f["canonical_name"] for f in catalog["foods"] for k in f["keys"]}

    meals, dropped = [], {"contact": 0, "prescription": 0, "unmapped": 0}
    for slot, raw_items in parsed["meals"].items():
        groups = []
        for position, raw in enumerate(raw_items):
            if is_contact(raw):
                dropped["contact"] += 1
                continue
            options = []
            components = parse_items.parse_item(raw, f"{case_id}::{slot}::{position}")
            for component in components:
                if component.is_noise or component.is_instruction or not component.food_text:
                    continue
                key = normalize_key(component.food_text)
                if not key or key in DESCRIPTOR_ONLY:
                    continue
                canonical = resolve(key, key_index)
                if canonical is None:
                    dropped["unmapped"] += 1
                    continue
                food = by_name[canonical]
                options.append({
                    "text": component.raw_text, "note": component.note,
                    "food_id": food["id"], "canonical_name": canonical, "normalized_key": key,
                    "quantity": component.quantity.value, "unit": component.quantity.unit.value,
                    "display_name": None, "alternative_group": component.alternative_group,
                    "compound_group": component.compound_group,
                    "evidence": {"cases": [case_id], "rules": [], "support": 1.0},
                })
            # Una línea no es un grupo. «1 Batido de 40gr proteínas CON 30 gr Amilopeptinas + 2 Sales minerales» son
            # tres cosas que se toman JUNTAS (compuesto), no tres entre las que elegir; metidas en un mismo grupo se
            # imprimen separadas por «o» y la rotación arrastra esa estructura a las propuestas siguientes, que es
            # como el multivitamínico acabó ofrecido como alternativa de los minerales. Se agrupa por
            # `alternative_group`: lo que él escribió con «/» va junto; lo demás, cada uno en su grupo.
            por_alternativa: dict[str | None, list[dict]] = {}
            for option in options:
                clave = option["alternative_group"] or f"solo::{len(por_alternativa)}::{option['food_id']}"
                por_alternativa.setdefault(clave, []).append(option)
            for miembros in por_alternativa.values():
                groups.append({"position": len(groups), "options": miembros})
        if groups:
            meals.append({"slot": slot, "groups": groups})

    notes = []
    for note in parsed.get("notes", ()):
        if is_contact(note):
            dropped["contact"] += 1
        elif excluded.must_drop(note):
            dropped["prescription"] += 1
        else:
            notes.append(note)

    payload = {
        "meals": meals, "notes": notes, "profile": profile, "strategy": "imported_document",
        "parameters": {"source": "document", "routing": "imported", "goal_text": parsed.get("goal_text"),
                       "document_date": parsed.get("doc_date"), "edition": edition},
        "validation": {"violations": [], "applied": []}, "retrieved_case_ids": [case_id],
    }
    return {"payload": payload, "dropped": dropped, "slots": [m["slot"] for m in meals]}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--document", type=Path, required=True)
    ap.add_argument("--client-code", required=True)
    ap.add_argument("--edition", type=int, required=True)
    ap.add_argument("--apply", action="store_true", help="write to saved_diets; without it, report only")
    args = ap.parse_args()

    from finalprosports.infrastructure.config.persistence import make_session_factory
    from finalprosports.infrastructure.config.settings import Settings
    from sqlalchemy import text

    catalog = json.loads((paths.dataset_dir_v3() / "foods.json").read_text(encoding="utf-8"))
    session_factory = make_session_factory(Settings().database_url)
    diet_id = f"{args.client_code}::e{args.edition:02d}"
    with session_factory() as session:
        previous = session.execute(text("select payload from saved_diets where id = :i"), {"i": diet_id}).scalar()
        if previous is None:
            print(f"no existe {diet_id}: hace falta el perfil de una dieta ya guardada para reimportar")
            return 1
        profile = previous["profile"]
        created = session.execute(text("select created_at from saved_diets where id = :i"), {"i": diet_id}).scalar()

        result = build_payload(args.document, edition=args.edition, profile=profile, catalog=catalog)
        before = [m["slot"] for m in previous["meals"]]
        print(f"{diet_id}\n  franjas antes  : {before}\n  franjas ahora  : {result['slots']}")
        print(f"  descartado     : {result['dropped']}")
        print(f"  notas          : {len(previous.get('notes', []))} -> {len(result['payload']['notes'])}")
        if not args.apply:
            print("  (simulación: sin --apply no se escribe)")
            return 0
        session.execute(text("update saved_diets set payload = :p where id = :i"),
                        {"p": json.dumps(result["payload"], ensure_ascii=False), "i": diet_id})
        session.commit()
        print(f"  escrito (created_at {created} intacto)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
