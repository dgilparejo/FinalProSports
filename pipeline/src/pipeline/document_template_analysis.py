# -*- coding: utf-8 -*-
"""
S6 — What is constant in the professional's diet DOCUMENT and what varies, measured over the reconstructed documents.

Input:  $FPS_DATA_DIR/clientes/CLIENTE_NNN/DIETA__vNN.md   (text of every diet document, names and contacts already replaced by
        [NOMBRE] / [EMAIL] / [TEL] placeholders — the tree audit keeps it at criterion zero)
Output: docs/architecture/pdf_template.md — GENERATED, not versioned (aggregates only: prevalence of each element, never a document)

The custody with the original .odt / .rtf / .pdf files is closed (password held by the owner only), so the VISUAL layout (fonts, logo
position, columns) cannot be observed here; what CAN be observed — and is what the PDF exporter reproduces — is the text template:
header line, «OBJETIVO:» line, slot labels with their parenthetical hints, the «qty unit Food / alt» item lines, the training lines,
the «Notas:» block with «-» bullets and the contact footer. Every number in the report is a share of documents.
"""
from __future__ import annotations

import json
import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from pipeline import DOCS_DIR, data_dir  # noqa: E402

HEADER = re.compile(r"^DIETA\b.*?(\d{1,2}\s*/\s*\d{1,2}\s*/\s*\d{2,4})?\s*$", re.I)
DATE = re.compile(r"\d{1,2}\s*/\s*\d{1,2}\s*/\s*\d{2,4}")
SLOT = re.compile(r"^(RECI[EÉ]N LEVANTAD[OA]|DESAYUNO|MEDIA M[AÁ][ÑN][AÁ]N[AÁ]|ALMUERZO|COMIDA|MERIENDA|CENA|RECENA|BATIDO|ANTES DE ENTRENAR|DESPU[EÉ]S (?:DE )?ENTRENAR[^:]*|AL LEVANTARSE)\s*(\(([^)]*)\))?\s*:", re.I)
ITEM_UNIT = re.compile(r"^\s*\d+(?:[.,]\d+)?\s*(gr|grs|g|ml|cl|l|ud|uds|unidad(?:es)?|cucharad(?:a|ita)s?|latas?|lonchas?|rodajas?|cazos?|c[aá]psulas?|puñados?|dientes?)\b", re.I)
ALT = " / "
NOTES = re.compile(r"^\s*notas?\s*:?\s*$", re.I)
BULLET = re.compile(r"^\s*[-–•*]")
FOOTER_EMAIL, FOOTER_TEL = re.compile(r"\[EMAIL\]"), re.compile(r"\[TEL\]|^\s*tel\b", re.I)
OBJ = re.compile(r"^OBJETIVO\s*:", re.I)


