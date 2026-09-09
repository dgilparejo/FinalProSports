"""Diets endpoints (E6): propose (use case with automatic strategy routing), save the edited diet, read it, export it as PDF, similar cases.

The propose response makes the engine visible without extra work for the UI: the strategy used and WHY (no history / same goal / goal
changed), the evidence per food (cases, support, backing rules with prevalence and lift), the validation report with the forced changes,
and the gap assessment when one was logged."""
from fastapi import APIRouter, HTTPException, Query, Response, status

from finalprosports.application.exception.client.client_not_found_error import ClientNotFoundError
from finalprosports.domain.model import ClientProfile, Goal, Restriction, RestrictionKind
from finalprosports.infrastructure.adapter.inbound.rest.dto.client_dto import ProposeDto, SavedProposalDto
from finalprosports.infrastructure.adapter.inbound.rest.dto.profile_dto import ProfileRequestDto
from finalprosports.infrastructure.adapter.inbound.rest.mapper.profile_mapper import to_domain
from finalprosports.infrastructure.adapter.inbound.rest.service.client.get_clients_rest_adapter import client_ref
from finalprosports.infrastructure.adapter.inbound.rest.service.record.lab_results_rest_adapter import lab_context
from finalprosports.infrastructure.adapter.outbound.persistence.mapper.proposal_mapper import proposal_from_dict, proposal_to_dict

ROUTING_LABELS = {"cold_start": "Sin historial: consenso de los casos más parecidos (arranque en frío)",
                  "same_goal": "Mismo objetivo que la versión anterior: se parte de ella y se rotan las especies rotatorias dentro de su familia",
                  "goal_changed": "Cambio de objetivo: la dieta anterior deja de ser referencia; consenso del arquetipo del nuevo objetivo (con las versiones anteriores como candidatos)"}


def _fill_names(d: dict, names: dict[int, str]) -> None:
    """Presentation only: items inherited from a previous version carry food_id but no canonical_name (the engine keeps the
    original line in ``text``); the UI shows the catalogue name, so resolve it here at the REST boundary."""
    for meal in d.get("meals", []):
        for group in meal.get("groups", []):
            for o in group.get("options", []):
                if not o.get("canonical_name") and o.get("food_id") in names:
                    o["canonical_name"] = names[o["food_id"]]
    for f in (d.get("validation") or {}).get("forced_changes", []):
        if not f.get("canonical_name") and f.get("food_id") in names:
            f["canonical_name"] = names[f["food_id"]]


def proposal_response(proposal, gap=None, names: dict[int, str] | None = None) -> dict:
    d = proposal_to_dict(proposal)
    if names:
        _fill_names(d, names)
    routing = proposal.parameters.get("routing", "cold_start")
    d["routing"] = {"code": routing, "label": ROUTING_LABELS.get(routing, routing), "strategy": proposal.strategy,
                    "previous_version": proposal.parameters.get("previous_version"), "rotated_items": proposal.parameters.get("rotated_items"),
                    "renewal_applied": proposal.parameters.get("renewal_applied"), "renewal_target": proposal.parameters.get("renewal_target"),
                    "degradation": proposal.parameters.get("degradation"), "k_effective": proposal.parameters.get("k_effective"), "same_goal_cases": proposal.parameters.get("same_goal_cases")}
    d["gap"] = gap
    d["owned_supplements"] = [{"food_id": i, "canonical_name": (names or {}).get(i)} for i in proposal.profile.owned_supplement_ids]   # S3: shown, never vetoed
    return d


class _LiveNames(dict):
    """food_id -> canonical name, read from the live catalogue dict on every access."""

    def __init__(self, catalog: dict):
        super().__init__()
        self._catalog = catalog

    def get(self, key, default=None):
        f = self._catalog.get(key)
        return f.canonical_name if f else default

    def __contains__(self, key):
        return key in self._catalog

    def __getitem__(self, key):
        return self._catalog[key].canonical_name

    def __bool__(self):
        return True


