"""Clients endpoints (E6, S1, S9): list, register, detail, history. Every query is scoped by the current professional
(CurrentProfessionalOutputPort) AND to his portfolio: the case base (corpus) is never served as a client — the filter lives in the
repository, so no endpoint can reach a corpus profile even by key.

S9: the client is identified by NAME everywhere a person reads (list, file, proposal, PDF) and by an internal UUID
(``id``) everywhere the machine does (URLs, bodies). The name lives in the record's identification block and is joined here, at the
REST boundary; the profile — what the engine sees — never carries it."""
from fastapi import APIRouter, status

from finalprosports.domain.model import ClientProfile, Goal, Restriction, RestrictionKind
from finalprosports.domain.model.client_record import Identification
from finalprosports.infrastructure.adapter.inbound.rest.dto.client_dto import RegisterClientDto

ALLERGY_KINDS = (RestrictionKind.PEANUT, RestrictionKind.TREE_NUT, RestrictionKind.SHELLFISH, RestrictionKind.EGG, RestrictionKind.FISH)
INTOLERANCE_KINDS = (RestrictionKind.LACTOSE, RestrictionKind.GLUTEN, RestrictionKind.SOY)


def identification_to_dict(i: Identification | None) -> dict:
    i = i or Identification()
    return {"full_name": i.full_name, "birth_date": i.birth_date.isoformat() if i.birth_date else None, "phone": i.phone, "email": i.email}


def client_to_dict(p: ClientProfile, identification: Identification | None = None) -> dict:
    return {"id": p.client_code, **identification_to_dict(identification),
            "sex": p.sex, "age": p.age, "age_bucket": p.age_bucket, "height_cm": p.height_cm, "activity_level": p.activity_level,
            "goal": p.goal.value if p.goal else None, "is_athlete": p.is_athlete, "has_allergies": p.has_allergies, "has_intolerances": p.has_intolerances,
            "has_medical_restrictions": p.has_medical_restrictions, "restrictions": [r.kind.value for r in p.restrictions]}


def client_ref(p: ClientProfile | None, identification: Identification | None) -> dict | None:
    """The minimal reference other resources (proposal, saved diet) carry: key + name."""
    if p is None:
        return None
    return {"id": p.client_code, "full_name": identification.full_name if identification else None}


def profile_from_registration(dto: RegisterClientDto, professional_id: str) -> ClientProfile:
    """The DRAFT profile: the key is assigned by the use case; the age is derived from the birth date there too."""
    restrictions = tuple(Restriction(RestrictionKind(r)) for r in dto.restrictions)
    return ClientProfile(client_code="", professional_id=professional_id, sex=dto.sex, age=None, height_cm=dto.height_cm,
                         activity_level=dto.activity_level, goal=Goal(dto.goal) if dto.goal else None, is_athlete=dto.is_athlete,
                         has_allergies=any(r.kind in ALLERGY_KINDS for r in restrictions), has_intolerances=any(r.kind in INTOLERANCE_KINDS for r in restrictions),
                         restrictions=restrictions)


def identification_from_registration(dto: RegisterClientDto) -> Identification:
    return Identification(dto.full_name.strip(), dto.birth_date, (dto.phone or "").strip() or None, (dto.email or "").strip() or None)


def version_to_dict(d) -> dict:
    return {"id": d.id, "goal": d.goal.value, "diet_version": d.diet_version, "template_group_id": d.template_group_id,
            "slots": [m.slot.value for m in d.meals], "items": sum(len(m.items) for m in d.meals), "notes": len(d.notes),
            "meals": [{"slot": m.slot.value, "items": [{"food_id": i.food_id, "canonical_name": i.canonical_name, "text": i.raw_text, "quantity": i.quantity.value,
                                                        "unit": i.quantity.unit.value, "alternative_group": i.alternative_group} for i in m.items]} for m in d.meals]}


class GetClientsRestAdapter:
    def __init__(self, root):
        self.router = APIRouter(tags=["clients"])
        clients, history, current, register = root.get_clients_service, root.get_client_history_service, root.current_professional, root.register_client_use_case
        proposals, repo, records = root.proposal_repository, root.client_repository, root.client_records

        @self.router.get("/clients", summary="Clients of the current professional's portfolio, by name (never the case base)")
        def get_clients():
            pid = current.current_professional_id()
            saved, names = repo.count_saved_diets(pid), records.list_identifications(pid)
            rows = [client_to_dict(p, names.get(p.client_code)) | {"diet_count": saved.get(p.client_code, 0)} for p in clients.get_clients(pid)]
            return sorted(rows, key=lambda r: ((r["full_name"] or "").casefold(), r["id"]))

        @self.router.post("/clients", status_code=status.HTTP_201_CREATED, summary="Register a client by name (the id is a UUID assigned by the application)")
        def register_client(dto: RegisterClientDto):
            pid = current.current_professional_id()
            identification = identification_from_registration(dto)
            return client_to_dict(register.register(profile_from_registration(dto, pid), identification), identification)

        @self.router.get("/clients/{client_id}", summary="Client detail (profile + identification)")
        def get_client(client_id: str):
            pid = current.current_professional_id()
            record = records.get(pid, client_id)
            return client_to_dict(clients.get_client(pid, client_id), record.identification if record else None)

        @self.router.get("/clients/{client_id}/diets", summary="History: the versions saved for the client (the next proposal starts from the last one when the goal is unchanged)")
        def get_diets(client_id: str):
            pid = current.current_professional_id()
            clients.get_client(pid, client_id)
            versions = sorted(history.get_history(pid, client_id), key=lambda d: ((d.diet_version if d.diet_version is not None else -1), d.id))
            return {"versions": [version_to_dict(d) for d in versions], "saved": list(proposals.list_for_client(pid, client_id))}

        @self.router.get("/clients/{client_id}/history", include_in_schema=False)
        def get_history_legacy(client_id: str):
            return get_diets(client_id)["versions"]