def analyse(root: Path) -> dict:
    docs = sorted(root.glob("CLIENTE_*/DIETA__v*.md"))
    c = Counter()
    slot_hints: dict[str, Counter] = {}
    units: Counter = Counter()
    n_slots: list[int] = []
    positions: Counter = Counter()          # where the notes block sits: after the last slot?
    for p in docs:
        text = p.read_text(encoding="utf-8", errors="ignore")
        body = text.split("```", 2)
        lines = [l.rstrip() for l in (body[1] if len(body) >= 2 else text).splitlines()]
        lines = [l for l in lines if l.strip()]
        if not lines:
            continue
        c["docs"] += 1
        first = lines[0]
        if HEADER.match(first):
            c["header_starts_with_DIETA"] += 1
            if DATE.search(first):
                c["header_has_date"] += 1
        if any(OBJ.match(l) for l in lines[:4]):
            c["objetivo_line_in_first_4"] += 1
        slots_here = 0
        seen_notes = False
        for l in lines:
            m = SLOT.match(l)
            if m:
                slots_here += 1
                name = re.sub(r"\s+", " ", m.group(1).upper().replace("É", "E").replace("Ñ", "N"))
                name = re.sub(r"^(DESPUES) (DE )?ENTRENAR.*$", r"DESPUES ENTRENAR", name)
                slot_hints.setdefault(name, Counter())["__docs__"] += 1
                if m.group(3):
                    slot_hints[name][m.group(3).strip().lower()[:60]] += 1
                continue
            mu = ITEM_UNIT.match(l)
            if mu:
                units[mu.group(1).lower()] += 1
                if ALT in l or " o " in l.lower():
                    c["item_lines_with_alternatives"] += 1
                c["item_lines_with_unit"] += 1
            if NOTES.match(l):
                seen_notes = True; c["notes_block"] += 1
            elif seen_notes and BULLET.match(l):
                c["note_bullets"] += 1
            if FOOTER_EMAIL.search(l):
                c["footer_email"] += 1
            if FOOTER_TEL.search(l):
                c["footer_tel"] += 1
        n_slots.append(slots_here)
        if seen_notes:
            c["docs_with_notes"] += 1
        if any(FOOTER_EMAIL.search(l) or FOOTER_TEL.search(l) for l in lines[-4:]):
            c["footer_contact_in_last_4_lines"] += 1
    n = max(1, c["docs"])
    share = {k: round(v / n, 3) for k, v in c.items() if k != "docs"}
    hints = {}
    for slot, cnt in sorted(slot_hints.items(), key=lambda t: -t[1]["__docs__"]):
        total = cnt.pop("__docs__")
        hints[slot] = {"docs_share": round(total / n, 3), "hint_share": round(sum(cnt.values()) / total, 3) if total else 0.0,
                       "top_hints": [(h, round(v / total, 3)) for h, v in cnt.most_common(4)]}
    return {"docs": c["docs"], "share": share, "units": [(u, v) for u, v in units.most_common(8)], "slots": hints,
            "slots_per_doc": {"min": min(n_slots) if n_slots else 0, "median": sorted(n_slots)[len(n_slots) // 2] if n_slots else 0, "max": max(n_slots) if n_slots else 0},
            "docs_with_notes_share": round(c["docs_with_notes"] / n, 3), "bullets_per_notes_doc": round(c["note_bullets"] / max(1, c["docs_with_notes"]), 2)}


def markdown(r: dict) -> str:
    s = r["share"]
    L = ["# Plantilla del documento de dieta del profesional (S6)", "",
         f"Medido sobre los **{r['docs']} documentos de dieta reconstruidos** (`clientes/CLIENTE_NNN/DIETA__vNN.md`, texto sin nombres). La custodia con los",
         "originales (odt / rtf / doc / pdf) está cerrada —la contraseña la tiene solo el autor—, así que **la maquetación visual (tipografía, posición del",
         "logo, columnas) no ha podido observarse en este sprint**: lo que se reproduce es la plantilla TEXTUAL, que sí es observable y constante. La",
         "comparación visual con un original (captura con nombre, teléfono y correo tapados) queda pendiente de extraer tres o cuatro",
         "documentos a `docs/reference/_work/` (carpeta ignorada por git) y se anote aquí lo que difiera.", "",
         "## Elementos constantes (≥ 90 % de los documentos)", "", "| Elemento | Cuota |", "|---|---|"]
    rows = [("Primera línea `DIETA <cliente> DD / MM / AA`", s.get("header_starts_with_DIETA", 0)), ("… con fecha en la cabecera", s.get("header_has_date", 0)),
            ("Línea `OBJETIVO: …` en las primeras cuatro líneas", s.get("objetivo_line_in_first_4", 0)), ("Bloque `Notas:`", r["docs_with_notes_share"]),
            ("Contacto (correo / teléfono) en las últimas líneas", s.get("footer_contact_in_last_4_lines", 0))]
    for name, v in rows:
        L.append(f"| {name} | {v:.0%} |")
    L += ["", f"Franjas por documento: mín. {r['slots_per_doc']['min']}, mediana {r['slots_per_doc']['median']}, máx. {r['slots_per_doc']['max']}. "
          f"Viñetas por bloque de notas: {r['bullets_per_notes_doc']} de media (marcador «-»).", "",
          "## Franjas: etiqueta en mayúsculas seguida de dos puntos, con indicación entre paréntesis según el objetivo", "",
          "| Franja | Documentos | Con indicación | Indicaciones más frecuentes |", "|---|---|---|---|"]
    for slot, h in r["slots"].items():
        top = "; ".join(f"«{t}» {v:.0%}" for t, v in h["top_hints"]) or "—"
        L.append(f"| {slot} | {h['docs_share']:.0%} | {h['hint_share']:.0%} | {top} |")
    L += ["", "## Ítems", "",
          f"Línea `cantidad unidad Alimento` con alternativas separadas por ` / `: {s.get('item_lines_with_alternatives', 0):.0%} de las líneas con unidad llevan alternativas. "
          "Unidades tal como las escribe (las más frecuentes): " + ", ".join(f"`{u}` ({v})" for u, v in r["units"]) + ". El exportador usa **`gr`** para gramos, como él.", "",
          "## Lo que varía", "",
          "- La indicación entre paréntesis de COMIDA y CENA depende del objetivo (ayuno / cetosis: «lo más tarde que puedas» / «lo más temprano que puedas»).",
          "- El número y el orden de las franjas (2–7), la presencia de ANTES / DESPUÉS DE ENTRENAR y RECIÉN LEVANTADO.",
          "- La longitud del bloque de notas (0–10 viñetas) y su redacción, en mayúsculas o minúsculas.", "",
          "## Lo que el exportador reproduce (`domain/composition/policy/document_template_policy.py`)", "",
          "Cabecera `DIETA <nombre del expediente o código> <fecha>`, `OBJETIVO:` con el texto del objetivo, franjas en mayúsculas con su indicación por",
          "objetivo, ítems `cantidad gr Alimento / alternativa`, líneas de entrenamiento, `Notas:` con viñetas «-», y pie con la marca del profesional",
          "(logo) y el contacto configurado (`PROFESSIONAL_CONTACT`, vacío por defecto: ningún dato real entra en el repositorio).", ""]
    return "\n".join(L)


def main() -> int:
    r = analyse(data_dir() / "clientes")
    (DOCS_DIR / "architecture" / "pdf_template.md").write_text(markdown(r), encoding="utf-8", newline="\n")
    print(json.dumps({k: v for k, v in r.items() if k != "slots"} | {"slots": {k: v["docs_share"] for k, v in r["slots"].items()}}, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
