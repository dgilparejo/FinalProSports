"""SQLAlchemy entities mirror db/schema.sql (the migrations are the source of truth; entities are read/write views)."""
from pgvector.sqlalchemy import Vector
from sqlalchemy import ARRAY, Boolean, ForeignKeyConstraint, Integer, Numeric, SmallInteger, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class DietEntity(Base):
    __tablename__ = "diets"
    id: Mapped[str] = mapped_column(Text, primary_key=True)
    professional_id: Mapped[str] = mapped_column(Text, primary_key=True)
    client_code: Mapped[str] = mapped_column(Text, nullable=False)
    goal: Mapped[str] = mapped_column(Text, nullable=False)
    goals: Mapped[list[str]] = mapped_column(ARRAY(Text), default=list)
    goal_inferred: Mapped[bool] = mapped_column(Boolean, nullable=False)
    goal_text: Mapped[str | None] = mapped_column(Text)
    diet_version: Mapped[int | None] = mapped_column(SmallInteger)
    template_group_id: Mapped[str | None] = mapped_column(Text)
    shared_diet: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    notes: Mapped[list[str]] = mapped_column(ARRAY(Text), default=list)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    embedding = mapped_column(Vector(768))


class DietItemEntity(Base):
    __tablename__ = "diet_items"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    professional_id: Mapped[str] = mapped_column(Text, nullable=False)
    diet_id: Mapped[str] = mapped_column(Text, nullable=False)
    meal_slot: Mapped[str] = mapped_column(Text, nullable=False)
    position: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    component_index: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    food_id: Mapped[int | None] = mapped_column(Integer)
    normalized_key: Mapped[str] = mapped_column(Text, nullable=False)
    raw_text: Mapped[str] = mapped_column(Text, nullable=False)
    food_text: Mapped[str] = mapped_column(Text, nullable=False)
    quantity = mapped_column(Numeric(10, 2))
    unit: Mapped[str] = mapped_column(Text, nullable=False)
    raw_unit: Mapped[str | None] = mapped_column(Text)
    alternative_group: Mapped[str | None] = mapped_column(Text)
    compound_group: Mapped[str | None] = mapped_column(Text)
    unmapped: Mapped[bool] = mapped_column(Boolean, nullable=False)
    unmapped_reason: Mapped[str | None] = mapped_column(Text)
    generic_assumption: Mapped[bool] = mapped_column(Boolean, nullable=False)
    note: Mapped[str | None] = mapped_column(Text)
    __table_args__ = (ForeignKeyConstraint(["professional_id", "diet_id"], ["diets.professional_id", "diets.id"], ondelete="CASCADE"),)
