from finalprosports.infrastructure.config.security import current_professional_id_or_raise


class RequestScopedProfessionalAdapter:
    """CurrentProfessionalOutputPort: the professional resolved from the validated token of THIS request.

    It holds no state and has no default. Outside a request that authenticated, reading it raises
    (`ProfessionalContextNotBound`) instead of returning a professional — the v1 adapter that answered
    with a configured id no longer exists in the tree, on purpose: an adapter that hands out a tenant
    with no token is an authentication bypass waiting for a code path that forgets the dependency.
    """

    def current_professional_id(self) -> str:
        return current_professional_id_or_raise()
