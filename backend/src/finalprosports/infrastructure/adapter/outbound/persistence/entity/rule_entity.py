from sqlalchemy import ARRAY, Boolean, Integer, Numeric, Text
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class RuleEntity(Base):
    __tablename__ = "rules"
    id: Mapped[str] = mapped_column(Text, primary_key=True)
    professional_id: Mapped[str] = mapped_column(Text, primary_key=True)
    section: Mapped[str] = mapped_column(Text, nullable=False)
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    statement: Mapped[str] = mapped_column(Text, nullable=False)
    condition: Mapped[list[str]] = mapped_column(ARRAY(Text), default=list)
    n_group: Mapped[int | None] = mapped_column(Integer)
    n_support: Mapped[int | None] = mapped_column(Integer)
    prevalence_in_group = mapped_column(Numeric(6, 4))
    lift = mapped_column(Numeric(8, 2))
    adjusted = mapped_column(Numeric(8, 2))
    confidence: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    evaluation_level: Mapped[str] = mapped_column(Text, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    nature: Mapped[str | None] = mapped_column(Text)          # prescriptive | descriptive (0009)
