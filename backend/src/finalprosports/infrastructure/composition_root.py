"""The only place where implementations are wired to ports."""
from __future__ import annotations

from pathlib import Path

from dataclasses import dataclass

from finalprosports.application.service.catalog.food_matcher import FoodMatcher
from finalprosports.application.service.catalog.get_food_catalog_service import GetFoodCatalogService
from finalprosports.application.service.record.get_client_record_service import GetClientRecordService
from finalprosports.application.usecase.record.add_lab_results_use_case import AddLabResultsUseCase
from finalprosports.application.usecase.record.import_body_composition_use_case import ImportBodyCompositionUseCase
from finalprosports.application.usecase.record.update_client_record_use_case import UpdateClientRecordUseCase
from finalprosports.infrastructure.adapter.outbound.persistence.service.record.client_record_output_adapter import BodyMeasurementOutputAdapter, ClientRecordOutputAdapter
from finalprosports.infrastructure.adapter.outbound.persistence.service.record.lab_result_output_adapter import LabResultOutputAdapter
from finalprosports.application.service.client.get_client_history_service import GetClientHistoryService
from finalprosports.application.service.client.get_clients_service import GetClientsService
from finalprosports.application.service.retrieval.retrieve_similar_cases_service import RetrieveSimilarCasesService
from finalprosports.application.service.rules.get_rules_service import GetRulesService
from finalprosports.application.service.validation.diet_validator import DietValidator
from finalprosports.application.strategy.case_based_composer import CaseBasedComposer
from finalprosports.application.strategy.rotation_composer import RotationComposer
from finalprosports.infrastructure.adapter.outbound.persistence.service.rotation.file_rotation_stats_adapter import FileRotationStatsAdapter
from finalprosports.infrastructure.adapter.outbound.persistence.service.notes.file_note_catalogue_adapter import FileNoteCatalogueAdapter
from finalprosports.infrastructure.adapter.outbound.persistence.service.plausibility.file_plausibility_envelope_adapter import FilePlausibilityEnvelopeAdapter
from finalprosports.infrastructure.adapter.outbound.persistence.service.plausibility.file_supplement_slots_adapter import (
    FileSupplementSlotsAdapter)
from finalprosports.domain.composition.policy.composition_policy import CompositionParams
from finalprosports.domain.composition.policy.rotation_policy import RotationParams
from finalprosports.domain.composition.policy.rule_applicability import with_low_confidence_enabled
from finalprosports.domain.model import RestrictionMode
from finalprosports.application.usecase.catalog.add_food_use_case import AddFoodUseCase
from finalprosports.application.usecase.client.register_client_use_case import RegisterClientUseCase
from finalprosports.application.usecase.diet.export_diet_use_case import ExportDietUseCase
from finalprosports.application.usecase.diet.save_edited_diet_use_case import SaveEditedDietUseCase
from finalprosports.application.usecase.proposal.propose_diet_use_case import ProposeDietUseCase
from finalprosports.infrastructure.adapter.outbound.export.odt_diet_exporter_adapter import OdtDietExporterAdapter
from finalprosports.infrastructure.adapter.outbound.export.pdf_diet_exporter_adapter import PdfDietExporterAdapter
from finalprosports.infrastructure.adapter.outbound.persistence.service.proposal.proposal_repository_output_adapter import ProposalRepositoryOutputAdapter
from finalprosports.infrastructure.adapter.outbound.persistence.repository.gap_log_adapter import GapLogAdapter
from finalprosports.infrastructure.adapter.outbound.persistence.service.case.case_repository_output_adapter import CaseRepositoryBase
from finalprosports.infrastructure.adapter.outbound.persistence.service.case.retrieval_strategy_adapters import case_repository_for
from finalprosports.infrastructure.adapter.outbound.persistence.service.catalog.food_catalog_output_adapter import FoodCatalogOutputAdapter
from finalprosports.infrastructure.adapter.outbound.persistence.service.client.client_repository_output_adapter import ClientRepositoryOutputAdapter
from finalprosports.infrastructure.adapter.outbound.persistence.service.diet.saved_diet_history_output_adapter import SavedDietHistoryOutputAdapter
from finalprosports.infrastructure.adapter.outbound.persistence.service.rules.rule_repository_output_adapter import RuleRepositoryOutputAdapter
from finalprosports.infrastructure.adapter.outbound.persistence.repository.professional_directory_adapter import ProfessionalDirectoryAdapter
from finalprosports.infrastructure.adapter.outbound.security.request_scoped_professional_adapter import RequestScopedProfessionalAdapter
from finalprosports.infrastructure.config.persistence import make_session_factory
from finalprosports.infrastructure.config.settings import Settings


