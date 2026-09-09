"""GetClientRecordService (S3): the record, the measurements, the body-composition estimate and the two completeness indicators
(record vs algorithm input) of a portfolio client, in one read."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from finalprosports.application.exception.client.client_not_found_error import ClientNotFoundError
from finalprosports.application.port.outbound.persistence.client.client_repository_output_port import ClientRepositoryOutputPort
from finalprosports.application.port.outbound.persistence.record.body_measurement_output_port import BodyMeasurementOutputPort
from finalprosports.application.port.outbound.persistence.record.client_record_output_port import ClientRecordOutputPort
from finalprosports.domain.composition.policy.body_composition_policy import BodyCompositionEstimate, estimate
from finalprosports.domain.composition.policy.profile_completeness_policy import Completeness, completeness
from finalprosports.domain.model import ClientProfile
from finalprosports.domain.model.client_record import BodyMeasurement, ClientRecord


@dataclass(frozen=True)
class ClientRecordView:
    profile: ClientProfile
    record: ClientRecord
    measurements: tuple[BodyMeasurement, ...]
    body_composition: BodyCompositionEstimate
    completeness: Completeness

    @property
    def latest_weight_kg(self) -> float | None:
        for m in sorted(self.measurements, key=lambda x: x.measured_at, reverse=True):
            if m.weight_kg is not None:
                return m.weight_kg
        return self.record.physiology.initial_weight_kg


class GetClientRecordService:
    def __init__(self, clients: ClientRepositoryOutputPort, records: ClientRecordOutputPort, measurements: BodyMeasurementOutputPort):
        self._clients, self._records, self._measurements = clients, records, measurements

    def get(self, professional_id: str, client_code: str, today: date | None = None) -> ClientRecordView:
        profile = self._clients.get(professional_id, client_code)
        if profile is None:
            raise ClientNotFoundError(client_code)
        record = self._records.get(professional_id, client_code) or ClientRecord(client_code, professional_id)
        measurements = self._measurements.list(professional_id, client_code)
        latest = next((m for m in sorted(measurements, key=lambda x: x.measured_at, reverse=True) if m.weight_kg is not None), None)
        weight = latest.weight_kg if latest else record.physiology.initial_weight_kg
        p = record.physiology
        est = estimate(profile.sex, profile.height_cm or p.height_cm, weight, p.waist_cm, p.neck_cm, p.wrist_cm, p.hip_cm)
        return ClientRecordView(profile, record, measurements, est, completeness(profile, record))
