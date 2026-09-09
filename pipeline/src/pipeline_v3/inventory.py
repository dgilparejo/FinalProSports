"""F1 -- inventory and conversion: one row per input file, totals that add up (principle 2).

Walks the raw source tree, converts every document (see :mod:`pipeline_v3.convert`) and writes
``manifest.jsonl`` -- one record per input file, including the ones that produced nothing and why.

Client identity comes from the first path component under the sources root. The mapping from that real folder name
to ``CLIENTE_NNN`` is *never* written here: it is derived in :mod:`pipeline_v3.anonymize` and kept in the private
directory outside the repository. This module only ever emits the pseudonym and salted hashes.

Usage::

    python pipeline/src/pipeline_v3/inventory.py [--no-cache] [--limit N]
"""
from __future__ import annotations

import argparse
import collections
import json
import re
import sys
import time
import unicodedata
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from pipeline_v3 import convert, identity, paths
    from pipeline_v3.identity import client_key, load_or_build_registry
else:
    from . import convert, identity, paths
    from .identity import client_key, load_or_build_registry

# A date written in the original file name. Captured HERE, before the name is masked: the masked manifest keeps no
# name, and the report date is needed to place a lab result relative to a diet. A bare date is not an identifier.
_MONTHS = {"ENERO": 1, "FEBRERO": 2, "MARZO": 3, "ABRIL": 4, "MAYO": 5, "JUNIO": 6, "JULIO": 7,
           "AGOSTO": 8, "SEPTIEMBRE": 9, "SETIEMBRE": 9, "OCTUBRE": 10, "NOVIEMBRE": 11, "DICIEMBRE": 12}

# The corpus writes report dates four ways, and the bare six-digit DDMMYY form is the commonest one by far --
# "Analitica ... 070224.pdf". A pattern that only knows separated and ISO-style dates finds none of them.
_NAME_DATE_SEP = re.compile(r"(?<!\d)(\d{1,2})[._\-/](\d{1,2})[._\-/](\d{2,4})(?!\d)")
_NAME_DATE_ISO = re.compile(r"(?<!\d)(20\d{2})[-_.]?(0[1-9]|1[0-2])[-_.]?(0[1-9]|[12]\d|3[01])(?!\d)")
_NAME_DATE_DDMMYY = re.compile(r"(?<!\d)(0[1-9]|[12]\d|3[01])(0[1-9]|1[0-2])(\d{2})(?!\d)")
_NAME_DATE_YEARMONTH = re.compile(r"(?<!\d)(20\d{2})\D{1,3}(" + "|".join(_MONTHS) + r")\b", re.I)


def date_in_name(name: str) -> str | None:
    """A date written in the file name, or None. Tries the four conventions the corpus actually uses."""
    from datetime import date as _date

    def make(year: int, month: int, day: int) -> str | None:
        if year < 100:
            year += 2000 if year < 70 else 1900
        if not (1990 <= year <= 2030 and 1 <= month <= 12 and 1 <= day <= 31):
            return None
        try:
            return _date(year, month, day).isoformat()
        except ValueError:
            return None

    match = _NAME_DATE_ISO.search(name)
    if match:
        found = make(int(match.group(1)), int(match.group(2)), int(match.group(3)))
        if found:
            return found
    match = _NAME_DATE_SEP.search(name)
    if match:
        found = make(int(match.group(3)), int(match.group(2)), int(match.group(1)))
        if found:
            return found
    match = _NAME_DATE_DDMMYY.search(name)
    if match:
        found = make(int(match.group(3)), int(match.group(2)), int(match.group(1)))
        if found:
            return found
    match = _NAME_DATE_YEARMONTH.search(name)
    if match:
        return make(int(match.group(1)), _MONTHS[match.group(2).upper()], 1)
    return None


_WORD_RE = re.compile(r"[A-Za-zÁÉÍÓÚÑÜáéíóúñü]{3,}")

AUDIO_EXT = {".au", ".mp3", ".wav", ".aup", ".m4a", ".ogg"}
IMAGE_EXT = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".tif", ".tiff"}


# --------------------------------------------------------------------------------- content-based classification

def _fold(text: str) -> str:
    text = unicodedata.normalize("NFKD", text)
    return "".join(c for c in text if not unicodedata.combining(c)).upper()


