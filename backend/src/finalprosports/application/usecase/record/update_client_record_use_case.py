"""UpdateClientRecordUseCase (S3): saves the intake questionnaire and SYNCHRONISES the algorithm inputs into the ClientProfile:
age from the birth date, height, sport, and the free-text preferences resolved against the catalogue (disliked foods -> soft
exclusions applied by the validator; supplements already owned -> shown with the proposal). Everything else stays record."""
from __future__ import annotations

from dataclasses import replace
from datetime import date

from finalprosports.application.exception.client.client_not_found_error import ClientNotFoundError
from finalprosports.application.port.outbound.persistence.client.client_repository_output_port import ClientRepositoryOutputPort
from finalprosports.application.port.outbound.persistence.record.client_record_output_port import ClientRecordOutputPort
from finalprosports.application.service.catalog.food_matcher import FoodMatcher, MatchResult
from finalprosports.domain.model import ClientProfile
from finalprosports.domain.model.client_record import ClientRecord


class UpdateClientRecordUseCase:
    def __init__(self, clients: ClientRepositoryOutputPort, records: ClientRecordOutputPort, matcher: FoodMatcher):
        self._clients, self._records, self._matcher = clients, records, matcher

    def update(self, professional_id: str, record: ClientRecord, today: date | None = None) -> tuple[ClientRecord, ClientProfile, dict[str, MatchResult]]:
        profile = self._clients.get(professional_id, record.client_code)
        if profile is None:
            raise ClientNotFoundError(record.client_code)
        saved = self._records.save(replace(record, professional_id=professional_id))
        disliked = self._matcher.match(saved.diet.disliked_foods)
        supplements = self._matcher.match(saved.sports.supplements_owned)
        today = today or date.today()
        # La complexión y el horario de entreno viajan al perfil porque la SIMILITUD los consulta: `body_type` pesa
        # hoy 0,10, aunque el barrido de pesos dice que sobra — quitarlo gana +0,0166 [+0,0060,
        # +0,0271] bajo D3 — y la cifra con que se eligió se ha retirado por no reproducir. La sincronización se
        # mantenga o no el peso: sin esta línea el rasgo existía en el expediente, existía en la política y valía None para todo
        # cliente de la cartera, que es el mismo defecto que motivó ampliar la similitud: enriquecer un expediente
        # que la función de comparación no lee. Se copia lo DECLARADO; no se deriva nada de la muñeca aquí.
        synced = replace(profile,
                         age=saved.age_on(today) if saved.identification.birth_date else profile.age,
                         height_cm=saved.physiology.height_cm or profile.height_cm,
                         sport=(saved.sports.sports or "").strip()[:120] or profile.sport,
                         body_type=(saved.physiology.somatotype.value if saved.physiology.somatotype else profile.body_type),
                         training_time=(saved.sports.training_schedule or "").strip()[:120] or profile.training_time,
                         disliked_food_ids=disliked.food_ids, owned_supplement_ids=supplements.food_ids,
                         has_medical_restrictions=bool((saved.medical.injuries or "").strip() or (saved.medical.surgeries or "").strip()) or profile.has_medical_restrictions)
        self._clients.save(synced)
        return saved, synced, {"disliked_foods": disliked, "supplements_owned": supplements}
