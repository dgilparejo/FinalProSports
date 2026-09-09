from finalprosports.application.port.outbound.persistence.diet.diet_repository_output_port import DietRepositoryOutputPort
from finalprosports.domain.model import Diet


class GetClientHistoryService:
    def __init__(self, diets: DietRepositoryOutputPort):
        self._diets = diets

    def get_history(self, professional_id: str, client_code: str) -> tuple[Diet, ...]:
        return self._diets.history(professional_id, client_code)