# Each rule is (label, weight, compiled pattern). A document gets the label with the highest total weight;
# ties and zero-score documents are reported as ``unclassified`` rather than being forced into a bucket.
_SIGNALS: list[tuple[str, int, re.Pattern]] = [
    # diet: meal-slot headers and the objective line
    ("diet", 3, re.compile(r"^\s*(DESAYUNO|MEDIA\s*MANANA|ALMUERZO|COMIDA|MERIENDA|MEDIA\s*TARDE|CENA|RECENA|ANTES DE (ENTRENAR|DORMIR)|DESPUES DE ENTRENAR|POST[- ]?ENTRENO|PRE[- ]?ENTRENO)\s*[:.\-]", re.M)),
    ("diet", 2, re.compile(r"\bOBJETIVO\s*[:.\-]")),
    ("diet", 1, re.compile(r"\b\d+\s*(GR|GRS|GRAMOS|ML|CL)\b")),
    # questionnaire: the labelled personal-data sheet
    ("questionnaire", 3, re.compile(r"\bGUSTOS\s+(POSITIVOS|NEGATIVOS)\s*[:.\-]")),
    ("questionnaire", 3, re.compile(r"\bVICIOS\s+ALIMENTICIOS\s*[:.\-]")),
    ("questionnaire", 3, re.compile(r"\bHORARIOS?\s+DE\s+(TRABAJO|ENTRENAMIENTO)\s*[:.\-]")),
    ("questionnaire", 2, re.compile(r"\bOPERAC\s*IONES\s*[:.\-]")),
    ("questionnaire", 2, re.compile(r"\bTIEMPO\s+ENTRENANDO\s*[:.\-]")),
    ("questionnaire", 2, re.compile(r"\bLOGROS\s+DEPORTIVOS\s*[:.\-]")),
    ("questionnaire", 2, re.compile(r"\b(FUMA|BEBE\s+ALCOHOL)\s*[:.\-]")),
    ("questionnaire", 1, re.compile(r"\b(MUNECA|CINTURA|CUELLO|CADERA)\s*[:.\-]")),
    # training plan
    ("training", 3, re.compile(r"\b\d+\s*(SERIES?|X)\s*\d+\s*(REPS?|REPETICIONES)", re.I)),
    ("training", 3, re.compile(r"^\s*(LUNES|MARTES|MIERCOLES|JUEVES|VIERNES|SABADO|DOMINGO)\s*[:.\-]", re.M)),
    ("training", 2, re.compile(r"\b(PRESS\s+BANCA|JALON|SENTADILLA|PESO\s+MUERTO|CURL\s+BICEPS|REMO|FONDOS|ZANCADAS)\b")),
    ("training", 2, re.compile(r"\b(RUTINA|ENTRENAMIENTO)\s+(DE\s+)?(FUERZA|HIPERTROFIA|VOLUMEN|DEFINICION)\b")),
    ("training", 1, re.compile(r"\b(CALENTAMIENTO|ESTIRAMIENTOS|CARDIO|HIIT)\b")),
    # clinical laboratory report
    ("lab_clinical", 4, re.compile(r"\b(HEMOGRAMA|BIOQUIMICA|HEMATIES|LEUCOCITOS|HEMOGLOBINA|PLAQUETAS)\b")),
    ("lab_clinical", 3, re.compile(r"\bVALORES?\s+DE\s+REFERENCIA\b|\bINTERVALO\s+DE\s+REFERENCIA\b")),
    ("lab_clinical", 3, re.compile(r"\b(COLESTEROL\s+(TOTAL|HDL|LDL)|TRIGLICERIDOS|CREATININA|TRANSAMINASAS|GLUCOSA)\b")),
    ("lab_clinical", 3, re.compile(r"\bDIRECTOR\s+TECNICO\b|\bANALISIS\s+CLINICOS\b")),
    ("lab_clinical", 2, re.compile(r"\bMG\s*/\s*DL\b|\bU\s*/\s*L\b|\bMG/DL\b")),
    # bioanalyser printout -- a different instrument entirely, never mixed with the above
    ("lab_bioanalyzer", 5, re.compile(r"\bVISCOSIDAD\s+DE\s+LA\s+SANGRE\b")),
    ("lab_bioanalyzer", 5, re.compile(r"\bCRISTAL\s+DE\s+COLESTEROL\b")),
    ("lab_bioanalyzer", 5, re.compile(r"\bELASTICIDAD\s+VASCULAR\b")),
    ("lab_bioanalyzer", 3, re.compile(r"\bRANGO\s+NORMAL\b.{0,40}\bVALOR\s+(OBTENIDO|ACTUAL)\b", re.S)),
    ("lab_bioanalyzer", 3, re.compile(r"\bBIOANALIZADOR\b|\bANALIZADOR\s+CUANTICO\b")),
    # follow-up sheet
    ("followup", 4, re.compile(r"\bHOJA\s+(DE\s+)?SEGUIMIENTO\b")),
    ("followup", 2, re.compile(r"\bSEMANA\s*\d+\b.{0,60}\b(PESO|KG)\b", re.S)),
]

