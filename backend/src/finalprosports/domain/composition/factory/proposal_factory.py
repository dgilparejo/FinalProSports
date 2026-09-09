"""Assembles a DietProposal and converts it to a Diet (so that the rule engine and the overlap metrics see a proposal
exactly as they see a case).

Every proposal passes through here, whatever strategy built it, which makes it the one place where an impossible quantity can
be stopped for good. It is needed: the composer's own median is already guarded, but the rotation carries items forward from
the client's previous version verbatim, and that version can carry the professional's own slip — his document for this client
reads «160 Arroz vaporizado» with no unit, which the parser stored as 160 PIECES of rice and the exporter printed as
«160 Arroz». `sane` reads it back as the 160 grams it plainly was."""
from dataclasses import replace

from finalprosports.domain.composition.policy.quantity_policy import sane
from finalprosports.domain.model import AlternativeGroup, ClientProfile, Diet, DietProposal, Goal, Meal, ProposedItem, ProposedMeal, ValidationReport


def _sane_meals(meals: list[ProposedMeal]) -> tuple[ProposedMeal, ...]:
    out = []
    for m in meals:
        groups = []
        for g in m.groups:
            options = tuple(replace(o, item=replace(o.item, quantity=sane(o.item.quantity))) for o in g.options)
            groups.append(replace(g, options=options) if isinstance(g, AlternativeGroup) else g)
        out.append(replace(m, groups=tuple(groups)))
    return tuple(out)


def build_proposal(profile: ClientProfile, meals: list[ProposedMeal], notes: list[str], case_ids: list[str], strategy: str,
                   parameters: dict | None = None, validation: ValidationReport | None = None) -> DietProposal:
    return DietProposal(profile=profile, meals=_sane_meals(meals), notes=tuple(notes), retrieved_case_ids=tuple(case_ids), strategy=strategy,
                        parameters=dict(parameters or {}), validation=validation)


def to_diet(proposal: DietProposal, diet_id: str = "PROPUESTA") -> Diet:
    meals = tuple(Meal(m.slot, tuple(o.item for g in m.groups for o in g.options)) for m in proposal.meals)
    return Diet(id=diet_id, professional_id=proposal.profile.professional_id, client_code=proposal.profile.client_code,
                goal=proposal.profile.goal or Goal.UNCLASSIFIED, meals=meals, notes=tuple(proposal.notes))
