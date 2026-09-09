# -*- coding: utf-8 -*-
"""S2 · Golden model diets: 20 profiles (every goal x both sexes x three age brackets, three with hard restrictions, two recurrent),
each proposal (1) must satisfy every plausibility assertion of the domain policy and (2) must match its snapshot.

Plausibility (domain/composition/policy/plausibility_policy.py, limits mined from the corpus):
  no quantity outside [p05, p95] for its food and unit · distinct foods per slot inside the slot band · slot count inside the band
  · no food repeated in a slot · alternatives of one group share the family · zero foods vetoed by the declared restrictions
  · zero enforceable prohibitions violated · goal-conditional rules satisfied · required slot structure (dinner = protein + vegetable)
  · recurrent: novelty vs the previous version inside the professional's renewal band.

Snapshots (tests/golden/snapshots/<profile>.json) freeze strategy, routing, meals (food, quantity, unit per option) and notes. Any change
of the engine fails with a readable diff; accept it consciously with `pytest tests/golden --update-snapshots` (or GOLDEN_UPDATE=1).
Recurrent profiles: the first proposal (cold start) is treated as version e01 and the second one is routed as same goal -> rotation.
"""
from __future__ import annotations

import dataclasses
import difflib
import json

import pytest

from .conftest import SNAPSHOTS_DIR, load_profiles

PROFILES = load_profiles()


def make_profile(spec: dict, pid: str):
    from finalprosports.domain.model import ClientProfile, Goal, Restriction, RestrictionKind
    restrictions = tuple(Restriction(RestrictionKind(r)) for r in spec.get("restrictions", []))
    allergies = any(r.kind.value.startswith("is_") and r.kind.value != "is_alcohol" and r.kind.value != "is_stimulant" for r in restrictions) or \
        any(r.kind in (RestrictionKind.SHELLFISH, RestrictionKind.EGG, RestrictionKind.FISH) for r in restrictions)
    intolerances = any(r.kind in (RestrictionKind.LACTOSE, RestrictionKind.GLUTEN, RestrictionKind.SOY) for r in restrictions)
    return ClientProfile(client_code=f"GOLDEN_{spec['name']}", professional_id=pid, sex=spec["sex"], age=spec["age"], height_cm=spec["height_cm"],
                         activity_level=spec["activity_level"], goal=Goal(spec["goal"]), restrictions=restrictions, has_allergies=allergies, has_intolerances=intolerances)


def snapshot_of(proposal) -> dict:
    return {"strategy": proposal.strategy, "routing": proposal.parameters.get("routing"), "k_effective": proposal.parameters.get("k_effective"),
            "meals": [{"slot": m.slot.value, "groups": [[{"food": o.item.canonical_name, "food_id": o.item.food_id, "quantity": o.item.quantity.value, "unit": o.item.quantity.unit.value}
                                                         for o in g.options] for g in m.groups]} for m in proposal.meals],
            "notes": list(proposal.notes), "forced_changes": [f"{f.slot.value}:{f.canonical_name}:{f.reason}" for f in (proposal.validation.forced_changes if proposal.validation else ())],
            "compliance": proposal.compliance}


def run_case(engine: dict, spec: dict):
    """Returns (proposal, previous) — previous is the synthetic first version for recurrent profiles."""
    from finalprosports.domain.composition.factory.proposal_factory import to_diet
    root, pid = engine["root"], engine["pid"]
    profile = make_profile(spec, pid)
    previous = None
    if spec.get("recurrent"):
        first = root.propose_diet_use_case.propose(pid, profile, k=20, history=())
        previous = dataclasses.replace(to_diet(first, f"{profile.client_code}::e01"), diet_version=1)
        proposal = root.propose_diet_use_case.propose(pid, profile, k=20, history=(previous,))
    else:
        proposal = root.propose_diet_use_case.propose(pid, profile, k=20, history=())
    return proposal, previous


@pytest.mark.parametrize("spec", PROFILES, ids=[p["name"] for p in PROFILES])
def test_golden_profile_is_plausible_and_matches_snapshot(engine, spec, update_snapshots):
    from finalprosports.application.exception.proposal.goal_not_servable_error import GoalNotServableError
    from finalprosports.domain.composition.policy.plausibility_policy import check_plausibility

    # A goal the case base cannot serve must be REFUSED by name, and the refusal is the expected outcome of these
    # profiles -- not a relaxed assertion. On dataset-v3, `mantenimiento` has zero diets in the corpus and
    # `alta_en_fibra` has three, two of them entirely inside the non-composable bucket. Serving either would mean
    # composing a diet out of cases that belong to a different goal, or handing over an empty document.
    if spec.get("expect_goal_not_servable"):
        with pytest.raises(GoalNotServableError) as raised:
            run_case(engine, spec)
        assert raised.value.goal == spec["goal"], raised.value.goal
        return

    proposal, previous = run_case(engine, spec)
    violations = check_plausibility(proposal, engine["envelope"], engine["catalog"], engine["rules"], previous=previous, expected_slots=spec.get("expected_slots"))
    assert not violations, f"perfil {spec['name']}: {len(violations)} violación(es) de plausibilidad\n  " + "\n  ".join(str(v) for v in violations)

    snap = snapshot_of(proposal)
    path = SNAPSHOTS_DIR / f"{spec['name']}.json"
    text = json.dumps(snap, ensure_ascii=False, indent=1, sort_keys=True) + "\n"
    if update_snapshots or not path.exists():
        SNAPSHOTS_DIR.mkdir(exist_ok=True)
        path.write_text(text, encoding="utf-8", newline="\n")
        if not update_snapshots:
            pytest.skip(f"snapshot created: {path.name} (review it, then commit)")
        return
    expected = path.read_text(encoding="utf-8")
    if expected != text:
        diff = "\n".join(difflib.unified_diff(expected.splitlines(), text.splitlines(), f"snapshots/{path.name}", "engine output", lineterm="", n=2))
        pytest.fail(f"perfil {spec['name']}: la salida del motor difiere de la instantánea (revisar y aceptar con --update-snapshots)\n{diff}")


def test_profiles_cover_goals_sexes_ages_restrictions_and_recurrence():
    goals = {p["goal"] for p in PROFILES}
    sexes = {p["sex"] for p in PROFILES}
    brackets = {("<25" if p["age"] < 25 else "25-39" if p["age"] < 40 else "40-54" if p["age"] < 55 else "55+") for p in PROFILES}
    assert len(PROFILES) == 20
    assert len(goals) >= 7 and sexes == {"M", "F"} and len(brackets) >= 3
    assert sum(1 for p in PROFILES if p.get("restrictions")) >= 3
    assert sum(1 for p in PROFILES if p.get("recurrent")) >= 2
