from finalprosports.application.exception.client.client_not_found_error import ClientNotFoundError
from finalprosports.application.port.outbound.persistence.client.client_repository_output_port import ClientRepositoryOutputPort
from finalprosports.domain.model import ClientProfile


class GetClientsService:
    def __init__(self, clients: ClientRepositoryOutputPort):
        self._clients = clients

    def get_clients(self, professional_id: str) -> tuple[ClientProfile, ...]:
        return self._clients.list(professional_id)

    def get_client(self, professional_id: str, client_code: str) -> ClientProfile:
        profile = self._clients.get(professional_id, client_code)
        if profile is None:
            raise ClientNotFoundError(client_code)
        return profile
