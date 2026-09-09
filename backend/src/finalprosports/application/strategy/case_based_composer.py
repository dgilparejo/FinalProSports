"""v1 ProposalStrategy: compose a diet by consensus over the k retrieved cases (domain composition_policy), attach the rule
evidence per food (domain rule_support). Validation is NOT done here: DietValidator is an independent component that
validates any proposal, whatever strategy produced it (E4.4)."""
from dataclasses import replace
from finalprosports.domain.composition.factory.proposal_factory import build_proposal
from finalprosports.domain.composition.policy.composition_policy import CompositionParams, compose_meals, compose_notes
from finalprosports.domain.composition.policy.degradation_policy import select_cases
from finalprosports.domain.composition.policy.note_catalogue import NoteCatalogue
from finalprosports.domain.composition.policy.rule_applicability import applies
from finalprosports.domain.composition.policy.rule_support import attach_rule_support
from finalprosports.domain.composition.policy.supplement_placement_policy import place as place_supplements
from finalprosports.domain.model import ClientProfile, DietProposal, Food, RetrievedCase, Rule


class CaseBasedComposer:
    name = "case_based_composer"

    def __init__(self, catalog: dict[int, Food], params: CompositionParams = CompositionParams(), notes: NoteCatalogue | None = None,
                 interchangeable=None, supplement_slots=None):
        self._catalog, self.params, self._notes, self._interchangeable = catalog, params, notes, interchangeable
        # Tabla de RESPALDO para colocar suplementos; `None` deja la politica solo con los casos recuperados.
        self._supplement_slots = supplement_slots or {}

    def propose(self, profile: ClientProfile, cases: tuple[RetrievedCase, ...], rules: tuple[Rule, ...],
                params: CompositionParams | None = None) -> DietProposal:
        p = params or self.params
        used, mode, p = select_cases(cases, profile, p)        # k_effective = min(k, cases): explicit; degradation when same-goal cases are scarce (E5.6)
        liked = frozenset(profile.liked_food_ids or ())
        meals = compose_meals(used, p, self._catalog, interchangeable=self._interchangeable, liked=liked)
        if not meals and used:
            # A proposal with no meal at all is never a valid answer, and consensus can legitimately produce one:
            # for `alta_en_fibra` the corpus holds three diets, so a slot needs two of three cases to agree, and
            # once the non-composable bucket stopped counting none of them reached the threshold. Falling back to
            # the single most similar case is the degradation the system already uses when the neighbourhood is too
            # thin to compose from -- applied here on the outcome instead of on the count, because "three cases
            # available" and "three cases that agree on something" are not the same condition.
            meals = compose_meals(used[:1], replace(p, k=1, slot_threshold=0.0, inclusion_threshold=0.0),
                                  self._catalog, interchangeable=self._interchangeable, liked=liked)
            mode = "copy_top1_empty_consensus"
        # Los suplementos se colocan DONDE HAY QUE TOMARLOS, no en una lista al final del documento: primero segun lo
        # que hacen los casos recuperados de este cliente (resuelve el 74,8 %), despues segun la tabla minada del
        # corpus, y lo que ninguno de los dos sepa colocar se queda en el bloque. No anade, no quita, no cambia
        # cantidades: solo mueve de franja, y solo desde el bloque generico.
        meals = place_supplements(list(meals), used, self._catalog, self._supplement_slots)
        applicable = [r for r in rules if applies(r, profile)]
        meals = attach_rule_support(meals, applicable, self._catalog)
        notes = compose_notes(used, p, self._notes)
        parameters = {**p.as_dict(), "k_effective": len(used), "same_goal_cases": sum(1 for c in used if c.diet.goal == profile.goal), "degradation": mode}
        return build_proposal(profile, meals, notes, [c.diet.id for c in used], self.name, parameters)
