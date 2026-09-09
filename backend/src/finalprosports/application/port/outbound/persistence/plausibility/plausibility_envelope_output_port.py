"""Outbound port: the plausibility envelope mined from the corpus (S2). One implementation today (file produced by the pipeline)."""
from typing import Protocol

from finalprosports.domain.composition.policy.plausibility_policy import PlausibilityEnvelope


class PlausibilityEnvelopeOutputPort(Protocol):
    def load(self, professional_id: str) -> PlausibilityEnvelope | None: ...
