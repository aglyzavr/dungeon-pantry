import copy
from uuid import UUID
from datetime import datetime, timezone

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.campaign import Campaign
from app.models.character import Character, campaign_characters


class CampaignRepository:
    def __init__(self, db: AsyncSession):
        self._db = db

    async def get_all(self) -> list[Campaign]:
        result = await self._db.execute(
            select(Campaign).order_by(Campaign.created_at.desc())
        )
        return list(result.scalars().all())

    async def get_by_id(self, campaign_id: UUID) -> Campaign | None:
        result = await self._db.execute(
            select(Campaign)
            .where(Campaign.id == campaign_id)
            .options(selectinload(Campaign.characters))
        )
        return result.scalar_one_or_none()

    async def create(self, name: str, description: str | None, created_by: UUID) -> Campaign:
        campaign = Campaign(name=name, description=description, created_by=created_by)
        self._db.add(campaign)
        await self._db.flush()
        return campaign

    async def update(self, campaign: Campaign, name: str, description: str | None) -> Campaign:
        campaign.name = name
        campaign.description = description
        campaign.updated_at = datetime.now(timezone.utc)
        await self._db.flush()
        return campaign

    async def delete(self, campaign: Campaign) -> None:
        await self._db.delete(campaign)
        await self._db.flush()

    # ── Character assignment ──────────────────────────────────────────────────

    async def get_unassigned_characters(self, campaign_id: UUID) -> list[Character]:
        """All characters NOT yet in this campaign."""
        already_in = select(campaign_characters.c.character_id).where(
            campaign_characters.c.campaign_id == campaign_id
        )
        result = await self._db.execute(
            select(Character).where(Character.id.not_in(already_in))
            .order_by(Character.created_at.desc())
        )
        return list(result.scalars().all())

    async def assign_character(self, campaign_id: UUID, character_id: UUID) -> None:
        from sqlalchemy.dialects.postgresql import insert as pg_insert
        stmt = pg_insert(campaign_characters).values(
            campaign_id=campaign_id,
            character_id=character_id,
        ).on_conflict_do_nothing()
        await self._db.execute(stmt)
        await self._db.flush()

    async def remove_character(self, campaign_id: UUID, character_id: UUID) -> None:
        await self._db.execute(
            delete(campaign_characters).where(
                campaign_characters.c.campaign_id == campaign_id,
                campaign_characters.c.character_id == character_id,
            )
        )
        await self._db.flush()
