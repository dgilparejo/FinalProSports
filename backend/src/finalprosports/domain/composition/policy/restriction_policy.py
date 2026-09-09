"""Profile restrictions have maximum priority over any general rule (constitution policy `respetar_intolerancias_alergias`).

Two modes (RestrictionMode, selected by configuration and both measured):
  STRICT        every food carrying a restricted flag is vetoed.
  PROFESSIONAL  reproduces the professional's observed behaviour (rule `no_restringe_lacteos_intolerantes`, section 8): lactose is
                NOT vetoed for lactose-intolerant clients — it becomes a warning — while every other restriction stays a veto.
A restriction declared as non-strict by the caller only warns in either mode.
"""
from finalprosports.domain.model import ClientProfile, Food, RestrictionKind, RestrictionMode

PROFESSIONAL_TOLERATED = frozenset({RestrictionKind.LACTOSE})


def _is_veto(kind: RestrictionKind, strict: bool, mode: RestrictionMode) -> bool:
    if not strict:
        return False
    if mode is RestrictionMode.PROFESSIONAL and kind in PROFESSIONAL_TOLERATED:
        return False
    return True


def vetoed(food: Food, profile: ClientProfile, mode: RestrictionMode = RestrictionMode.STRICT) -> bool:
    return any(getattr(food.flags, r.kind.value, False) and _is_veto(r.kind, r.strict, mode) for r in profile.restrictions)


def veto_reasons(food: Food, profile: ClientProfile, mode: RestrictionMode = RestrictionMode.STRICT) -> tuple[str, ...]:
    return tuple(f"restriction:{r.kind.value}" for r in profile.restrictions if getattr(food.flags, r.kind.value, False) and _is_veto(r.kind, r.strict, mode))


def warnings(food: Food, profile: ClientProfile, mode: RestrictionMode = RestrictionMode.STRICT) -> tuple[str, ...]:
    """Restricted flags present in the food that are tolerated (non-strict, or lactose in PROFESSIONAL mode)."""
    return tuple(f"{r.kind.value}:{food.canonical_name}" for r in profile.restrictions
                 if getattr(food.flags, r.kind.value, False) and not _is_veto(r.kind, r.strict, mode))
