import json

from sqlalchemy import text


class GapLogAdapter:
    """GapLogOutputPort: appends to the gaps table."""

    def __init__(self, session_factory):
        self._sf = session_factory

    def log(self, professional_id: str, kind: str, payload: dict) -> None:
        with self._sf() as s:
            s.execute(text("INSERT INTO gaps (professional_id, kind, payload) VALUES (:pid, :kind, CAST(:payload AS jsonb))"),
                      {"pid": professional_id, "kind": kind, "payload": json.dumps(payload, ensure_ascii=False, default=str)})
            s.commit()