_NAME_SIGNALS: list[tuple[str, int, re.Pattern]] = [
    ("diet", 2, re.compile(r"\bDIETA\b")),
    ("training", 2, re.compile(r"\bENTREN")),
    ("lab_clinical", 2, re.compile(r"\bANALITIC")),
    ("questionnaire", 2, re.compile(r"\bDATOS\b|\bCUESTIONARIO\b|\bHOJA DATOS\b")),
    ("followup", 3, re.compile(r"\bHOJA\s+SEGUIMIENTO\b|\bSEGUIMIENTO\b")),
]


# The one class where the file name beats the content. A follow-up sheet is laid out like the questionnaire -- same
# labels, PESO, CINTURA, MUNECA -- so scoring by content calls 36 of the 40 "questionnaire" and the follow-up class
# all but disappears. The professional names these files "HOJA SEGUIMIENTO" and that is the reliable signal.
_FOLLOWUP_NAME = re.compile(r"\bSEGUIMIENTO\b")


def classify(text: str, file_name: str) -> tuple[str, dict[str, int], str]:
    """Return ``(label, scores, basis)``. ``basis`` says whether content or the file name decided it."""
    if _FOLLOWUP_NAME.search(_fold(file_name)):
        return "followup", {"followup": 99}, "filename_override"
    folded = _fold(text)
    scores: collections.Counter = collections.Counter()
    for label, weight, pattern in _SIGNALS:
        hits = len(pattern.findall(folded))
        if hits:
            scores[label] += weight * min(hits, 4)
    basis = "content"
    if not scores:
        folded_name = _fold(file_name)
        for label, weight, pattern in _NAME_SIGNALS:
            if pattern.search(folded_name):
                scores[label] += weight
        basis = "filename" if scores else "none"
    if not scores:
        return "unclassified", {}, basis
    ranked = scores.most_common()
    if len(ranked) > 1 and ranked[0][1] == ranked[1][1]:
        return "ambiguous", dict(scores), basis
    return ranked[0][0], dict(scores), basis


# --------------------------------------------------------------------------------------------------- the walk

def iter_sources(root: Path):
    """Yield every file under the sources root, plus the ``.bean`` documents as single units.

    A ``.bean`` directory is one Bean word-processor document: its text lives in ``TXT.rtf`` and the sibling images
    are figures embedded in that document, not separate files. Treating the directory as the unit keeps those 369
    images from being counted as standalone scale screenshots.
    """
    bean_dirs = {p for p in root.rglob("*") if p.is_dir() and p.suffix.lower() == ".bean"}
    for path in sorted(root.rglob("*")):
        if path.is_dir():
            if path in bean_dirs:
                inner = path / "TXT.rtf"
                yield (inner if inner.exists() else path), "bean"
            continue
        if any(parent in bean_dirs for parent in path.parents):
            continue          # already accounted for by its .bean document
        yield path, "file"


