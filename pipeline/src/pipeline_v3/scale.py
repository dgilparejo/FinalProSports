"""F3 -- the scale export: a body-composition time series per client.

The source is a single ZIP holding three JSON documents (``users``, ``history``, ``goals``). ``history`` rows carry a
``uuid`` that joins to ``users``; ``users`` carries the person's name, which is how a series is matched to a client
folder -- and the only reason this module ever touches a name. The name is used to *match* and is then dropped: what
reaches the dataset is ``client_code`` plus measurements.

The professional's own readings are excluded (the prompt puts them at 997 of 3.250, and they are his own body, not a
client's). The exclusion is by uuid, resolved once from the name digests, so no literal is compared.

Matching a scale user to a source folder is fuzzy by nature: the same person is written with two given names and two
surnames in one place and with an abbreviated given name and one surname in the other. The matcher is deliberately
conservative -- exact normalised match on the token set, then a subset match requiring at least two shared tokens and
an unambiguous winner -- and everything it cannot resolve is reported as ``unmatched`` with a masked shape, never
guessed.
"""
from __future__ import annotations

import argparse
import collections
import json
import sys
import zipfile
from datetime import date, datetime, timezone
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from pipeline_v3 import identity, paths
else:
    from . import identity, paths

MEASURES = ("weight", "percentFat", "percentHydration", "boneMass", "muscleMass",
            "physiqueRating", "visceralFatRating", "metabolicAge", "basalMet", "activityLevel")

FIELD_RENAME = {
    "weight": "weight_kg", "percentFat": "fat_pct", "percentHydration": "hydration_pct",
    "boneMass": "bone_mass_kg", "muscleMass": "muscle_mass_kg", "physiqueRating": "physique_rating",
    "visceralFatRating": "visceral_fat_rating", "metabolicAge": "metabolic_age",
    "basalMet": "basal_met_kcal", "activityLevel": "activity_level", "height": "height_cm",
    "age": "age", "isMale": "is_male",
}


def scale_file(root: Path) -> Path | None:
    candidates = sorted(p for p in root.iterdir() if p.is_file() and p.suffix.lower() == ".bin")
    return candidates[0] if candidates else None


def _load(path: Path) -> tuple[list[dict], list[dict]]:
    with zipfile.ZipFile(path) as zf:
        users = json.loads(zf.read("users").decode("utf-8"))
        history = json.loads(zf.read("history").decode("utf-8"))
    return users, history


def _parse_date(value) -> str | None:
    """The export stores epoch milliseconds. Returns an ISO date, or None when the value is unusable."""
    if value in (None, "", 0):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        text = str(value)[:10]
        try:
            datetime.strptime(text, "%Y-%m-%d")
            return text
        except ValueError:
            return None
    if number > 1e11:            # milliseconds
        number /= 1000.0
    if not (0 < number < 4e9):
        return None
    return datetime.fromtimestamp(number, tz=timezone.utc).date().isoformat()


def _derive_age(birthdate, reference: str | None) -> float | None:
    """Age in whole years at ``reference``. The birthdate itself is never returned and never stored."""
    born = _parse_date(birthdate)
    if not born:
        return None
    try:
        ref = date.fromisoformat(reference) if reference else date.today()
        b = date.fromisoformat(born)
    except (TypeError, ValueError):
        return None
    years = ref.year - b.year - ((ref.month, ref.day) < (b.month, b.day))
    return float(years) if 10 <= years <= 99 else None


def _tokens(name: str) -> list[str]:
    return [identity.norm(t) for t in identity._WORD.findall(name or "") if len(identity.norm(t)) >= 3]


def match_users_to_clients(users: list[dict], registry) -> tuple[dict[str, str], list[dict]]:
    """Return ``(uuid -> client_code, unmatched)``. Names are consumed here and never returned."""
    by_norm: dict[str, str] = {}
    by_tokens: list[tuple[frozenset[str], str]] = []
    for folder, code in registry.codes.items():
        toks = frozenset(_tokens(folder))
        by_norm[" ".join(sorted(toks))] = code
        by_tokens.append((toks, code))

    mapping: dict[str, str] = {}
    unmatched: list[dict] = []
    used: dict[str, str] = {}
    for user in users:
        uuid = user.get("uuid")
        toks = frozenset(_tokens(user.get("name", "")))
        if not uuid or not toks:
            unmatched.append({"uuid_digest": registry.digest(str(uuid))[:12], "reason": "no name in the export",
                              "token_count": len(toks)})
            continue
        key = " ".join(sorted(toks))
        code = by_norm.get(key)
        if code is None:
            # token-subset match: at least two shared tokens, and the candidate must not be ambiguous
            scored = [(len(toks & folder_toks), c) for folder_toks, c in by_tokens if len(toks & folder_toks) >= 2]
            scored.sort(reverse=True)
            if scored and (len(scored) == 1 or scored[0][0] > scored[1][0]):
                code = scored[0][1]
        if code is None:
            unmatched.append({"uuid_digest": registry.digest(str(uuid))[:12],
                              "name_shape": "-".join(identity.mask(t) for t in sorted(toks)),
                              "reason": "no source folder with two or more shared name tokens"})
            continue
        if code in used.values():
            unmatched.append({"uuid_digest": registry.digest(str(uuid))[:12], "reason": f"{code} already matched"})
            continue
        mapping[uuid] = code
        used[uuid] = code
    return mapping, unmatched


