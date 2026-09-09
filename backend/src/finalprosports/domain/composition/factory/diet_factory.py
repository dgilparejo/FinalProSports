"""Builds Diet aggregates from plain records (used by persistence mappers and the ETL loader)."""
from finalprosports.domain.model import Diet, DietItem, Goal, Meal, MealSlot, Quantity, Unit


def build_diet(professional_id: str, record: dict, items: list[dict]) -> Diet:
    by_slot: dict[str, list[DietItem]] = {}
    for it in items:
        di = DietItem(meal_slot=MealSlot(it["meal_slot"]), position=it["position"], component_index=it["component_index"],
                      food_id=it["food_id"], canonical_name=it["canonical_name"], normalized_key=it["normalized_key"],
                      raw_text=it["raw_text"], quantity=Quantity(it["quantity"], Unit(it["unit"] or ""), it.get("raw_unit")),
                      alternative_group=it.get("alternative_group"), compound_group=it.get("compound_group"),
                      generic_assumption=bool(it.get("generic_assumption")), note=it.get("note"))
        by_slot.setdefault(it["meal_slot"], []).append(di)
    meals = tuple(Meal(MealSlot(slot), tuple(sorted(v, key=lambda x: (x.position, x.component_index)))) for slot, v in by_slot.items())
    meta = record.get("meta", record)
    return Diet(id=record["id"], professional_id=professional_id, client_code=meta["client_code"], goal=Goal(meta["goal"]), meals=meals,
                notes=tuple(record.get("notes", ())), goal_inferred=bool(meta.get("goal_inferred")), diet_version=meta.get("diet_version"),
                template_group_id=meta.get("template_group_id"), goal_text=meta.get("goal_text"), goals=tuple(meta.get("goals", ())))
