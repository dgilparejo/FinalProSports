from fastapi import APIRouter

from finalprosports.infrastructure.adapter.inbound.rest.mapper.profile_mapper import rule_to_dto


class GetRulesRestAdapter:
    def __init__(self, root):
        self.router = APIRouter(tags=["rules"])
        service, current = root.get_rules_service, root.current_professional

        @self.router.get("/rules")
        def get_rules(include_low_confidence: bool = False):
            return [rule_to_dto(r) for r in service.get_rules(current.current_professional_id(), include_low_confidence)]
