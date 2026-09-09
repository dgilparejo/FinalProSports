from finalprosports.domain.composition.factory.diet_factory import build_diet
from finalprosports.domain.model import Diet
from finalprosports.infrastructure.adapter.outbound.persistence.entity.diet_entity import DietEntity, DietItemEntity


def to_domain(d: DietEntity, items: list[DietItemEntity]) -> Diet:
    record = {"id": d.id, "notes": list(d.notes or ()), "meta": {"client_code": d.client_code, "goal": d.goal, "goals": list(d.goals or ()),
              "goal_inferred": d.goal_inferred, "diet_version": d.diet_version, "template_group_id": d.template_group_id, "goal_text": d.goal_text}}
    rows = [{"meal_slot": i.meal_slot, "position": i.position, "component_index": i.component_index, "food_id": i.food_id,
             "canonical_name": None, "normalized_key": i.normalized_key, "raw_text": i.raw_text,
             "quantity": float(i.quantity) if i.quantity is not None else None, "unit": i.unit, "raw_unit": i.raw_unit,
             "alternative_group": i.alternative_group, "compound_group": i.compound_group, "generic_assumption": i.generic_assumption, "note": i.note}
            for i in items]
    return build_diet(d.professional_id, record, rows)
