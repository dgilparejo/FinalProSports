from fastapi import APIRouter, Depends

from finalprosports.infrastructure.adapter.inbound.rest.security.authentication import build_authentication_dependency
from finalprosports.infrastructure.adapter.inbound.rest.service.catalog.get_food_catalog_rest_adapter import GetFoodCatalogRestAdapter
from finalprosports.infrastructure.adapter.inbound.rest.service.client.get_clients_rest_adapter import GetClientsRestAdapter
from finalprosports.infrastructure.adapter.inbound.rest.service.record.client_record_rest_adapter import ClientRecordRestAdapter
from finalprosports.infrastructure.adapter.inbound.rest.service.record.lab_results_rest_adapter import LabResultsRestAdapter
from finalprosports.infrastructure.adapter.inbound.rest.service.rules.get_rules_rest_adapter import GetRulesRestAdapter
from finalprosports.infrastructure.adapter.inbound.rest.usecase.proposal.propose_diet_rest_adapter import ProposeDietRestAdapter
from finalprosports.infrastructure.config.security import KeycloakConfig, TokenVerifier
from finalprosports.infrastructure.config.settings import Settings


def build_router(root, settings: Settings | None = None, authenticate=None) -> APIRouter:
    """Every route under /api/v1 carries the authentication dependency BY CONSTRUCTION.

    Mounting it on the router rather than on each endpoint is the point: a new endpoint is guarded
    the moment it is added, with nothing to remember. `tests/architecture/test_every_route_is_guarded.py`
    fails if a route ever ends up outside it.
    """
    if authenticate is None:
        config = KeycloakConfig.from_settings(settings or Settings())
        authenticate = build_authentication_dependency(TokenVerifier(config), root.professional_directory, config.required_role)

    router = APIRouter(prefix="/api/v1", dependencies=[Depends(authenticate)])
    for adapter in (GetFoodCatalogRestAdapter(root), GetClientsRestAdapter(root), ClientRecordRestAdapter(root), LabResultsRestAdapter(root), GetRulesRestAdapter(root), ProposeDietRestAdapter(root)):
        router.include_router(adapter.router)
    return router
