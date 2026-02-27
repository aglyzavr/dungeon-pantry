from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.campaign import Campaign


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
            # Eagerly load characters so we don't hit N+1 on the detail page
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
        await self._db.flush()
        return campaign

    async def delete(self, campaign: Campaign) -> None:
        await self._db.delete(campaign)
        await self._db.flush()
