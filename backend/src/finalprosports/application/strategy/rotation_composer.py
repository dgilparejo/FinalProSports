"""RotationComposer (2.3): ProposalStrategy for a RECURRENT client.

What the professional does: he does not rebuild the diet every month — he takes the last version and rotates species. So the
strategy starts from the client's latest previous version, applies the domain RotationPolicy (keep anchors, rotate rotatory
species within their family using the archetype consensus as the pool of replacements, up to his measured renewal rate) and
keeps the previous notes. Validation is done afterwards by the independent DietValidator, like for any proposal.
Without history it degrades to the case-based composer (cold start)."""
from __future__ import annotations

import dataclasses

from finalprosports.application.strategy.case_based_composer import CaseBasedComposer
from finalprosports.domain.composition.policy.note_catalogue import NoteCatalogue
from finalprosports.domain.composition.factory.proposal_factory import build_proposal
from finalprosports.domain.composition.policy.composition_policy import CompositionParams
from finalprosports.domain.composition.policy.rotation_policy import RotationParams, rotate
from finalprosports.domain.composition.policy.restriction_policy import veto_reasons
from finalprosports.domain.composition.policy.rule_applicability import applies
from finalprosports.domain.composition.policy.rule_support import attach_rule_support
from finalprosports.domain.model import ClientProfile, Diet, DietProposal, Food, RestrictionMode, RetrievedCase, RotationStats, Rule


def restriction_filter(profile: ClientProfile, mode: RestrictionMode):
    """A food the client may not eat is never a rotation candidate. Applying this downstream, in the validator, left the
    slot short of an item: the functional test lost five items in one proposal that way."""
    disliked = set(profile.disliked_food_ids or ())

    def allowed(food: Food) -> bool:
        return not veto_reasons(food, profile, mode) and food.id not in disliked

    return allowed


def latest_version(history: tuple[Diet, ...]) -> Diet | None:
    """The most recent previous version: highest numeric version, then id order (deterministic)."""
    if not history:
        return None
    return max(history, key=lambda d: ((d.diet_version if d.diet_version is not None and d.diet_version < 1000 else -1), d.id))


class RotationComposer:
    name = "rotation_composer"

    def __init__(self, catalog: dict[int, Food], stats: RotationStats, params: CompositionParams = CompositionParams(), rotation: RotationParams = RotationParams(),
                 mode: RestrictionMode = RestrictionMode.STRICT, medians: dict[tuple[int, str], float] | None = None,
                 notes: NoteCatalogue | None = None):
        self._catalog, self._stats, self.params, self.rotation = catalog, stats, params, rotation
        self._notes = notes
        self._cold = CaseBasedComposer(catalog, params, notes=notes)
        self._mode, self._medians = mode, medians          # medians: corpus (food, unit) -> p50, for the scale check of substitution_policy

    def repertoire(self, stats: RotationStats) -> dict[str, list[int]]:
        """Family -> foods of the catalogue ordered by the professional's use (same-goal prevalence measured in the rotation analysis)."""
        out: dict[str, list[int]] = {}
        for fid, f in self._catalog.items():
            if f.family:
                out.setdefault(f.family, []).append(fid)
        for fam in out:
            out[fam].sort(key=lambda i: (-(stats.food_prevalence.get(i, 0.0)), i))
        return out

    def propose(self, profile: ClientProfile, cases: tuple[RetrievedCase, ...], rules: tuple[Rule, ...], params: CompositionParams | None = None,
                history: tuple[Diet, ...] = (), stats: RotationStats | None = None, rotation: RotationParams | None = None,
                renewal_target: float | None = None) -> DietProposal:
        previous = latest_version(history)
        if previous is None:
            cold = self._cold.propose(profile, cases, rules, params)
            return build_proposal(profile, list(cold.meals), list(cold.notes), list(cold.retrieved_case_ids), self.name, {**cold.parameters, "mode": "cold_start"})
        p = params or self.params
        consensus = self._cold.propose(profile, cases, rules, p)                     # archetype consensus = pool of same-family replacements
        st = stats or self._stats
        goal_changed = profile.goal is not None and previous.goal != profile.goal
        rp = rotation or self.rotation
        if renewal_target is not None:                       # §8: the level the professional chose, for FOOD only
            rp = dataclasses.replace(rp, renewal_target=renewal_target)
        allowed = restriction_filter(profile, self._mode)                        # the client's restrictions decide INSIDE the selection, not downstream
        meals, changes, refusals = rotate(previous, list(consensus.meals), goal_changed, st, self._catalog, rp,
                                          repertoire=self.repertoire(st), allowed=allowed, medians=self._medians)
        applicable = [r for r in rules if applies(r, profile)]
        meals = attach_rule_support(meals, applicable, self._catalog)
        # his own previous notes travel with the client, but the parser's leftovers do not: «Observaciones:» and the
        # footer fragments are not instructions and must not be reprinted in the next version (E9).
        keep = (lambda t: not self._notes.is_artefact(t)) if self._notes else (lambda t: True)
        notes = [n for n in previous.notes if keep(n)] or list(consensus.notes)
        n_prev = sum(1 for m in previous.meals for i in m.items if i.food_id is not None)
        parameters = {**p.as_dict(), "mode": "rotation", "previous_version": previous.id, "goal_changed": goal_changed,
                      "renewal_target": rp.renewal_target if rp.renewal_target is not None else (st.renewal_goal_change if goal_changed else st.renewal_same_goal), "use_repertoire": rp.use_repertoire,
                      "rotated_items": len(changes), "previous_items": n_prev, "renewal_applied": round(len(changes) / n_prev, 3) if n_prev else 0.0,
                      "rotation_refusals": refusals[:40],
                      "changes": [{"slot": c.slot.value, "removed": c.removed_name, "added": c.added_name, "family": c.family, "persistence": c.persistence} for c in changes]}
        return build_proposal(profile, meals, notes, [c.diet.id for c in cases[: p.k]], self.name, parameters)
