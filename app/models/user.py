from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.base import UUIDMixin


class User(UUIDMixin, Base):
    __tablename__ = "users"

    username: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    role: Mapped[str] = mapped_column(String(10), nullable=False)
    language: Mapped[str] = mapped_column(String(5), nullable=False, server_default="en")
    theme: Mapped[str] = mapped_column(String(10), nullable=False, server_default="light")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=text("NOW()"),
        nullable=False,
    )

    __table_args__ = (
        CheckConstraint("role IN ('dm', 'player')", name="users_role_check"),
        CheckConstraint("language IN ('en', 'ru')", name="users_language_check"),
        CheckConstraint("theme IN ('light', 'dark')", name="users_theme_check"),
    )

    characters: Mapped[list["Character"]] = relationship(
        "Character", back_populates="owner", lazy="select"
    )
    campaigns: Mapped[list["Campaign"]] = relationship(
        "Campaign", back_populates="creator", lazy="select"
    )

    @property
    def is_dm(self) -> bool:
        return self.role == "dm"