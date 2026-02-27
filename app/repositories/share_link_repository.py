from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.share_link import ShareLink


class ShareLinkRepository:
    def __init__(self, db: AsyncSession):
        self._db = db

    async def get_by_token(self, token: str) -> ShareLink | None:
        result = await self._db.execute(
            select(ShareLink)
            .where(ShareLink.id == token)
            .options(selectinload(ShareLink.character))
        )
        return result.scalar_one_or_none()

    async def get_for_character(self, character_id: UUID) -> list[ShareLink]:
        result = await self._db.execute(
            select(ShareLink)
            .where(ShareLink.character_id == character_id)
            .order_by(ShareLink.created_at.desc())
        )
        return list(result.scalars().all())

    async def create(
        self,
        character_id: UUID,
        label: str | None,
        expires_at: datetime | None,
    ) -> ShareLink:
        link = ShareLink(
            character_id=character_id,
            label=label,
            expires_at=expires_at,
        )
        self._db.add(link)
        await self._db.flush()
        return link

    async def revoke(self, token: str) -> None:
        result = await self._db.execute(
            select(ShareLink).where(ShareLink.id == token)
        )
        link = result.scalar_one_or_none()
        if link:
            link.is_active = False
            await self._db.flush()

    async def delete(self, token: str) -> None:
        result = await self._db.execute(
            select(ShareLink).where(ShareLink.id == token)
        )
        link = result.scalar_one_or_none()
        if link:
            await self._db.delete(link)
            await self._db.flush()
