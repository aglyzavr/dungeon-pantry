import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, ForeignKey, LargeBinary, Table
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


campaign_characters = Table(
    "campaign_characters",
    Base.metadata,
    Column(
        "campaign_id",
        UUID(as_uuid=True),
        ForeignKey("campaigns.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column(
        "character_id",
        UUID(as_uuid=True),
        ForeignKey("characters.id", ondelete="CASCADE"),
        primary_key=True,
    ),
)


class Character(Base):
    __tablename__ = "characters"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
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
    campaigns: Mapped[list["Campaign"]] = relationship(
        "Campaign",
        secondary=campaign_characters,
        back_populates="characters",
    )
    share_links: Mapped[list["ShareLink"]] = relationship(
        "ShareLink",
        back_populates="character",
        cascade="all, delete-orphan",
        lazy="selectin",                                 
    )
