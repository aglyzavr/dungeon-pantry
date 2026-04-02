import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, LargeBinary, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.base import UUIDMixin


class CampaignCharacter(UUIDMixin, Base):
    """Association object storing per-campaign character data.
    
    Each CampaignCharacter represents a unique character instance within a campaign.
    The sheet_data, portrait_data, and portrait_mime_type are completely independent
    from those on the base Character — changes in one campaign do not affect others.
    """
    __tablename__ = "campaign_characters"

    campaign_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("campaigns.id", ondelete="CASCADE"),
        nullable=False,
    )
    character_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("characters.id", ondelete="CASCADE"),
        nullable=False,
    )

    # Per-campaign snapshot — fully independent from Character.sheet_data
    sheet_data: Mapped[dict] = mapped_column(JSONB, nullable=False)
    portrait_data: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    portrait_mime_type: Mapped[str | None] = mapped_column(nullable=True)

    joined_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    character: Mapped["Character"] = relationship(
        "Character", back_populates="campaign_associations"
    )
    campaign: Mapped["Campaign"] = relationship(
        "Campaign", back_populates="character_associations"
    )

    __table_args__ = (
        UniqueConstraint("campaign_id", "character_id", name="uq_campaign_characters_campaign_character"),
    )


class Character(UUIDMixin, Base):
    __tablename__ = "characters"

    owner_id: Mapped[uuid.UUID | None] = mapped_column(  # ← nullable for unassign
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),      # ← SET NULL on user delete
        nullable=True,
        index=True,
    )
    sheet_data: Mapped[dict] = mapped_column(JSONB, nullable=False)
    portrait_path: Mapped[str | None] = mapped_column(
        nullable=True,  # DEPRECATED: legacy field, use portrait_data instead
    )
    portrait_data: Mapped[bytes | None] = mapped_column(
        LargeBinary, nullable=True  # image data stored in database
    )
    portrait_mime_type: Mapped[str | None] = mapped_column(
        nullable=True  # e.g., "image/png", "image/jpeg"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    owner: Mapped["User | None"] = relationship(
        "User",
        back_populates="characters",
        lazy="selectin",                                   
    )
    campaign_associations: Mapped[list["CampaignCharacter"]] = relationship(
        "CampaignCharacter",
        back_populates="character",
        cascade="all, delete-orphan",
    )
    share_links: Mapped[list["ShareLink"]] = relationship(
        "ShareLink",
        back_populates="character",
        cascade="all, delete-orphan",
        lazy="selectin",                                 
    )
