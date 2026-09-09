"""ClientRecordOutputPort and BodyMeasurementOutputPort on Postgres (S3): client_records (one row per portfolio client, explicit columns)
and body_measurements. Both are scoped to the portfolio through the client_profiles join (a corpus code never has a record)."""
from __future__ import annotations

from sqlalchemy import text

from finalprosports.domain.model.client_record import BodyMeasurement, ClientRecord, Identification
from finalprosports.infrastructure.adapter.outbound.persistence.mapper.client_record_mapper import (
    RECORD_COLUMNS, measurement_from_row, measurement_to_row, record_from_row, record_to_row,
)

_PORTFOLIO = "JOIN client_profiles p ON p.professional_id = r.professional_id AND p.client_code = r.client_code AND NOT p.is_corpus_case"


class ClientRecordOutputAdapter:
    def __init__(self, session_factory):
        self._sf = session_factory

    def get(self, professional_id: str, client_code: str) -> ClientRecord | None:
        with self._sf() as s:
            row = s.execute(text(f"SELECT r.* FROM client_records r {_PORTFOLIO} WHERE r.professional_id = :p AND r.client_code = :c"),
                            {"p": professional_id, "c": client_code}).first()
            return record_from_row(row) if row else None

    def list_identifications(self, professional_id: str) -> dict[str, Identification]:
        with self._sf() as s:
            rows = s.execute(text(f"SELECT r.client_code, r.full_name, r.birth_date, r.phone, r.email FROM client_records r {_PORTFOLIO} WHERE r.professional_id = :p"),
                             {"p": professional_id}).all()
            return {r.client_code: Identification(r.full_name, r.birth_date, r.phone, r.email) for r in rows}

    def save(self, record: ClientRecord) -> ClientRecord:
        cols = ", ".join(RECORD_COLUMNS)
        marks = ", ".join(f":{c}" for c in RECORD_COLUMNS)
        updates = ", ".join(f"{c} = EXCLUDED.{c}" for c in RECORD_COLUMNS)
        with self._sf() as s:
            s.execute(text(f"INSERT INTO client_records (client_code, professional_id, {cols}, updated_at) VALUES (:client_code, :professional_id, {marks}, now()) "
                           f"ON CONFLICT (professional_id, client_code) DO UPDATE SET {updates}, updated_at = now()"), record_to_row(record))
            s.commit()
        return self.get(record.professional_id, record.client_code) or record


class BodyMeasurementOutputAdapter:
    def __init__(self, session_factory):
        self._sf = session_factory

    def list(self, professional_id: str, client_code: str) -> tuple[BodyMeasurement, ...]:
        with self._sf() as s:
            rows = s.execute(text(f"SELECT r.* FROM body_measurements r {_PORTFOLIO} WHERE r.professional_id = :p AND r.client_code = :c ORDER BY r.measured_at"),
                             {"p": professional_id, "c": client_code}).all()
            return tuple(measurement_from_row(r) for r in rows)

    def all_by_client(self, professional_id: str) -> dict[str, tuple[BodyMeasurement, ...]]:
        """Toda la serie del profesional, INCLUIDA la base de casos, en una sentencia.

        `list` filtra por cartera a propósito (S3: un código del corpus no tiene expediente). Desde la 0015 el corpus SÍ
        tiene báscula, y el arnés necesita la serie de los 171 clientes con lecturas para aplicarles la regla temporal
        una por una. Se separa en vez de relajar `list` para no ampliar en silencio lo que ve la ruta de la cartera.
        """
        by: dict[str, list[BodyMeasurement]] = {}
        with self._sf() as s:
            rows = s.execute(text("SELECT r.* FROM body_measurements r WHERE r.professional_id = :p ORDER BY r.client_code, r.measured_at"),
                             {"p": professional_id}).all()
        for r in rows:
            by.setdefault(r.client_code, []).append(measurement_from_row(r))
        return {c: tuple(v) for c, v in by.items()}

    def add(self, professional_id: str, client_code: str, measurements: tuple[BodyMeasurement, ...]) -> int:
        cols = ("measured_at", "weight_kg", "height_cm", "body_fat_pct", "muscle_pct", "water_pct", "bone_kg", "source",
                "muscle_mass_kg", "physique_rating", "visceral_fat_rating", "metabolic_age", "basal_met_kcal")
        names = ", ".join(("professional_id", "client_code") + cols)
        marks = ", ".join(f":{c}" for c in ("professional_id", "client_code") + cols)
        with self._sf() as s:
            n = 0
            for m in measurements:
                r = s.execute(text(f"INSERT INTO body_measurements ({names}) VALUES ({marks}) "
                                   "ON CONFLICT (professional_id, client_code, measured_at, source) DO NOTHING"),
                              measurement_to_row(professional_id, client_code, m))
                n += r.rowcount or 0
            s.commit()
            return n
