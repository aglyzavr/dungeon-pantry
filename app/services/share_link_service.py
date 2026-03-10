from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.share_link import ShareLink
from app.repositories.share_link_repository import ShareLinkRepository


class ShareLinkNotFound(Exception):
    pass


class ShareLinkExpired(Exception):
    pass


class ShareLinkService:
    def __init__(self, db: AsyncSession):
        self._repo = ShareLinkRepository(db)

    async def get_valid_link(self, token: str) -> ShareLink:
        link = await self._repo.get_by_token(token)
        if link is None:
            raise ShareLinkNotFound("Share link not found")
        if not link.is_valid:
            raise ShareLinkExpired("This share link has expired or been revoked")
        return link

    async def list_for_character(self, character_id: UUID) -> list[ShareLink]:
        return await self._repo.get_for_character(character_id)

    async def create_link(
        self,
        character_id: UUID,
        label: str | None = None,
        expires_days: int | None = None,
    ) -> ShareLink:
        expires_at = None
        if expires_days:
            expires_at = datetime.now(timezone.utc) + timedelta(days=expires_days)
        return await self._repo.create(
            character_id=character_id,
            label=label,
            expires_at=expires_at,
        )

    async def revoke_link(self, token: str, expected_character_id: UUID) -> None:
        link = await self._repo.get_by_token(token)
        if link is None:
            raise ShareLinkNotFound("Share link not found")
        if str(link.character_id) != str(expected_character_id):
            raise ShareLinkNotFound("Share link does not belong to this character")
        await self._repo.revoke(token)

    async def delete_link(self, token: str, expected_character_id: UUID) -> None:
        link = await self._repo.get_by_token(token)
        if link is None:
            raise ShareLinkNotFound("Share link not found")
        if str(link.character_id) != str(expected_character_id):
            raise ShareLinkNotFound("Share link does not belong to this character")
        await self._repo.delete(token)