def professional_uuids(users: list[dict], history: list[dict], registry) -> set[str]:
    """The professional's own uuids, identified by name digest -- never by a literal comparison.

    A digest hit is NOT enough on its own. Five scale accounts carry his surname and three of them are *clients* who
    happen to share it: they have their own source folder and 11 readings between them. Dropping those would delete
    real clients' body composition to remove the trainer's. So an account is his only when the digest matches **and**
    no client folder answers to that name; that leaves exactly the 997 readings the data owner counted.
    """
    salt, digests = identity._professional()
    if not digests:
        return set()
    import hashlib
    folders = {" ".join(sorted(_tokens(folder))) for folder in registry.codes}
    out = set()
    for user in users:
        tokens = _tokens(user.get("name", ""))
        if not any(hashlib.sha256((salt + t).encode("utf-8")).hexdigest() in digests for t in tokens):
            continue
        if " ".join(sorted(tokens)) in folders:
            continue                    # a client who shares the surname, not the professional
        out.add(user.get("uuid"))
    return {u for u in out if u}


def build(out_dir: Path | None = None) -> dict:
    root = paths.sources_root()
    out_dir = out_dir or paths.dataset_dir_v3()
    out_dir.mkdir(parents=True, exist_ok=True)
    registry = identity.load_or_build_registry(root)

    path = scale_file(root)
    if path is None:
        raise FileNotFoundError("no scale export (.bin) at the sources root")
    users, history = _load(path)

    excluded_uuids = professional_uuids(users, history, registry)
    mapping, unmatched = match_users_to_clients(
        [u for u in users if u.get("uuid") not in excluded_uuids], registry)

    rows: list[dict] = []
    dropped = collections.Counter()
    for record in history:
        uuid = record.get("uuid")
        if uuid in excluded_uuids:
            dropped["professional"] += 1
            continue
        code = mapping.get(uuid)
        if code is None:
            dropped["unmatched_user"] += 1
            continue
        date = _parse_date(record.get("date"))
        if date is None:
            dropped["unusable_date"] += 1
            continue
        row = {"client_code": code, "date": date, "source": "bascula"}
        for key in ("height", "age", "isMale", *MEASURES):
            value = record.get(key)
            if value in (None, "", 0) and key not in ("isMale",):
                continue
            row[FIELD_RENAME.get(key, key)] = value
        rows.append(row)

    rows.sort(key=lambda r: (r["client_code"], r["date"]))
    measurements = out_dir / "body_measurements.jsonl"
    with open(measurements, "w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")

    per_client = collections.Counter(r["client_code"] for r in rows)
    spans: dict[str, int] = {}
    for code in per_client:
        dates = sorted(r["date"] for r in rows if r["client_code"] == code)
        spans[code] = (datetime.fromisoformat(dates[-1]) - datetime.fromisoformat(dates[0])).days
    trajectory = {c for c, n in per_client.items() if n >= 2 and spans[c] >= 21}

    # Demographics the scale knows and the questionnaire usually does not. The questionnaire has no SEXO label at
    # all and gives an explicit age in under 1 % of documents, while every scale account states sex, height and
    # activity level and carries a birthdate. Age is DERIVED here and the birthdate is dropped on the spot: a full
    # date of birth is a direct identifier, the age is not.
    demographics: dict[str, dict] = {}
    users_by_uuid = {u.get("uuid"): u for u in users}
    for uuid, code in mapping.items():
        user = users_by_uuid.get(uuid, {})
        latest = max((r for r in rows if r["client_code"] == code), key=lambda r: r["date"], default=None)
        entry: dict = {}
        if user.get("isMale") is not None:
            entry["sex"] = "M" if user.get("isMale") else "F"
        height = user.get("height_cm") or (latest or {}).get("height_cm")
        if height and 120 <= float(height) <= 220:
            entry["height_cm"] = float(height)
        if user.get("activity_level") not in (None, ""):
            entry["activity_level"] = user.get("activity_level")
        if user.get("isLifetimeAthlete") is not None:
            entry["is_athlete"] = bool(user.get("isLifetimeAthlete"))
        age = _derive_age(user.get("birthdate"), (latest or {}).get("date"))
        if age is None and latest is not None:
            age = latest.get("age")
        if age and 10 <= float(age) <= 99:
            entry["age"] = float(age)
        if entry:
            demographics[code] = entry
    (out_dir / "scale_demographics.json").write_text(
        json.dumps(demographics, ensure_ascii=False, indent=1), encoding="utf-8", newline="\n")

    coverage = {field: sum(1 for r in rows if field in r) for field in
                ("weight_kg", "fat_pct", "muscle_mass_kg", "hydration_pct", "visceral_fat_rating",
                 "metabolic_age", "basal_met_kcal", "bone_mass_kg")}
    summary = {
        "source_file": path.name,
        "users_in_export": len(users),
        "professional_users_excluded": len(excluded_uuids),
        "history_rows_total": len(history),
        "history_rows_kept": len(rows),
        "history_rows_dropped": dict(dropped),
        "users_matched_to_a_client": len(mapping),
        "users_unmatched": len(unmatched),
        "clients_with_any_reading": len(per_client),
        "clients_with_trajectory_2plus_21days": len(trajectory),
        "readings_per_client_median": sorted(per_client.values())[len(per_client) // 2] if per_client else 0,
        "clients_with_scale_demographics": len(demographics),
        "field_coverage_pct": {k: round(100 * v / len(rows), 1) if rows else 0.0 for k, v in coverage.items()},
        "unmatched_detail": unmatched,
    }
    (out_dir / "scale_log.json").write_text(json.dumps(summary, ensure_ascii=False, indent=1),
                                            encoding="utf-8", newline="\n")
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="F3: body-composition series from the scale export")
    parser.parse_args()
    summary = build()
    printable = {k: v for k, v in summary.items() if k != "unmatched_detail"}
    print(json.dumps(printable, ensure_ascii=False, indent=1))
    print(f"\nunmatched scale users: {summary['users_unmatched']} (detail in scale_log.json)")


if __name__ == "__main__":
    main()
