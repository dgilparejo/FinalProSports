"""Pydantic DTOs of the clients and saved-diets endpoints (Pydantic lives ONLY in this package).

S9: a client of the portfolio is registered BY NAME, as the professional's intake sheet asks; the key is a UUID the
application assigns and returns as ``id``. Nobody types a code: the ``CLIENTE_NNN`` pseudonyms belong to the case base and the
repository keeps refusing them, but that guard is no longer part of the registration contract."""
from datetime import date

from pydantic import BaseModel, Field

UUID_PATTERN = r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"


class RegisterClientDto(BaseModel):
    """Registration form: identification (as the sheet asks) + what the engine needs. Health is captured as structured restrictions
    (flags of the catalogue), never as free text; the rest of the sheet is filled in the record."""

    full_name: str = Field(min_length=2, max_length=120, description="Name and surname, as the professional's sheet asks", examples=["Nora Ficticia Demo"])
    birth_date: date | None = Field(default=None, description="Age (algorithm input) is derived from it")
    phone: str | None = Field(default=None, max_length=40)
    email: str | None = Field(default=None, max_length=120)
    sex: str | None = Field(default=None, pattern="^[MF]$")
    height_cm: int | None = Field(default=None, ge=120, le=220)
    activity_level: int | None = Field(default=None, ge=1, le=6, description="1 sedentary … 6 professional athlete")
    goal: str | None = Field(default=None, description="volumen_masa | definicion_grasa | ayuno_intermitente | descarga_carga | cetosis_keto | hipocalorica | alta_en_fibra | mantenimiento")
    is_athlete: bool | None = None
    restrictions: list[str] = Field(default_factory=list, description="RestrictionKind values: contains_lactose, contains_gluten, contains_soy, contains_shellfish, contains_egg, contains_fish, is_peanut, is_tree_nut, is_alcohol, is_stimulant")


class ProposeDto(BaseModel):
    """Request of a proposal for an existing client of the portfolio: its id (UUID), the goal (professional's input), optional restrictions override, k cases."""

    client_id: str = Field(pattern=UUID_PATTERN, description="Internal key of the client (the id returned by /clients)")
    goal: str
    restrictions: list[str] | None = Field(default=None, description="If given, replaces the client's stored restrictions for this proposal")
    strict_restrictions: bool = True
    k: int = Field(default=20, ge=1, le=20)
    novelty: str | None = Field(default=None, pattern="^(conservadora|equilibrada|muy_distinta)$",
                                description="Cuánto debe diferenciarse de la dieta anterior del cliente: conservadora (15 %), equilibrada (27,2 %, su tasa medida) o muy_distinta (42,4 %, la que él alcanza al cambiar de objetivo). No afecta a los suplementos, que se arrastran por su propia tasa (17,3 %).")


class SavedProposalDto(BaseModel):
    """A proposal as returned by POST /diets/propose, possibly edited by the professional, sent back to be validated and saved."""

    profile: dict
    strategy: str = "edited"
    parameters: dict = Field(default_factory=dict)
    retrieved_case_ids: list[str] = Field(default_factory=list)
    meals: list[dict]
    notes: list[str] = Field(default_factory=list)
    validation: dict | None = None
    edited: bool = True
    original: dict | None = Field(default=None, description="S5: the proposal exactly as POST /diets/propose returned it, to record the professional's edits (diff)")