@dataclass
class CompositionRoot:
    current_professional: RequestScopedProfessionalAdapter
    professional_directory: ProfessionalDirectoryAdapter
    configured_professional_id: str      # OFFLINE tools only (harness, demo seed): they are not requests and have no token
    get_food_catalog_service: GetFoodCatalogService
    get_clients_service: GetClientsService
    get_client_history_service: GetClientHistoryService
    get_rules_service: GetRulesService
    retrieve_similar_cases_service: RetrieveSimilarCasesService
    propose_diet_use_case: ProposeDietUseCase
    register_client_use_case: RegisterClientUseCase
    save_edited_diet_use_case: SaveEditedDietUseCase
    export_diet_use_case: ExportDietUseCase
    proposal_repository: ProposalRepositoryOutputAdapter
    client_repository: ClientRepositoryOutputAdapter
    client_records: ClientRecordOutputAdapter
    history: SavedDietHistoryOutputAdapter
    get_client_record_service: GetClientRecordService
    update_client_record_use_case: UpdateClientRecordUseCase
    import_body_composition_use_case: ImportBodyCompositionUseCase
    add_lab_results_use_case: AddLabResultsUseCase
    add_food_use_case: AddFoodUseCase
    lab_results: LabResultOutputAdapter
    composer: CaseBasedComposer
    rotation_composer: RotationComposer
    rotation_stats: object                            # RotationStatsOutputPort
    validator: DietValidator
    rules: object                                     # RuleRepositoryOutputPort (low-confidence switch applied)
    catalog: dict
    embedder: object                                  # EmbedderOutputPort; exposed for the eval adapters (latency per phase)
    case_repository: CaseRepositoryBase
    retrieval_strategy: str = "attributes"
    envelope: FilePlausibilityEnvelopeAdapter | None = None   # PlausibilityEnvelopeOutputPort (S2)
    note_catalogue: object | None = None                      # NoteCatalogueOutputPort (E9): canonical notes by theme

    @classmethod
    def from_env(cls, embedder=None) -> "CompositionRoot":
        settings = Settings()
        sf = make_session_factory(settings.database_url)
        catalog = FoodCatalogOutputAdapter(sf)
        cases = case_repository_for(settings.retrieval_strategy, sf, alpha=settings.hybrid_alpha)
        clients = ClientRepositoryOutputAdapter(sf)
        current = RequestScopedProfessionalAdapter()      # v2: the professional comes from THIS request's token, never from configuration
        directory = ProfessionalDirectoryAdapter(sf)      # sub -> professional (migration 0011)
        if embedder is None:
            from finalprosports.infrastructure.adapter.outbound.embeddings.e5_embedder_adapter import LazyE5EmbedderAdapter
            embedder = LazyE5EmbedderAdapter(settings.embedding_model, revision=settings.embedding_model_revision)   # loaded on first use only
        gaps = GapLogAdapter(sf)
        retrieval = RetrieveSimilarCasesService(embedder, cases, gaps, settings.similarity_threshold)
        foods = catalog.by_id(settings.professional_id)
        _sec = Path(settings.professional_secondary_logo) if settings.professional_secondary_logo else None
        _pdf = PdfDietExporterAdapter(settings.professional_brand, settings.professional_contact, secondary_logo=_sec)
        _odt = OdtDietExporterAdapter(settings.professional_brand, settings.professional_contact, secondary_logo=_sec)
        note_catalogue = FileNoteCatalogueAdapter()                       # E9 canonical notes (None when the file is absent: literal consensus)
        _notes = note_catalogue.load(settings.professional_id)
        rotation_stats = FileRotationStatsAdapter()
        _rot = rotation_stats.load(settings.professional_id)
        _inter = _rot.are_interchangeable if _rot.interchangeable else None   # the pairs HE writes as alternatives (rotation + composition)
        # Donde va cada suplemento: respaldo minado del corpus, para lo que los casos recuperados no sepan colocar.
        _supplement_slots = FileSupplementSlotsAdapter().load(settings.professional_id)
        composer = CaseBasedComposer(foods, CompositionParams(k=settings.composer_k, inclusion_threshold=settings.composer_inclusion_threshold),
                                     notes=_notes, interchangeable=_inter, supplement_slots=_supplement_slots)
        envelope = FilePlausibilityEnvelopeAdapter()                      # S2 plausibility layer (None when the file is absent)
        _env = envelope.load(settings.professional_id) if envelope is not None else None
        validator = DietValidator(foods, RestrictionMode(settings.restriction_mode), settings.enforce_rules, envelope=_env)   # the completion quantifies with his medians
        _medians = {k: b.p50 for k, b in _env.quantities.items()} if _env is not None else None      # (food_id, unit) -> median, for the scale check of the rotation
        rotation_composer = RotationComposer(foods, _rot, composer.params,
                                            RotationParams(use_repertoire=settings.rotation_use_repertoire),
                                            mode=RestrictionMode(settings.restriction_mode), medians=_medians, notes=_notes)
        recurrent = rotation_composer if settings.recurrent_strategy == "rotation" else None
        proposals = ProposalRepositoryOutputAdapter(sf)
        rules = _RulesWithSwitch(RuleRepositoryOutputAdapter(sf), settings.enable_low_confidence_rules)
        history = SavedDietHistoryOutputAdapter(sf)                       # S1: a portfolio client's versions are the diets saved for him
        records, measurements = ClientRecordOutputAdapter(sf), BodyMeasurementOutputAdapter(sf)      # S3 intake
        labs = LabResultOutputAdapter(sf)                                                              # S4 analytics (context only)
        matcher = FoodMatcher(foods)                                                                    # shared: intake text -> catalogue; grows with S5 additions
        return cls(current_professional=current, professional_directory=directory, configured_professional_id=settings.professional_id, get_food_catalog_service=GetFoodCatalogService(catalog),
                   get_clients_service=GetClientsService(clients), get_client_history_service=GetClientHistoryService(history),
                   get_rules_service=GetRulesService(rules), retrieve_similar_cases_service=retrieval,
                   propose_diet_use_case=ProposeDietUseCase(retrieval, composer, validator, rules, recurrent_strategy=recurrent, history=history,
                                                            route_goal_change_to_archetype=settings.route_goal_change_to_archetype,
                                                            envelope=envelope, catalog=foods, completion=settings.plausibility_completion),
                   embedder=embedder, case_repository=cases, retrieval_strategy=settings.retrieval_strategy,
                   register_client_use_case=RegisterClientUseCase(clients, records), save_edited_diet_use_case=SaveEditedDietUseCase(proposals, validator, rules),
                   export_diet_use_case=ExportDietUseCase(proposals, _pdf, labs, records, exporters={"pdf": _pdf, "odt": _odt}, clients=clients), proposal_repository=proposals, client_repository=clients, client_records=records, history=history,
                   get_client_record_service=GetClientRecordService(clients, records, measurements),
                   update_client_record_use_case=UpdateClientRecordUseCase(clients, records, matcher),
                   add_food_use_case=AddFoodUseCase(catalog, foods, matcher),
                   import_body_composition_use_case=ImportBodyCompositionUseCase(clients, measurements),
                   add_lab_results_use_case=AddLabResultsUseCase(clients, labs), lab_results=labs,
                   composer=composer, note_catalogue=note_catalogue, rotation_composer=rotation_composer, rotation_stats=rotation_stats, validator=validator, rules=rules, catalog=foods, envelope=envelope)


class _RulesWithSwitch:
    """RuleRepositoryOutputPort that applies the low-confidence configuration switch to the stored rules."""

    def __init__(self, inner, enable_low: bool):
        self._inner, self._enable_low = inner, enable_low

    def all(self, professional_id: str):
        rules = self._inner.all(professional_id)
        return with_low_confidence_enabled(rules, True) if self._enable_low else rules
