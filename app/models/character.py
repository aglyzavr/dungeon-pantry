import uuid
from typing import Any

from sqlalchemy import ForeignKey, Table, Column
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.base import TimestampMixin, UUIDMixin

# Many-to-many association table (no ORM class needed — it's a pure join table)
campaign_characters = Table(
    "campaign_characters",
    Base.metadata,
    Column("campaign_id", UUID(as_uuid=True),
           ForeignKey("campaigns.id", ondelete="CASCADE"), primary_key=True),
    Column("character_id", UUID(as_uuid=True),
           ForeignKey("characters.id", ondelete="CASCADE"), primary_key=True),
)


class Character(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "characters"

    owner_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    # Full D&D 2024 character sheet stored as JSONB.
    # The CharacterSheet Pydantic schema (added in Step 3) is the source of truth
    # for what lives inside this blob.
    sheet_data: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)

    # Relationships
    owner: Mapped["User"] = relationship("User", back_populates="characters")
    campaigns: Mapped[list["Campaign"]] = relationship(
        "Campaign",
        secondary="campaign_characters",
        back_populates="characters",
        lazy="select",
    )
    share: Mapped["CharacterShare | None"] = relationship(
        "CharacterShare", back_populates="character",
        uselist=False, cascade="all, delete-orphan"
    )
