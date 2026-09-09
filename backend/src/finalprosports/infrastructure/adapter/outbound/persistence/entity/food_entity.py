from sqlalchemy import ARRAY, Boolean, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base

FLAGS = ("is_processed_sugar", "is_soft_drink", "is_salt", "is_fasting_compatible", "is_alcohol", "is_stimulant", "is_peanut", "is_tree_nut",
         "contains_lactose", "contains_gluten", "contains_soy", "contains_shellfish", "contains_egg", "contains_fish")


class FoodEntity(Base):
    __tablename__ = "foods"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    professional_id: Mapped[str] = mapped_column(Text, primary_key=True)
    canonical_name: Mapped[str] = mapped_column(Text, nullable=False)
    family: Mapped[str] = mapped_column(Text, nullable=False)
    food_group: Mapped[str] = mapped_column(Text, nullable=False)
    secondary_group: Mapped[str | None] = mapped_column(Text)
    frequency: Mapped[int] = mapped_column(Integer, nullable=False)
    synonyms: Mapped[list[str]] = mapped_column(ARRAY(Text), default=list)
    keys: Mapped[list[str]] = mapped_column(ARRAY(Text), default=list)
    created_by_professional: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


for _flag in FLAGS:
    setattr(FoodEntity, _flag, mapped_column(_flag, Boolean, nullable=False, default=False))
