"""ProposeDietUseCase: retrieval -> proposal strategy -> independent validator.

After the strategy, the S2 plausibility layer (proposal_completion_policy) completes the slot structure from the retrieved cases and
clamps quantities into the envelope mined from the corpus; the validator runs last. The harness measures the raw strategies.

Two scenarios (2.4): a NEW client (no history) is served by the cold-start strategy (case-based consensus of the archetype); a
RECURRENT client (previous versions available) is served by the recurrent strategy (RotationComposer: previous version + rotation
policy), because that is what the professional does and where the signal is. The history handed to the strategy contains only
versions the caller allows (the LOO harness passes strictly earlier versions and asserts it).
"""
from finalprosports.application.exception.proposal.goal_not_servable_error import GoalNotServableError
from finalprosports.domain.composition.policy.neighbourhood_policy import ServiceBand
from finalprosports.application.exception.proposal.no_similar_cases_error import NoSimilarCasesError
from finalprosports.application.port.inbound.service.retrieval.retrieve_similar_cases_input_port import RetrieveSimilarCasesInputPort
from finalprosports.application.port.outbound.persistence.plausibility.plausibility_envelope_output_port import PlausibilityEnvelopeOutputPort
from finalprosports.application.port.outbound.persistence.rules.rule_repository_output_port import RuleRepositoryOutputPort
from finalprosports.application.service.annotation import timed
from finalprosports.application.service.validation.diet_validator import DietValidator
from finalprosports.application.strategy.proposal_strategy import ProposalStrategy
from finalprosports.application.strategy.rotation_composer import latest_version
from finalprosports.domain.composition.policy.novelty_policy import DEFAULT, renewal_target
from finalprosports.domain.composition.policy.proposal_completion_policy import (complete_structure, harmonise_rations, name_variants, preserve_parentheticals,
                                                                                 normalize_quantities)
from finalprosports.domain.composition.policy.slot_applicability_policy import drop_inapplicable
from finalprosports.domain.model import ClientProfile, Diet, DietProposal


