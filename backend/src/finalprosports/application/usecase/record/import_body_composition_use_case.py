"""ImportBodyCompositionUseCase (S3): import the connected scale's export or a manual reading.

The scale dump has the SAME structure as the professional's `db_*/users` + `history` files (other values): `users` rows carry
name, isMale, birthdate (epoch ms), height_cm, activity_level, isLifetimeAthlete (verified against the original profile parser of the ETL,
perfiles.py); `history` rows carry the ELEVEN magnitudes the scale measures (date in epoch ms, weight, percentFat, percentHydration,
boneMass, muscleMass, physiqueRating, visceralFatRating, metabolicAge, basalMet, height), accepted under the key names of
the `.bin` itself, of `body_measurements.jsonl` and of the short aliases. Names and e-mails in the dump are IGNORED: identification is typed by the professional in the record.
The profile receives sex, birth date -> age, height, activity level and athlete flag; the measurements go to the record. """
from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime, timezone

from finalprosports.application.exception.client.client_not_found_error import ClientNotFoundError
from finalprosports.application.port.outbound.persistence.client.client_repository_output_port import ClientRepositoryOutputPort
from finalprosports.application.port.outbound.persistence.record.body_measurement_output_port import BodyMeasurementOutputPort
from finalprosports.domain.model import ClientProfile
from finalprosports.domain.model.client_record import BodyMeasurement

# Los nombres que trae cada magnitud, en los TRES dialectos en los que llega, y en este orden de preferencia:
#   1. el nuestro (`weight_kg`), 2. el del `.bin` de la báscula, que es camelCase (`percentFat`, `boneMass`,
#   `visceralFatRating`…), 3. el de `body_measurements.jsonl`, que es el `.bin` ya renombrado por el extractor
#   (`fat_pct`, `hydration_pct`, `bone_mass_kg`…), y por último los sinónimos cortos y en español que se aceptaban.
# El dialecto 2 es el contrato REAL de la exportación y es el que faltaba: verificado contra `pipeline_v3/scale.py`,
# que es quien abre el `.bin` (un ZIP con `users`, `history` y `goals`) y construye la serie del corpus.
_WEIGHT = ("weight_kg", "weight", "peso")
_FAT = ("body_fat_pct", "percentFat", "fat_pct", "fat", "bodyFat", "grasa")
_MUSCLE_PCT = ("muscle_pct", "musclePercent", "percentMuscle", "muscle", "musculo")
_MUSCLE_KG = ("muscle_mass_kg", "muscleMass", "musculo_kg")
_WATER = ("water_pct", "percentHydration", "hydration_pct", "water", "agua")
_BONE = ("bone_kg", "boneMass", "bone_mass_kg", "bone", "hueso")
_PHYSIQUE = ("physique_rating", "physiqueRating")
_VISCERAL = ("visceral_fat_rating", "visceralFatRating")
_METABOLIC_AGE = ("metabolic_age", "metabolicAge")
_BASAL = ("basal_met_kcal", "basalMet")
_HEIGHT = ("height_cm", "height", "altura")
_TIME = ("timestamp", "date", "measured_at", "dateTime", "fecha")


def _num(row: dict, keys: tuple[str, ...]) -> float | None:
    for k in keys:
        if row.get(k) is not None:
            try:
                return float(row[k])
            except (TypeError, ValueError):
                continue
    return None


def _when(row: dict) -> datetime:
    for k in _TIME:
        v = row.get(k)
        if v is None:
            continue
        if isinstance(v, (int, float)):
            return datetime.fromtimestamp(v / (1000 if v > 1e11 else 1), timezone.utc)
        try:
            dt = datetime.fromisoformat(str(v).replace("Z", "+00:00"))
            return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return datetime.now(timezone.utc)


def _int(row: dict, keys: tuple[str, ...]) -> int | None:
    """Entero a partir del valor numérico. `basalMet` llega como CADENA en la exportación («2725»), de ahí el rodeo."""
    v = _num(row, keys)
    return int(round(v)) if v is not None else None


def measurements_from_history(history: list[dict]) -> tuple[BodyMeasurement, ...]:
    """Las ONCE magnitudes de la exportación, no las cinco que caben en la hoja de S3.

    Antes se leían peso, grasa, músculo (%), agua y hueso, y con los nombres del dialecto corto. Sobre un `.bin` real
    eso guardaba el peso y la fecha y tiraba TODO lo demás en silencio, porque la exportación no escribe `fat` sino
    `percentFat`, ni `water` sino `percentHydration`. El músculo se guarda en KILOS, que es lo que la báscula mide;
    `muscle_pct` se queda para la entrada a mano y no se convierte, que era la razón por la que la 0015 abrió columna
    aparte."""
    out = []
    for row in history or ():
        out.append(BodyMeasurement(
            _when(row), _num(row, _WEIGHT), _int(row, _HEIGHT), _num(row, _FAT), _num(row, _MUSCLE_PCT),
            _num(row, _WATER), _num(row, _BONE), "scale",
            muscle_mass_kg=_num(row, _MUSCLE_KG), physique_rating=_int(row, _PHYSIQUE),
            visceral_fat_rating=_num(row, _VISCERAL), metabolic_age=_int(row, _METABOLIC_AGE),
            basal_met_kcal=_int(row, _BASAL)))
    return tuple(sorted(out, key=lambda m: m.measured_at))


def profile_from_user(profile: ClientProfile, user: dict, today: date) -> tuple[ClientProfile, date | None]:
    birth: date | None = None
    if user.get("birthdate") is not None:
        try:
            v = float(user["birthdate"])
            birth = datetime.fromtimestamp(v / (1000 if v > 1e11 else 1), timezone.utc).date()
        except (TypeError, ValueError, OSError):
            birth = None
    age = (today.year - birth.year - ((today.month, today.day) < (birth.month, birth.day))) if birth else profile.age
    sex = ("M" if user["isMale"] else "F") if user.get("isMale") is not None else profile.sex
    return replace(profile, sex=sex, age=age, height_cm=int(user["height_cm"]) if user.get("height_cm") else profile.height_cm,
                   activity_level=int(user["activity_level"]) if user.get("activity_level") is not None else profile.activity_level,
                   is_athlete=bool(user["isLifetimeAthlete"]) if user.get("isLifetimeAthlete") is not None else profile.is_athlete), birth


class ImportBodyCompositionUseCase:
    def __init__(self, clients: ClientRepositoryOutputPort, measurements: BodyMeasurementOutputPort):
        self._clients, self._measurements = clients, measurements

    def import_scale(self, professional_id: str, client_code: str, users: list[dict], history: list[dict], today: date | None = None) -> dict:
        profile = self._clients.get(professional_id, client_code)
        if profile is None:
            raise ClientNotFoundError(client_code)
        birth = None
        if users:
            profile, birth = profile_from_user(profile, users[0], today or date.today())     # one client per import: the first user row
            self._clients.save(profile)
        ms = measurements_from_history(history)
        added = self._measurements.add(professional_id, client_code, ms) if ms else 0
        return {"profile": profile, "birth_date": birth, "measurements_added": added, "users_seen": len(users or ())}

    def add_manual(self, professional_id: str, client_code: str, measurement: BodyMeasurement) -> dict:
        profile = self._clients.get(professional_id, client_code)
        if profile is None:
            raise ClientNotFoundError(client_code)
        if measurement.height_cm and measurement.height_cm != profile.height_cm:
            profile = replace(profile, height_cm=measurement.height_cm)
            self._clients.save(profile)
        added = self._measurements.add(professional_id, client_code, (replace(measurement, source="manual"),))
        return {"profile": profile, "measurements_added": added}
