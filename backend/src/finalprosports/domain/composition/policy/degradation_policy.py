"""Degradation when same-goal cases are scarce (E5.6): the gap policy detects, this policy acts.

In the leave-one-out evaluation, the 23 queries of minority goals (alta_en_fibra, hipocalorica, mantenimiento) had fewer than k
same-goal cases among the k retrieved. Measured on them (J normalized_key): composing over the 20 mixed cases 0,327; composing only
over the same-goal cases (reduce_k) 0,315-0,329 depending on the minimum; copying the best same-goal case 0,349. Fewer cases make a
worse consensus, so the default degradation is copy_top1; reduce_k stays implemented and selectable.
  - copy_top1  reproduce the best same-goal case (composition over one case with inclusion threshold 0 yields the case itself,
               alternatives included) — or the best case of any goal if none shares the goal;
  - reduce_k   compose only over the same-goal cases when there are at least `min_cases_to_compose`, else copy_top1;
  - none       no degradation.
This is the same mechanism a v2 fallback would use. Pure function; the mode applied is recorded in the proposal's parameters.
"""
from __future__ import annotations

from dataclasses import replace

from finalprosports.domain.composition.policy.composition_policy import CompositionParams
from finalprosports.domain.model import ClientProfile, RetrievedCase


def _copy(cases, same, params):
    best = same[:1] or cases[:1]
    return best, "copy_top1", replace(params, inclusion_threshold=0.0, slot_threshold=0.0, note_threshold=0.0)


def select_cases(cases: tuple[RetrievedCase, ...], profile: ClientProfile, params: CompositionParams) -> tuple[tuple[RetrievedCase, ...], str, CompositionParams]:
    """Returns (cases to compose over, degradation mode applied, effective params). mode in {'none', 'reduce_k', 'copy_top1'}."""
    used = tuple(cases[: params.k])
    if params.degradation == "none" or profile.goal is None or not used:
        return used, "none", params
    same = tuple(c for c in used if c.diet.goal == profile.goal)
    if len(same) == len(used):
        return used, "none", params
    if params.degradation == "reduce_k" and len(same) >= params.min_cases_to_compose:
        return same, "reduce_k", params
    return _copy(used, same, params)