class ProposeDietRestAdapter:
    def __init__(self, root):
        self.router = APIRouter(tags=["diets"])
        use_case, retrieval, current, clients = root.propose_diet_use_case, root.retrieve_similar_cases_service, root.current_professional, root.get_clients_service
        save_uc, export_uc, proposals = root.save_edited_diet_use_case, root.export_diet_use_case, root.proposal_repository
        names = _LiveNames(root.catalog)                                   # S5: foods added at runtime are visible without restart
        labs, records, repo = root.lab_results, root.client_records, root.client_repository

        def context(pid: str, client_id: str) -> dict:
            """S4: what the professional sees next to the proposal and never enters the engine."""
            return {"lab_results": lab_context(labs.list(pid, client_id))}

        def who(pid: str, client_id: str) -> dict | None:
            """S9: the NAME travels with the response for the screen and the PDF, never inside the engine's profile."""
            record = records.get(pid, client_id)
            return client_ref(repo.get(pid, client_id), record.identification if record else None)

        def pdf_filename(pid: str, client_id: str, diet_id: str) -> str:
            record = records.get(pid, client_id)
            name = (record.identification.full_name or "").strip() if record else ""
            slug = "".join(ch if ch.isalnum() else "_" for ch in name).strip("_") or "cliente"
            version = diet_id.rsplit("::", 1)[-1]
            return f"dieta_{slug}_{version}"

        @self.router.post("/diets/propose", summary="Propose a diet for a client (strategy routed automatically: cold start / same goal / goal changed)")
        def propose(dto: ProposeDto):
            pid = current.current_professional_id()
            stored = clients.get_client(pid, dto.client_id)
            restrictions = stored.restrictions if dto.restrictions is None else tuple(Restriction(RestrictionKind(r), strict=dto.strict_restrictions) for r in dto.restrictions)
            profile = ClientProfile(client_code=stored.client_code, professional_id=pid, sex=stored.sex, age=stored.age, height_cm=stored.height_cm, activity_level=stored.activity_level,
                                    goal=Goal(dto.goal), has_allergies=stored.has_allergies, has_intolerances=stored.has_intolerances, has_medical_restrictions=stored.has_medical_restrictions,
                                    restrictions=restrictions, is_athlete=stored.is_athlete, sport=stored.sport,
                                    disliked_food_ids=stored.disliked_food_ids, owned_supplement_ids=stored.owned_supplement_ids)
            proposal = use_case.propose(pid, profile, k=dto.k, novelty=dto.novelty)
            a = retrieval.last_assessment
            gap = None
            if a is not None and a.is_gap:
                gap = {"kind": a.kind, "triggered": list(a.triggered), "counts": vars(a.counts), "best_score": a.best_score, "threshold": a.threshold}
            return proposal_response(proposal, gap, names) | {"client": who(pid, dto.client_id), "context": context(pid, dto.client_id)}

        @self.router.post("/diets", status_code=status.HTTP_201_CREATED, summary="Save a proposal (possibly edited): re-validated, then stored with its evidence")
        def save(dto: SavedProposalDto):
            pid = current.current_professional_id()
            proposal = proposal_from_dict(dto.model_dump(exclude={"edited", "original"}))
            original = proposal_from_dict({k: v for k, v in dto.original.items() if k in ("profile", "strategy", "parameters", "retrieved_case_ids", "meals", "notes", "validation")}) if dto.original else None
            saved = save_uc.save(pid, proposal, dto.edited, original)
            return {"id": saved["id"], **proposal_response(saved["proposal"], names=names), "client": who(pid, proposal.profile.client_code), "context": context(pid, proposal.profile.client_code),
                    "diff": saved["diff"].as_dict() if saved["diff"] is not None else None}

        @self.router.get("/diets/{diet_id}", summary="A saved diet with its evidence and validation")
        def get_diet(diet_id: str):
            pid = current.current_professional_id()
            proposal = proposals.get(pid, diet_id)
            if proposal is None:
                raise ClientNotFoundError(f"saved diet {diet_id}")
            meta = proposals.get_detail(pid, diet_id) or {}
            return {"id": diet_id, "edited": meta.get("edited"), "created_at": meta.get("created_at"), **proposal_response(proposal, names=names),
                    "client": who(pid, proposal.profile.client_code), "context": context(pid, str(proposal.profile.client_code)), "diff": meta.get("diff")}

        MEDIA = {"pdf": "application/pdf", "odt": "application/vnd.oasis.opendocument.text"}

        def _export(diet_id: str, fmt: str) -> Response:
            """The professional chooses the format. The PDF is what he hands to the client; the .odt is the document he can
            still edit, which is what he does today with each client's previous version. Same content behind both."""
            if fmt not in MEDIA:
                raise HTTPException(status_code=400, detail=f"formato no soportado: {fmt} (admitidos: {', '.join(MEDIA)})")
            pid = current.current_professional_id()
            data = export_uc.export(pid, diet_id, fmt)
            proposal = proposals.get(pid, diet_id)
            stem = pdf_filename(pid, proposal.profile.client_code, diet_id) if proposal else "dieta"
            disposition = "inline" if fmt == "pdf" else "attachment"        # a browser cannot display an .odt: it downloads
            return Response(content=data, media_type=MEDIA[fmt],
                            headers={"Content-Disposition": f'{disposition}; filename="{stem}.{fmt}"'})

        @self.router.get("/diets/{diet_id}/pdf", summary="PDF of a saved diet", response_class=Response,
                         responses={200: {"content": {"application/pdf": {}}}})
        def get_pdf(diet_id: str):
            return _export(diet_id, "pdf")

        @self.router.get("/diets/{diet_id}/export", summary="Saved diet in the format the professional chooses (pdf | odt)",
                         response_class=Response,
                         responses={200: {"content": {"application/pdf": {}, "application/vnd.oasis.opendocument.text": {}}}})
        def get_export(diet_id: str, format: str = Query("pdf", pattern="^(pdf|odt)$", description="pdf | odt")):
            return _export(diet_id, format)

        @self.router.post("/similar-cases", summary="Retrieval only: the k most similar cases for an ad-hoc profile")
        def similar(dto: ProfileRequestDto):
            pid = current.current_professional_id()
            cases = retrieval.retrieve(pid, to_domain(dto, pid), k=dto.k)
            return {"strategy": root.retrieval_strategy,
                    "cases": [{"rank": c.rank, "diet_id": c.diet.id, "goal": c.diet.goal.value, "score": round(c.score.total, 4),
                               "cosine": round(c.score.vector, 4), "attributes": round(c.score.attributes, 4)} for c in cases]}
