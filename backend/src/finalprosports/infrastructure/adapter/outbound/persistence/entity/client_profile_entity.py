from sqlalchemy import ARRAY, Boolean, Integer, SmallInteger, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class ClientProfileEntity(Base):
    __tablename__ = "client_profiles"
    client_code: Mapped[str] = mapped_column(Text, primary_key=True)
    professional_id: Mapped[str] = mapped_column(Text, primary_key=True)
    sex: Mapped[str | None] = mapped_column(String(1))
    age: Mapped[int | None] = mapped_column(SmallInteger)
    age_bucket: Mapped[str | None] = mapped_column(Text)
    height_cm: Mapped[int | None] = mapped_column(SmallInteger)
    activity_level: Mapped[int | None] = mapped_column(SmallInteger)
    activity_level_reported: Mapped[bool] = mapped_column(Boolean, nullable=False)
    is_athlete: Mapped[bool | None] = mapped_column(Boolean)
    goals: Mapped[str | None] = mapped_column(Text)
    sport: Mapped[str | None] = mapped_column(Text)
    corpus_alias: Mapped[str | None] = mapped_column(Text)       # 0014: el seudonimo del corpus, si es la misma persona
    body_type: Mapped[str | None] = mapped_column(Text)          # 0013: rasgo de similitud
    training_time: Mapped[str | None] = mapped_column(Text)      # 0013
    liked_foods: Mapped[str | None] = mapped_column(Text)
    disliked_foods: Mapped[str | None] = mapped_column(Text)
    has_allergies: Mapped[bool] = mapped_column(Boolean, nullable=False)
    has_intolerances: Mapped[bool] = mapped_column(Boolean, nullable=False)
    has_medical_restrictions: Mapped[bool] = mapped_column(Boolean, nullable=False)
    diet_count: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    empty_profile: Mapped[bool] = mapped_column(Boolean, nullable=False)
    unmapped: Mapped[bool] = mapped_column(Boolean, nullable=False)
    suspicious_demographics: Mapped[bool] = mapped_column(Boolean, nullable=False)
    field_carryover_suspected: Mapped[bool] = mapped_column(Boolean, nullable=False)
    restrictions: Mapped[list[str]] = mapped_column(ARRAY(Text), default=list)
    is_corpus_case: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    disliked_food_ids: Mapped[list[int]] = mapped_column(ARRAY(Integer), default=list)
    liked_food_ids: Mapped[list[int] | None] = mapped_column(ARRAY(Integer), nullable=True)   # 0017
    owned_supplement_ids: Mapped[list[int]] = mapped_column(ARRAY(Integer), default=list)
