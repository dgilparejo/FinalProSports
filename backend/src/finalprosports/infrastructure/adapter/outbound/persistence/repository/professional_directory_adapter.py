from sqlalchemy import text


class ProfessionalDirectoryAdapter:
    """Maps a Keycloak subject (`sub`) to the professional it owns. Populated by migration 0011.

    The mapping is looked up on every request. It is a single indexed row read; caching it would
    mean a revoked or re-pointed subject keeping access until the cache expired, which is not a
    trade worth making for a query this cheap.
    """

    def __init__(self, session_factory):
        self._sf = session_factory

    def professional_for_subject(self, subject: str) -> str | None:
        with self._sf() as s:
            row = s.execute(text("SELECT id FROM professionals WHERE keycloak_subject = :sub"), {"sub": subject}).first()
            return row[0] if row else None
