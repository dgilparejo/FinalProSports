from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class ApiErrorResponse:
    code: str
    message: str

    def to_dict(self) -> dict:
        return asdict(self)