def build(no_cache: bool = False, limit: int | None = None) -> dict:
    root = paths.sources_root()
    out_dir = paths.dataset_dir_v3()
    out_dir.mkdir(parents=True, exist_ok=True)
    registry = load_or_build_registry(root)

    rows: list[dict] = []
    started = time.time()
    for index, (path, unit) in enumerate(iter_sources(root)):
        if limit and index >= limit:
            break
        rel = path.relative_to(root)
        client_dir = rel.parts[0] if len(rel.parts) > 1 else None
        code = registry.code_for(client_dir) if client_dir else None
        ext = path.suffix.lower()

        if ext in AUDIO_EXT:
            rows.append({"rel": _safe_rel(rel, registry), "client_code": code, "unit": unit, "ext": ext,
                         "detected": "audio", "converter": "-", "status": "skipped_media",
                         "reason": "audio: excluded by instruction", "chars": 0, "label": "-", "sha1": ""})
            continue
        if ext in IMAGE_EXT:
            rows.append({"rel": _safe_rel(rel, registry), "client_code": code, "unit": unit, "ext": ext,
                         "detected": "image", "converter": "-", "status": "skipped_media",
                         "reason": "image: no OCR by instruction", "chars": 0, "label": "-", "sha1": ""})
            continue

        conversion = convert.convert_file(path, use_cache=not no_cache, registry=registry, code=code)
        text = convert.cached_text(conversion.sha1) if conversion.status == "ok" else ""
        label, scores, basis = classify(text, path.name) if text else ("-", {}, "none")
        reason = ""
        if conversion.status != "ok":
            reason = conversion.error or conversion.status
        elif not text.strip():
            reason = "converter produced no text"

        rows.append({
            "rel": _safe_rel(rel, registry), "client_code": code, "unit": unit, "ext": ext,
            "detected": conversion.detected, "converter": conversion.converter, "status": conversion.status,
            "reason": _safe_message(reason, registry), "chars": conversion.chars, "lines": conversion.lines,
            "label": label, "label_basis": basis, "label_scores": scores,
            "sha1": conversion.sha1, "size_bytes": conversion.size_bytes,
            # captured before the file name is masked: a bare date is not an identifier, and without it a lab
            # result cannot be placed relative to a diet
            "name_date": date_in_name(path.name),
            "name_date": date_in_name(path.name),
            "notes": [_safe_message(n, registry) for n in conversion.notes], "scrubbed": conversion.scrubbed,
            "residual_name_tokens": conversion.residual_name_tokens,
        })
        if (index + 1) % 250 == 0:
            print(f"  ...{index + 1} files ({time.time() - started:.0f}s)", file=sys.stderr, flush=True)

    manifest = out_dir / "manifest.jsonl"
    with open(manifest, "w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")

    summary = _summarise(rows)
    summary["elapsed_s"] = round(time.time() - started, 1)
    (out_dir / "inventory_log.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=1), encoding="utf-8", newline="\n")
    return summary


def _safe_rel(rel: Path, registry) -> str:
    """Relative path with the client folder replaced by its pseudonym and EVERY other component masked.

    File names and intermediate folder names both carry real names in this corpus, so the manifest -- an auditable
    artefact that lives in the data tree -- keeps a stable salted token for every component but the first.
    """
    parts = list(rel.parts)
    if len(parts) > 1:
        parts[0] = registry.code_for(parts[0]) or "UNKNOWN"
        parts[1:] = [registry.mask_file_name(part) for part in parts[1:]]
    else:
        parts = [registry.mask_file_name(parts[0])]
    return "/".join(parts)


def _safe_message(message: str, registry) -> str:
    """Strip any file-system path out of a converter's error or warning text.

    ``pdftotext`` and ``antiword`` echo the path they failed to open, which is the one place a real name can slip
    into the manifest through a field nobody thinks of as a path.
    """
    if not message:
        return message
    cleaned = re.sub(r"[A-Za-z]:[\\/][^\s'\"]+|/[^\s'\"]{6,}", "<PATH>", message)
    # Only roster tokens are masked. An earlier version ran the file-name allowlist over the whole message and
    # turned "no converter for detected format" into a row of hashes, which destroyed the diagnostic without
    # protecting anything: a converter's own error vocabulary is not personal data.
    return _WORD_RE.sub(
        lambda m: "[NOMBRE]" if identity.norm(m.group(0)) in registry._all_tokens
        and identity.norm(m.group(0)) not in identity.STOPWORDS else m.group(0),
        cleaned,
    )


def _summarise(rows: list[dict]) -> dict:
    by_ext_status: dict[str, collections.Counter] = collections.defaultdict(collections.Counter)
    by_detected = collections.Counter()
    by_label = collections.Counter()
    by_converter = collections.Counter()
    failures: list[dict] = []
    for row in rows:
        by_ext_status[row["ext"]][row["status"]] += 1
        by_detected[row["detected"]] += 1
        by_label[row["label"]] += 1
        by_converter[row["converter"]] += 1
        if row["status"] in ("failed", "unsupported", "empty_output"):
            failures.append({k: row[k] for k in ("rel", "ext", "detected", "status", "reason")})
    clients = {r["client_code"] for r in rows if r["client_code"]}
    scrub_total: collections.Counter = collections.Counter()
    residual = 0
    for row in rows:
        for k, v in (row.get("scrubbed") or {}).items():
            scrub_total[k] += v
        residual += row.get("residual_name_tokens", 0) or 0
    return {
        "pii_substitutions": dict(scrub_total.most_common()),
        "residual_name_tokens_total": residual,
        "files_total": len(rows),
        "clients": len(clients),
        "by_extension_status": {k: dict(v) for k, v in sorted(by_ext_status.items())},
        "by_detected_format": dict(by_detected.most_common()),
        "by_converter": dict(by_converter.most_common()),
        "by_label": dict(by_label.most_common()),
        "failures": failures,
        "failures_total": len(failures),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="F1: inventory and convert the raw sources")
    parser.add_argument("--no-cache", action="store_true", help="re-convert even if a cached text exists")
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()
    summary = build(no_cache=args.no_cache, limit=args.limit)
    print(json.dumps({k: v for k, v in summary.items() if k != "failures"}, ensure_ascii=False, indent=1))
    print(f"\nfailures: {summary['failures_total']} (listed in inventory_log.json)")


if __name__ == "__main__":
    main()
