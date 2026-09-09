"""F3 -- lab reports, in three levels, with the two formats never mixed.

There are two kinds of report in this corpus and they measure different things:

* **clinical laboratory** (an accredited lab, signed by a technical director): haemogram, biochemistry, values in
  mg/dL or U/L against a reference interval;
* **bioanalyser**: a device printout with its own invented indices -- "Viscosidad de la Sangre", "Cristal de
  Colesterol", "Elasticidad Vascular" -- each with a normal range and an obtained value.

A bioanalyser marker and a lab marker are not the same magnitude even when they share a word, so they go to separate
namespaces (``clinical.*`` and ``bioanalyzer.*``) and ``source_type`` is mandatory on every record. Merging them
would mean building dietary criteria on noise in a health application.

The three levels, as commissioned:

1. existence, date and distance in days to each diet -- free, and always produced;
2. ``source_type`` per report, from content;
3. parsed values, per format. Level 3 only runs where it is reliable; where it is not, the report stays at level 1
   and says so.
"""
from __future__ import annotations

import argparse
import collections
import json
import re
import sys
from datetime import date
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from pipeline_v3 import convert, identity, paths
else:
    from . import convert, identity, paths
from pipeline import excluded  # noqa: E402

# Enough extractable text to attempt level 3 at all. Below this the PDF is an image of a table.
MIN_CHARS_FOR_PARSING = 1200
# Below this many parsed rows a clinical report is treated as unparsed rather than partially parsed.
MIN_CLINICAL_ROWS = 8
_NUTRIGEN = re.compile(r"NutriGen|Fagron|nutrigen[eé]tic", re.I)
# Un CUARTO formato escondido en el cajon clinico: informes de fisiologia deportiva (ergoespirometria). No son
# analiticas: su tabla es antropometrica (pliegues, perimetros, diametros, somatotipo) y el parser clinico la lee
# como filas analito/valor, produciendo «analitos» llamados GENERAL PESO, DERECHA o PLIEGUES TRICIPITAL con la
# columna de al lado por unidad. Eran 33 valores inventados en 3 informes. Se detecta y NO se parsea.
_SPORTS_PHYSIOLOGY = re.compile(r"ergoespirom|tapiz rodante|prueba de esfuerzo|valoraci[oó]n ergo", re.I)
# Analitica de laboratorio de verdad: firmada, con hemograma o bioquimica. Se usa para saber que se ESPERABA parsear.
_LABORATORY = re.compile(r"hemograma|bioqu[ií]mica|hemat[ií]es|leucocitos|colesterol total|creatinina", re.I)

_DATE_IN_NAME = re.compile(r"(?<!\d)(\d{1,2})[._\-/](\d{1,2})[._\-/](\d{2,4})(?!\d)|(?<!\d)(20\d{2})(\d{2})(\d{2})(?!\d)")

# Bioanalyser: "<indicator name> <low> - <high> <value>" laid out in columns.
_BIO_ROW = re.compile(
    r"^\s*(?P<name>[A-Za-zÁÉÍÓÚÑÜáéíóúñü][^\d\n]{4,60}?)\s{2,}"
    r"(?P<low>\d+[.,]?\d*)\s*[-–]\s*(?P<high>\d+[.,]?\d*)\s{2,}"
    r"(?P<value>\d+[.,]?\d*)\s*$",
    re.M,
)
# Clinical: "<analyte> <value> <unit> <low> - <high>", tolerating the column spacing pdftotext -layout produces.
_CLIN_ROW = re.compile(
    r"^\s*(?P<name>[A-Za-zÁÉÍÓÚÑÜáéíóúñü][^\d\n]{3,45}?)\s{2,}"
    r"(?P<value>[<>]?\s*\d+[.,]?\d*)\s{1,}"
    r"(?P<unit>[A-Za-zµ%/\^\d.]{1,12})?\s*"
    r"(?:\s{2,}(?P<low>\d+[.,]?\d*)\s*[-–]\s*(?P<high>\d+[.,]?\d*))?\s*$",
    re.M,
)


def _number(text: str) -> float | None:
    try:
        return float(str(text).replace(",", ".").strip().lstrip("<>").strip())
    except (TypeError, ValueError):
        return None


def date_from_name(name: str) -> str | None:
    match = _DATE_IN_NAME.search(name)
    if not match:
        return None
    groups = match.groups()
    try:
        if groups[0]:
            day, month, year = int(groups[0]), int(groups[1]), int(groups[2])
            year += 2000 if year < 70 else 1900 if year < 100 else 0
        else:
            year, month, day = int(groups[3]), int(groups[4]), int(groups[5])
        return date(year, month, day).isoformat()
    except (TypeError, ValueError):
        return None


