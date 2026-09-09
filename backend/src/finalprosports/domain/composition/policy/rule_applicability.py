"""Which rules apply to a profile (goal / sex / phase conditions) and whether they are active.

Active = status KEPT and `enabled`. The 19 kept rules with high/medium confidence are enabled by default; low-confidence
rules (kept, retired or descriptive) are implemented but disabled unless the configuration enables them
(Settings.enable_low_confidence_rules) so that their contribution can be measured separately.
"""
from finalprosports.domain.model import ClientProfile, Rule, RuleConfidence, RuleScope, RuleStatus


def phase_of(diet_version: int | None) -> str | None:
    """Phase labels used by the phase-conditioned rules: v1 | v2-4 | v5+."""
    if diet_version is None:
        return None
    return "v1" if diet_version <= 1 else "v2-4" if diet_version <= 4 else "v5+"


def is_active(rule: Rule) -> bool:
    """`enabled` already encodes the default (kept & high/medium) and the low-confidence switch; policy rules never apply."""
    return rule.enabled and rule.status is not RuleStatus.POLICY


def applies(rule: Rule, profile: ClientProfile, phase: str | None = None) -> bool:
    if not is_active(rule):
        return False
    if rule.scope in (RuleScope.GLOBAL, RuleScope.PLACEMENT, RuleScope.AVOID_PLACEMENT):
        return True
    if rule.scope is RuleScope.GOAL:
        return profile.goal is not None and profile.goal.value in rule.condition
    if rule.scope is RuleScope.SEX:
        return profile.sex is not None and profile.sex in rule.condition
    if rule.scope is RuleScope.PHASE:
        return phase is not None and phase in rule.condition
    if rule.scope is RuleScope.BEHAVIOUR:
        return profile.has_intolerances
    return False


def with_low_confidence_enabled(rules: tuple[Rule, ...], enabled: bool) -> tuple[Rule, ...]:
    """Configuration switch: enable (or keep disabled) every low-confidence rule, whatever its status."""
    from dataclasses import replace
    return tuple(replace(r, enabled=enabled) if r.confidence is RuleConfidence.LOW else r for r in rules)