class ProposeDietUseCase:
    def __init__(self, retrieval: RetrieveSimilarCasesInputPort, strategy: ProposalStrategy, validator: DietValidator, rules: RuleRepositoryOutputPort,
                 recurrent_strategy: ProposalStrategy | None = None, history=None, route_goal_change_to_archetype: bool = True,
                 envelope: PlausibilityEnvelopeOutputPort | None = None, catalog: dict | None = None, completion: bool = True):
        self._retrieval, self._strategy, self._validator, self._rules = retrieval, strategy, validator, rules
        self._recurrent, self._history = recurrent_strategy, history         # history: DietRepositoryOutputPort-like (.history(pid, client_code))
        self._route_goal_change = route_goal_change_to_archetype
        self._envelope, self._catalog, self._completion = envelope, catalog or {}, completion   # S2 plausibility layer (off when no envelope is wired)

    def strategy_for(self, history: tuple[Diet, ...], profile: ClientProfile | None = None) -> ProposalStrategy:
        """Routing rule derived from the data (RESULTS §9): same goal -> start from the previous version and rotate; goal changed -> the previous
        diet stops being a reference and the archetype consensus is the better signal (copying the previous falls to 0,322 vs cold 0,292)."""
        if not history or self._recurrent is None:
            return self._strategy
        previous = latest_version(history)
        if self._route_goal_change and profile is not None and profile.goal is not None and previous is not None and previous.goal != profile.goal:
            return self._strategy
        return self._recurrent

    @timed
    def propose(self, professional_id: str, profile: ClientProfile, k: int = 20, exclude_diet_ids: frozenset[str] = frozenset(),
                history: tuple[Diet, ...] | None = None, novelty: str | None = None) -> DietProposal:
        cases = self._retrieval.retrieve(professional_id, profile, k, exclude_diet_ids)
        if not cases:
            raise NoSimilarCasesError(profile.client_code)
        if history is None:
            history = tuple(self._history.history(professional_id, profile.client_code)) if self._history is not None else ()
        rules = self._rules.all(professional_id)
        strategy = self.strategy_for(history, profile)
        target = renewal_target(novelty)                       # §8: the professional chooses how different this one is
        proposal = (strategy.propose(profile, cases, rules, history=history, renewal_target=target)
                    if strategy is self._recurrent else strategy.propose(profile, cases, rules))
        # Two categorical ways a goal turns out unservable, and neither is a tuned threshold.
        #   (a) the corpus holds ZERO cases of that goal, so whatever was retrieved belongs to a different goal and
        #       the diet would be served under a label the evidence does not support (dataset-v3: `mantenimiento`);
        #   (b) cases were retrieved but the consensus yielded no slot at all, because they carry no reproducible
        #       structure (dataset-v3: `alta_en_fibra`, 3 diets, 2 of them entirely in the unmapped bucket).
        # (a) is asked of the REPOSITORY, not of the retrieved k. `same_goal_cases` in the proposal counts the
        # same-goal cases AMONG the k, which is zero both when the corpus has none and when a client legitimately
        # changed goal and the neighbours come from the old one -- two different facts that must not be conflated.
        # `assess` is not in the inbound port (whose contract is `retrieve`), so it is used when the adapter offers
        # it and skipped otherwise; without it the outcome test below still catches the empty case.
        assess = getattr(self._retrieval, "assess", None)
        if profile.goal is not None and assess is not None:
            gap = assess(professional_id, profile, k, exclude_diet_ids, cases)
            if gap.counts.same_goal == 0:
                raise GoalNotServableError(profile.goal.value, cases=len(cases))
        # LAS TRES BANDAS. El criterio (a) de arriba solo detecta el corpus con CERO casos
        # del objetivo. Falta el escalón intermedio: un objetivo puede tener casos y aun asi tener tan pocos CLIENTES
        # distintos que los k votos sean una persona repetida. `hipocalorica` tiene UNO: veinte votos suyos no son un
        # consenso, son una copia con pasos intermedios, y servirla como «basada en casos» afirma algo que la
        # evidencia no sostiene. El corte esta en el numero absoluto de clientes del objetivo, no en una fraccion, y
        # vive en `neighbourhood_policy` con su justificacion.
        vecindario = getattr(self._retrieval, "last_neighbourhood", None)
        if vecindario is not None and vecindario.band is ServiceBand.DO_NOT_SERVE:
            raise GoalNotServableError(profile.goal.value if profile.goal else "sin_objetivo", cases=len(cases))
        if not proposal.meals:
            # The consensus produced NO slot. That is not a diet with a defect, it is the corpus saying it cannot
            # serve this goal, and the honest answer is to say so rather than to hand over an empty document.
            # Categorical, not a tuned threshold: the test is the OUTCOME (no slot survived), so it fires exactly
            # when there is nothing to deliver. On dataset-v3 it is `mantenimiento` (0 diets in the corpus) and
            # `alta_en_fibra` (3 diets, 2 of them entirely inside the unmapped bucket, so 1 usable).
            raise GoalNotServableError(profile.goal.value if profile.goal else "sin_objetivo", cases=len(cases))
        previous = latest_version(history) if history else None
        routing = "cold_start" if previous is None else ("goal_changed" if (profile.goal is not None and previous.goal != profile.goal and self._route_goal_change) else "same_goal")
        extra = {"routing": routing, "history_size": len(history), "novelty": novelty or DEFAULT.value}
        if vecindario is not None:
            # Lo que el panel de explicabilidad muestra: con cuantos casos del objetivo y de cuantos clientes
            # DISTINTOS se construyo. `neighbourhood_warning` va relleno solo en la banda SERVIR DECLARANDO.
            extra |= {"neighbourhood": {"band": vecindario.band.value, "goal_diets": vecindario.goal_diets,
                                        "goal_clients": vecindario.goal_clients,
                                        "distinct_clients": vecindario.distinct_clients,
                                        "available_goal_clients": vecindario.available_goal_clients},
                      "neighbourhood_warning": vecindario.warning}
        env = self._envelope.load(professional_id) if (self._completion and self._envelope is not None) else None
        if env is not None:                                                  # S2: plausibility layer — structure from the cases, quantities into the corpus envelope
            meals, changes = complete_structure(list(proposal.meals), cases, env, self._catalog,
                                                profile=proposal.profile, mode=self._validator._mode)  # noqa: SLF001 — same mode the validator will apply
            # `split_mixed_groups` está RETIRADO. Partía los grupos que mezclan papeles, que es un defecto real
            # (§4b y §4c), pero la cura resultó mucho peor que la enfermedad: desmontaba también los grupos
            # legítimos y dejaba la dieta atomizada. Medido sobre la dieta del cliente real, 46 grupos de
            # alternativas donde el profesional escribe una media de 7,08 (mediana 7, p95 12), con COMIDA pasando
            # de 5 líneas a 11 y CENA de 9 a 15: el cliente se comería las cuatro opciones de hidratos en vez de
            # elegir una. El defecto de los grupos mixtos hay que arreglarlo donde se FORMAN —composición y
            # rotación—, no desmontándolos después. `check_alternative_group_count` vigila ahora esta regresión.
            meals, q_changes = normalize_quantities(meals, env, self._catalog)   # units and bands first...
            meals, r_changes = harmonise_rations(meals, env, self._catalog)      # ... then the rations read together
            # Y se vuelve a acotar, porque las dos políticas pueden pelearse: armonizar la ración del pollo con la
            # del pescado que lo acompaña lo bajaba a 120 g, fuera de su propia banda [130, 300]. La banda del
            # alimento gana — es la que sale de sus 433 raciones escritas — y la proporción cede.
            meals, q2_changes = normalize_quantities(meals, env, self._catalog)
            changes += q_changes + r_changes + q2_changes
            meals = name_variants(meals, env, cases)
            # `preserve_parentheticals` PROBADO Y RETIRADO. El matiz entre paréntesis es de la LÍNEA, no del
            # alimento, y asignar a cada `food_id` el paréntesis más votado entre los vecinos produce disparates:
            # «1 Naranja (omega 3 si no tienes)» —el paréntesis era del D3K2—, «1 Multivitamínico / Minerales
            # (asada a ser posible)» y «28 gr Nueces (40 gr)». Conservarlos exige emparejar paréntesis con
            # componente dentro de la misma línea del caso, no un voto por alimento. Queda como trabajo declarado.                                 # §3: «Arroz integral», not «Arroz», when he said so
            proposal = proposal.__class__(**{**proposal.__dict__, "meals": tuple(meals)})
            extra["plausibility"] = {"applied": True, "changes": [c.as_dict() for c in changes]}
        applicable, dropped = drop_inapplicable(proposal.meals, profile)      # dataset-v2: a slot that depends on a fact about the CLIENT (intra-workout for someone who does not train)
        if dropped:
            proposal = proposal.__class__(**{**proposal.__dict__, "meals": applicable})
            extra["slots_not_applicable"] = list(dropped)
        proposal = proposal.__class__(**{**proposal.__dict__, "parameters": {**proposal.parameters, **extra}})
        validated = self._validator.validate(proposal, rules, profile, cases=cases)
        # §3 · «Arroz» generico en el DESAYUNO, la ultima violacion real de la dieta del cliente real.
        #
        # `name_variants` corria ANTES del validador, y el validador AÑADE alimentos: quitados «avena» y «cereales
        # integrales» por gluten, la regla `desayuno_avena_cereales` metio «arroz» en el desayuno. Ese item nace
        # despues de la capa de nombres, asi que salia con el canonico pelado mientras el arroz de COMIDA y el de
        # MEDIA TARDE -- los mismos veinte vecinos, siete de ellos escribiendo «Arroz integral» -- si llevaban la
        # variante. La causa no era el consenso: era el ORDEN.
        #
        # Se vuelve a pasar sobre la propuesta ya validada, con los MISMOS casos y el mismo suelo de consenso. Es
        # idempotente (solo rellena `display_name` donde falta) y no toca `food_id`, `canonical_name`, la cantidad ni
        # el conjunto de items, que es lo que leen el Jaccard y todas las cifras publicadas: cambia lo que se IMPRIME
        # y nada mas. Por eso puede aplicarse aqui sin reabrir la medicion, al contrario que acotar cantidades tras el
        # validador (DISCUSSION §3), que si mueve los items y quedo declarado y no aplicado.
        if env is not None:
            validated = validated.__class__(**{**validated.__dict__, "meals": tuple(name_variants(list(validated.meals), env, cases))})
        return validated
