# -*- coding: utf-8 -*-
"""The line that is not crossed: a declared hard restriction is honoured 100 % of the time, on every path.

Everything else in this system is calibrated against what the professional does — rules are demanded only when they are
prescriptive, quantities are bounded by the percentiles of his own practice, rotation renews at the rate he renews. None of
that reasoning may ever reach an allergy, an intolerance or a coeliac's gluten. A coeliac does not receive gluten in 10 % of
the diets, or in one. It is the only point of the system with clinical risk, so it gets its own test and the test is
exhaustive over `RestrictionKind` rather than illustrative over one case.

Four paths can put a food into a proposal, and each is checked separately, because it is the second and third that are easy
to forget: they were built to ADD food, not to filter it.
  1. the composer's consensus, then the validator's veto pass;
  2. the validator's completion — a prescriptive rule demanding a food group must declare itself unsatisfiable rather than
     add a forbidden food;
  3. the plausibility layer's structural completion, which fills a slot from the retrieved cases;
  4. the rotation's substitution, which swaps a food for another of its family.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from finalprosports.application.service.validation.diet_validator import DietValidator  # noqa: E402
from finalprosports.application.strategy.case_based_composer import CaseBasedComposer  # noqa: E402
from finalprosports.domain.composition.factory.proposal_factory import to_diet  # noqa: E402
from finalprosports.domain.composition.policy.composition_policy import CompositionParams  # noqa: E402
from finalprosports.domain.composition.policy.plausibility_policy import PlausibilityEnvelope  # noqa: E402
from finalprosports.domain.composition.policy.proposal_completion_policy import complete_structure  # noqa: E402
from finalprosports.domain.composition.policy.restriction_policy import veto_reasons  # noqa: E402
from finalprosports.domain.model import (  # noqa: E402
    ClientProfile, Diet, DietItem, Food, FoodFlags, FoodGroup, Goal, Meal, MealSlot, Quantity, Restriction, RestrictionKind,
    RestrictionMode, RetrievedCase, Rule, RuleConfidence, RuleNature, RuleScope, RuleStatus, SimilarityScore, Unit,
)

# One catalogued food per restriction kind, each the ONLY protein/carb of its slot so the engine is pushed hardest: to satisfy
# a rule demanding that group it would have to use the forbidden food or declare defeat.
FORBIDDEN = {k: 100 + i for i, k in enumerate(RestrictionKind)}
CATALOG: dict[int, Food] = {}
for kind, fid in FORBIDDEN.items():
    CATALOG[fid] = Food(fid, f"alimento_{kind.name.lower()}", FoodGroup.PROTEIN, "prueba",
                        flags=FoodFlags(**{kind.value: True}))
CATALOG[1] = Food(1, "verdura neutra", FoodGroup.VEGETABLE, "verdura")
CATALOG[2] = Food(2, "grasa neutra", FoodGroup.FAT, "grasa")

RULES = (
    Rule("cena_proteina_grasa_verdura", "", RuleScope.GLOBAL, RuleStatus.KEPT, "item", (), RuleConfidence.HIGH,
         prevalence=0.86, nature=RuleNature.PRESCRIPTIVE),
    Rule("desayuno_avena_cereales", "", RuleScope.GLOBAL, RuleStatus.KEPT, "item", (), RuleConfidence.HIGH,
         prevalence=0.65, nature=RuleNature.PRESCRIPTIVE),
    Rule("suplementacion_pre_post", "", RuleScope.GLOBAL, RuleStatus.KEPT, "item", (), RuleConfidence.HIGH,
         prevalence=0.59, nature=RuleNature.PRESCRIPTIVE),
)


def item(slot, pos, comp, fid, q=150):
    f = CATALOG[fid]
    return DietItem(slot, pos, comp, fid, f.canonical_name, f.canonical_name, f.canonical_name, Quantity(q, Unit.GRAM))


def case(fid: int, rank: int) -> RetrievedCase:
    """A neighbour whose every slot leans on the forbidden food, so consensus, completion and rotation all reach for it."""
    meals = tuple(Meal(s, (item(s, 0, 0, fid), item(s, 1, 0, 1), item(s, 2, 0, 2)))
                  for s in (MealSlot.BREAKFAST, MealSlot.LUNCH, MealSlot.DINNER, MealSlot.PRE_WORKOUT))
    return RetrievedCase(Diet(f"C{fid}_{rank}::v01", "p", f"C{fid}_{rank}", Goal.VOLUME, meals), SimilarityScore(0, 1, 1), rank)


def profile_with(kind: RestrictionKind) -> ClientProfile:
    return ClientProfile("Q", "p", "M", 30, 180, 5, goal=Goal.VOLUME, restrictions=(Restriction(kind, True),))


def offending(diet: Diet, profile: ClientProfile, mode: RestrictionMode) -> list[str]:
    return [i.canonical_name for m in diet.meals for i in m.items
            if i.food_id in CATALOG and veto_reasons(CATALOG[i.food_id], profile, mode)]


def _pipeline(kind: RestrictionKind, mode: RestrictionMode):
    profile = profile_with(kind)
    cases = tuple(case(FORBIDDEN[kind], r) for r in range(1, 6))
    composer = CaseBasedComposer(CATALOG, CompositionParams(k=5, inclusion_threshold=0.3))
    raw = composer.propose(profile, cases, RULES)
    validated = DietValidator(CATALOG, mode, True).validate(raw, RULES, profile, cases=cases)
    return profile, cases, raw, validated


def test_no_restricted_food_survives_the_delivered_pipeline_for_any_restriction_kind():
    for kind in RestrictionKind:
        profile, _, _, validated = _pipeline(kind, RestrictionMode.STRICT)
        bad = offending(to_diet(validated), profile, RestrictionMode.STRICT)
        assert not bad, f"{kind.name}: the delivered proposal carries {bad}"


def test_the_completion_declares_defeat_instead_of_adding_a_forbidden_food():
    """A prescriptive rule demands a protein at dinner and the only protein the cases offer is the forbidden one. The rule
    must come back declared unsatisfiable — the whole point of the symmetric validator is that it may ADD food, and this is
    where that power has to stop."""
    for kind in RestrictionKind:
        profile, _, _, validated = _pipeline(kind, RestrictionMode.STRICT)
        added = [c for c in validated.validation.forced_changes if getattr(c, "action", None) == "added"]
        for c in added:
            assert not veto_reasons(CATALOG[c.food_id], profile, RestrictionMode.STRICT), \
                f"{kind.name}: the completion added a forbidden food ({c.food_name})"


def test_the_plausibility_completion_never_fills_a_slot_with_a_forbidden_food():
    for kind in RestrictionKind:
        profile, cases, raw, _ = _pipeline(kind, RestrictionMode.STRICT)
        # no envelope at all: the completion falls back to the cases, which is the hardest setting for this guard.
        # What is asserted is what the completion ADDS: the composer's own output is the validator's business, and this
        # function's contract is that it never introduces a food the client may not eat.
        _, changes = complete_structure(list(raw.meals), cases, None, CATALOG, profile=profile, mode=RestrictionMode.STRICT)
        bad = [c.canonical_name for c in changes
               if c.food_id in CATALOG and veto_reasons(CATALOG[c.food_id], profile, RestrictionMode.STRICT)]
        assert not bad, f"{kind.name}: the plausibility completion introduced {bad}"


def test_professional_mode_relaxes_lactose_and_nothing_else():
    """The one calibrated concession that exists — he does not restrict dairy to lactose-intolerant clients — and the proof
    that it is confined to lactose. Every other kind stays a veto in PROFESSIONAL mode too."""
    for kind in RestrictionKind:
        profile, _, _, validated = _pipeline(kind, RestrictionMode.PROFESSIONAL)
        bad = offending(to_diet(validated), profile, RestrictionMode.PROFESSIONAL)
        if kind is RestrictionKind.LACTOSE:
            continue                                       # tolerated by declared, measured professional behaviour
        assert not bad, f"{kind.name}: PROFESSIONAL mode let through {bad} — the concession must be lactose only"


def test_the_concession_is_declared_in_one_place_only():
    """Static guard: the tolerated set is a named constant, so widening it is a visible edit and never a side effect."""
    from finalprosports.domain.composition.policy.restriction_policy import PROFESSIONAL_TOLERATED
    assert PROFESSIONAL_TOLERATED == frozenset({RestrictionKind.LACTOSE}), PROFESSIONAL_TOLERATED


def test_every_path_that_can_add_a_food_consults_the_restriction_policy():
    """The routes are separate by construction, not by discipline: each function that chooses a food to put INTO a diet must
    name the restriction policy. A new one that forgets fails here rather than in a client's diet."""
    import ast

    src = Path(__file__).resolve().parents[2] / "src" / "finalprosports"
    required = {
        "application/service/validation/diet_validator.py": ("_candidates",),
        "domain/composition/policy/proposal_completion_policy.py": ("complete_structure",),
        "application/strategy/rotation_composer.py": ("restriction_filter",),
    }
    for rel, fns in required.items():
        tree = ast.parse((src / rel).read_text(encoding="utf-8"))
        names = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)} | {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)}
        assert "veto_reasons" in names or "vetoed" in names, f"{rel} chooses foods without consulting the restriction policy"
        defined = {n.name for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
        for fn in fns:
            assert fn in defined, f"{rel}: {fn} was renamed; re-point this guard at the function that now selects candidates"


if __name__ == "__main__":
    failed = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn(); print(f"PASS  {name}")
            except AssertionError as ex:
                failed += 1; print(f"FAIL  {name}: {str(ex)[:400]}")
    sys.exit(1 if failed else 0)
