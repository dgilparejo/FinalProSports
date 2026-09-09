"""Text representation used for dense retrieval (E3.1).

The document is built from the STRUCTURED items (canonical food names per slot), not from the original diet text: it is
shorter (fits the 512-token window of e5-base), has no duplicates, and puts the goal and the profile first. The query text
has exactly the same header, so query and document are compared symmetrically:

    OBJETIVO: <goal_text or goal label> | META: <goal>
    PERFIL: sexo M | edad 25-39 | actividad 5 | intolerancias no
    DESAYUNO: avena, plátano, claras de huevo          <- documents only
    ...
    NOTAS: nota · nota · nota                          <- documents only (the most informative notes)

Values stay in Spanish (corpus literals); identifiers are English. Pure functions, no I/O.
"""
from __future__ import annotations

from finalprosports.domain.model import ClientProfile, Goal, MealSlot

GOAL_LABELS: dict[Goal, str] = {
    Goal.VOLUME: "volumen y ganancia de masa muscular",
    Goal.FAT_LOSS: "definición y pérdida de grasa",
    Goal.INTERMITTENT_FASTING: "ayuno intermitente",
    Goal.CARB_CYCLING: "descarga y carga de hidratos",
    Goal.KETO: "cetosis (dieta keto)",
    Goal.HYPOCALORIC: "dieta hipocalórica",
    Goal.HIGH_FIBRE: "dieta alta en fibra",
    Goal.MAINTENANCE: "mantenimiento",
    Goal.UNCLASSIFIED: "sin clasificar",
}
SLOT_ORDER: tuple[MealSlot, ...] = tuple(MealSlot)          # enum order = chronological order of the day
MAX_NOTE_CHARS = 160


def age_bucket(age: int | None) -> str:
    if age is None:
        return "edad_NA"
    return "<25" if age < 25 else "25-39" if age < 40 else "40-54" if age < 55 else "55+"


def header_lines(goal: Goal | None, goal_text: str | None, sex: str | None, age: int | None, activity_level: int | None,
                 has_intolerances: bool) -> list[str]:
    g = goal or Goal.UNCLASSIFIED
    label = (goal_text or "").strip() or GOAL_LABELS[g]
    return [f"OBJETIVO: {label} | META: {g.value}",
            f"PERFIL: sexo {sex or '?'} | edad {age_bucket(age)} | actividad {activity_level if activity_level is not None else '?'}"
            f" | intolerancias {'sí' if has_intolerances else 'no'}"]


def query_text(profile: ClientProfile) -> str:
    """Query side (e5 'query: ' prefix is added by the embedder adapter)."""
    return "\n".join(header_lines(profile.goal, None, profile.sex, profile.age, profile.activity_level, profile.has_intolerances))


def document_text(goal: Goal | None, goal_text: str | None, sex: str | None, age: int | None, activity_level: int | None,
                  has_intolerances: bool, slot_foods: dict[str, list[str]], notes: list[str]) -> str:
    """Document side. `slot_foods` maps a slot literal to canonical food names in order of appearance (duplicates removed here)."""
    lines = header_lines(goal, goal_text, sex, age, activity_level, has_intolerances)
    for slot in SLOT_ORDER:
        foods = slot_foods.get(slot.value)
        if foods:
            seen: dict[str, None] = dict.fromkeys(f for f in foods if f)
            lines.append(f"{slot.value}: {', '.join(seen)}")
    for slot, foods in slot_foods.items():                        # literals outside the enum (none expected) are kept last
        if slot not in {s.value for s in SLOT_ORDER} and foods:
            lines.append(f"{slot}: {', '.join(dict.fromkeys(f for f in foods if f))}")
    clean = [n.strip()[:MAX_NOTE_CHARS] for n in notes if n and n.strip()]
    if clean:
        lines.append("NOTAS: " + " · ".join(clean))
    return "\n".join(lines)