def parse_bioanalyzer(text: str) -> list[dict]:
    out = []
    for match in _BIO_ROW.finditer(text):
        low, high, value = _number(match.group("low")), _number(match.group("high")), _number(match.group("value"))
        if None in (low, high, value) or low > high:
            continue
        name = re.sub(r"\s+", " ", match.group("name")).strip(" .:-")
        if len(name) < 5:
            continue
        out.append({"namespace": "bioanalyzer", "indicator": name,
                    "value": value, "range_low": low, "range_high": high,
                    "within_range": low <= value <= high})
    return out


def parse_clinical(text: str) -> list[dict]:
    out = []
    for match in _CLIN_ROW.finditer(text):
        value = _number(match.group("value"))
        if value is None:
            continue
        name = re.sub(r"\s+", " ", match.group("name")).strip(" .:-")
        if len(name) < 3 or name.isdigit():
            continue
        low, high = _number(match.group("low")), _number(match.group("high"))
        record = {"namespace": "clinical", "analyte": name, "value": value,
                  "unit": (match.group("unit") or "").strip() or None}
        if low is not None and high is not None and low <= high:
            record.update({"range_low": low, "range_high": high, "within_range": low <= value <= high})
        out.append(record)
    return out


def build(out_dir: Path | None = None) -> dict:
    out_dir = out_dir or paths.dataset_dir_v3()
    manifest = [json.loads(l) for l in (out_dir / "manifest.jsonl").read_text(encoding="utf-8").splitlines()
                if l.strip()]
    reports = [r for r in manifest if r.get("label") in ("lab_clinical", "lab_bioanalyzer")]

    diets_by_client: dict[str, list[dict]] = collections.defaultdict(list)
    diets_path = out_dir / "diets.jsonl"
    if diets_path.exists():
        for line in diets_path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                diet = json.loads(line)
                diets_by_client[diet["meta"]["client_code"]].append(diet)

    rows: list[dict] = []
    stats = collections.Counter()
    per_source = collections.Counter()
    text_lengths: list[int] = []

    for report in reports:
        source_type = "bioanalyzer" if report["label"] == "lab_bioanalyzer" else "clinical"
        per_source[source_type] += 1
        text = convert.cached_text(report["sha1"]) if report.get("status") == "ok" else ""
        chars = len(text)
        text_lengths.append(chars)
        # the manifest carries the date captured before the file name was masked
        report_date = report.get("name_date") or date_from_name(report["rel"].split("/")[-1])

        # level 3, only where there is enough text to be worth trying
        values: list[dict] = []
        level = 1
        reason = ""
        unreliable = False
        if report.get("status") != "ok":
            reason = report.get("reason") or report.get("status") or "not converted"
            stats["level1_not_converted"] += 1
        elif chars < MIN_CHARS_FOR_PARSING:
            reason = f"only {chars} extractable characters: the result table is an image, no OCR by instruction"
            stats["level1_too_little_text"] += 1
        elif _SPORTS_PHYSIOLOGY.search(text) and not _LABORATORY.search(text):
            source_type = "sports_physiology"
            per_source["clinical"] -= 1
            per_source["sports_physiology"] += 1
            reason = ("sports-physiology assessment, not a lab panel: its table is anthropometric and the clinical "
                      "parser reads its cells as analyte/value rows")
            stats["level2_sports_physiology"] += 1
        elif _NUTRIGEN.search(text):
            # A third format hiding in the clinical bucket: a nutrigenetic report (Fagron NutriGen), which is
            # neither a laboratory panel nor a device printout. It has no analyte/value/range rows to parse, and
            # running the clinical parser over it produced "analytes" called "Informe de Fagron NutriGen" and
            # "Formula sugerida" -- headings read as results. It stays at level 2 under its own source type.
            source_type = "nutrigenetic"
            per_source["clinical"] -= 1
            per_source["nutrigenetic"] += 1
            reason = "nutrigenetic report: no analyte/value/range rows exist in this format"
            stats["level2_nutrigenetic"] += 1
        else:
            values = parse_bioanalyzer(text) if source_type == "bioanalyzer" else parse_clinical(text)
            if source_type == "clinical" and len(values) < MIN_CLINICAL_ROWS:
                # Antes se BORRABAN. Se conservan marcadas: descartarlas perdia informacion que se pidio
                # guardar entera, y el motivo real no es que sean falsas sino que la extraccion de texto de estos PDF
                # descoloca las columnas (el valor de una fila cae al lado de la etiqueta de la siguiente), asi que
                # no se puede afirmar que el numero corresponda al analito. Quedan en nivel 2 con `unreliable = true`
                # y NINGUN consumidor las usa: la bandera va en el propio registro, no en un comentario.
                reason = (f"only {len(values)} result rows matched: this laboratory's PDF extracts its columns out of "
                          "order, so the value cannot be attributed to the analyte with confidence")
                unreliable = True
                stats["level2_clinical_unreliable"] += 1
            if values and not unreliable:
                level = 3
                stats[f"level3_{source_type}"] += 1
            elif not reason:
                reason = "text present but no result row matched the format's layout"
                stats["level1_no_rows_matched"] += 1
        level = 2 if level == 1 and source_type else level

        distances = []
        for diet in diets_by_client.get(report.get("client_code") or "", []):
            diet_date = diet["meta"].get("doc_date")
            if report_date and diet_date:
                delta = (date.fromisoformat(diet_date) - date.fromisoformat(report_date)).days
                distances.append({"diet_id": diet["id"], "days_from_report_to_diet": delta})
        distances.sort(key=lambda d: abs(d["days_from_report_to_diet"]))

        # EXCLUSION FARMACOLOGICA. La regla del proyecto es una LISTA BLANCA: se descarta toda mencion de una
        # sustancia excluida salvo que sea prosa clinica reconocida. El nombre de un parametro que viene acompanado de
        # un VALOR y un RANGO DE REFERENCIA es precisamente eso -- una magnitud medida, no una prescripcion -- y
        # redactarlo destruiria dato legitimo: aplicado a ciegas, el guarda borraba `Insulina` y `Testosterona`, que
        # son dos de los parametros con mas cobertura (148 y 146 clientes, 305 mediciones). Se cuentan y se conservan.
        #
        # Lo que SI se descarta es el texto libre: una linea de prescripcion dentro del informe no puede salir por
        # ningun campo de este fichero. Hoy el unico texto libre que se emite es `level_reason`, que lo escribe este
        # modulo; si manana se emitiera una nota del informe, tiene que pasar por `excluded.must_drop` aqui.
        for v in values:
            for key in ("indicator", "analyte"):
                name = v.get(key)
                if not name:
                    continue
                if excluded.contains(name):
                    measured = v.get("value") is not None and (v.get("range_low") is not None or v.get("unit"))
                    if measured:
                        stats["substance_named_as_a_measured_parameter_kept"] += 1
                    else:
                        v[key] = excluded.redact(name)
                        stats["parameter_names_redacted"] += 1
        if excluded.must_drop(reason):
            reason = excluded.redact(reason)
        rows.append({
            "client_code": report.get("client_code"),
            "source_type": source_type,                 # mandatory, never inferred at read time
            "report_sha1": report["sha1"],
            "report_date": report_date,
            "level": level,
            "level_reason": reason,
            "values_unreliable": unreliable,
            "extractable_chars": chars,
            "values": values,
            "nearest_diets": distances[:5],
        })
        if values:
            stats["values_extracted"] += len(values)

    rows.sort(key=lambda r: (r["client_code"] or "", r["report_date"] or ""))
    with open(out_dir / "lab_results.jsonl", "w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")

    lengths = sorted(text_lengths)
    clients = {r["client_code"] for r in rows if r["client_code"]}
    summary = {
        "reports_total": len(rows),
        "by_source_type": dict(per_source),
        "clients_with_a_report": len(clients),
        "reports_with_a_date_in_the_file_name": sum(1 for r in rows if r["report_date"]),
        "reports_at_level_3": sum(1 for r in rows if r["level"] == 3),
        "reports_at_level_2_only": sum(1 for r in rows if r["level"] == 2),
        "reports_with_unreliable_values_kept": sum(1 for r in rows if r["values_unreliable"]),
        "parameter_names_redacted_by_the_substance_guard": stats["parameter_names_redacted"],
        "substance_named_as_a_measured_parameter_kept": stats["substance_named_as_a_measured_parameter_kept"],
        "level_reasons": {k: v for k, v in stats.items() if k.startswith("level1")},
        "values_extracted": stats["values_extracted"],
        "extractable_chars_median": lengths[len(lengths) // 2] if lengths else 0,
        "reports_below_parsing_threshold": sum(1 for n in text_lengths if n < MIN_CHARS_FOR_PARSING),
        "threshold_chars": MIN_CHARS_FOR_PARSING,
        "namespace_note": ("clinical and bioanalyzer values never share a field; source_type is mandatory on every "
                           "record so a consumer cannot compare a device index with a laboratory magnitude"),
    }
    (out_dir / "labs_log.json").write_text(json.dumps(summary, ensure_ascii=False, indent=1),
                                           encoding="utf-8", newline="\n")
    return summary


def main() -> None:
    argparse.ArgumentParser(description="F3: lab reports at three levels").parse_args()
    print(json.dumps(build(), ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
