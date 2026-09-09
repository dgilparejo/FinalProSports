"""DietProposal <-> plain dict (the JSON stored in saved_diets.payload and served by the REST layer). One mapper, both directions."""
from __future__ import annotations

from finalprosports.domain.model import (
    AlternativeGroup, ClientProfile, DietItem, DietProposal, ForcedChange, Goal, ItemEvidence, MealSlot, ProposedItem, ProposedMeal, Quantity, Restriction,
    RestrictionKind, RuleCheck, RuleSupport, Unit, ValidationReport,
)


def profile_to_dict(p: ClientProfile) -> dict:
    return {"client_code": p.client_code, "professional_id": p.professional_id, "sex": p.sex, "age": p.age, "height_cm": p.height_cm, "activity_level": p.activity_level,
            "goal": p.goal.value if p.goal else None, "has_allergies": p.has_allergies, "has_intolerances": p.has_intolerances,
            "has_medical_restrictions": p.has_medical_restrictions, "restrictions": [{"kind": r.kind.value, "strict": r.strict} for r in p.restrictions], "is_athlete": p.is_athlete,
            "sport": p.sport, "disliked_food_ids": list(p.disliked_food_ids), "owned_supplement_ids": list(p.owned_supplement_ids)}


def profile_from_dict(d: dict) -> ClientProfile:
    return ClientProfile(client_code=d["client_code"], professional_id=d["professional_id"], sex=d.get("sex"), age=d.get("age"), height_cm=d.get("height_cm"),
                         activity_level=d.get("activity_level"), goal=Goal(d["goal"]) if d.get("goal") else None, has_allergies=bool(d.get("has_allergies")),
                         has_intolerances=bool(d.get("has_intolerances")), has_medical_restrictions=bool(d.get("has_medical_restrictions")),
                         restrictions=tuple(Restriction(RestrictionKind(r["kind"]), bool(r.get("strict", True))) for r in d.get("restrictions", [])), is_athlete=d.get("is_athlete"),
                         sport=d.get("sport"), disliked_food_ids=tuple(int(i) for i in d.get("disliked_food_ids", ())), owned_supplement_ids=tuple(int(i) for i in d.get("owned_supplement_ids", ())))


def item_to_dict(o: ProposedItem) -> dict:
    i = o.item
    return {"food_id": i.food_id, "canonical_name": i.canonical_name, "display_name": i.display_name, "normalized_key": i.normalized_key, "text": i.raw_text,
            "quantity": i.quantity.value, "unit": i.quantity.unit.value, "alternative_group": i.alternative_group, "compound_group": i.compound_group, "note": i.note,
            "evidence": {"support": o.evidence.support, "cases": list(o.evidence.case_ids),
                         "rules": [{"rule_id": r.rule_id, "prevalence": r.prevalence, "lift": r.lift} for r in o.evidence.rules]}}


def item_from_dict(d: dict, slot: MealSlot, position: int, component_index: int) -> ProposedItem:
    ev = d.get("evidence") or {}
    item = DietItem(meal_slot=slot, position=position, component_index=component_index, food_id=d.get("food_id"), canonical_name=d.get("canonical_name"),
                    normalized_key=d.get("normalized_key") or (d.get("canonical_name") or ""), raw_text=d.get("text") or (d.get("canonical_name") or ""),
                    quantity=Quantity(d.get("quantity"), Unit(d.get("unit") or "")), alternative_group=d.get("alternative_group"), compound_group=d.get("compound_group"), note=d.get("note"),
                    display_name=d.get("display_name"))    # his own wording when it is more specific than the canonical (§3)
    return ProposedItem(item, ItemEvidence(tuple(ev.get("cases", ())), float(ev.get("support", 0.0)),
                                           tuple(RuleSupport(r["rule_id"], r.get("prevalence"), r.get("lift")) for r in ev.get("rules", []))))


def proposal_to_dict(p: DietProposal) -> dict:
    v = p.validation
    return {"profile": profile_to_dict(p.profile), "strategy": p.strategy, "parameters": p.parameters, "retrieved_case_ids": list(p.retrieved_case_ids),
            "meals": [{"slot": m.slot.value, "groups": [{"position": g.position, "options": [item_to_dict(o) for o in g.options]} for g in m.groups]} for m in p.meals],
            "notes": list(p.notes),
            "validation": {"compliance": v.compliance,
                           "rules": [{"rule_id": c.rule_id, "applicable": c.applicable, "satisfied": c.satisfied, "enforced": c.enforced} for c in v.rule_checks],
                           "forced_changes": [{"slot": f.slot.value, "food_id": f.food_id, "canonical_name": f.canonical_name, "action": f.action, "reason": f.reason} for f in v.forced_changes],
                           "warnings": list(v.warnings)} if v else None}


def proposal_from_dict(d: dict) -> DietProposal:
    meals = []
    for m in d.get("meals", []):
        slot = MealSlot(m["slot"])
        groups = []
        for pos, g in enumerate(m.get("groups", [])):
            options = tuple(item_from_dict(o, slot, pos, ci) for ci, o in enumerate(g.get("options", [])))
            if options:
                groups.append(AlternativeGroup(pos, options))
        if groups:
            meals.append(ProposedMeal(slot, tuple(groups)))
    v = d.get("validation")
    validation = ValidationReport(tuple(RuleCheck(c["rule_id"], c["applicable"], c.get("satisfied"), bool(c.get("enforced"))) for c in v.get("rules", [])),
                                  tuple(ForcedChange(MealSlot(f["slot"]), f.get("food_id"), f.get("canonical_name"), f.get("action", "removed"), f["reason"]) for f in v.get("forced_changes", [])),
                                  tuple(v.get("warnings", []))) if v else None
    return DietProposal(profile=profile_from_dict(d["profile"]), meals=tuple(meals), notes=tuple(d.get("notes", [])), retrieved_case_ids=tuple(d.get("retrieved_case_ids", [])),
                        strategy=d.get("strategy", "edited"), parameters=dict(d.get("parameters") or {}), validation=validation)
