from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.campaign import Campaign
from app.models.character import Character
from app.repositories.campaign_repository import CampaignRepository
from app.schemas.campaign import CampaignCreate, CampaignUpdate


class CampaignNotFound(Exception):
    pass


class CampaignService:
    def __init__(self, db: AsyncSession):
        self._repo = CampaignRepository(db)

    async def list_campaigns(self) -> list[Campaign]:
        return await self._repo.get_all()

    async def get_campaign(self, campaign_id: UUID) -> Campaign:
        campaign = await self._repo.get_by_id(campaign_id)
        if campaign is None:
            raise CampaignNotFound(f"Campaign {campaign_id} not found")
        return campaign

    async def create_campaign(self, data: CampaignCreate, created_by: UUID) -> Campaign:
        return await self._repo.create(
            name=data.name, description=data.description, created_by=created_by
        )

    async def update_campaign(self, campaign_id: UUID, data: CampaignUpdate) -> Campaign:
        campaign = await self._repo.get_by_id(campaign_id)
        if campaign is None:
            raise CampaignNotFound(f"Campaign {campaign_id} not found")
        return await self._repo.update(campaign, name=data.name, description=data.description)

    async def delete_campaign(self, campaign_id: UUID) -> None:
        campaign = await self._repo.get_by_id(campaign_id)
        if campaign is None:
            raise CampaignNotFound(f"Campaign {campaign_id} not found")
        await self._repo.delete(campaign)

    async def get_unassigned_characters(self, campaign_id: UUID) -> list[Character]:
        return await self._repo.get_unassigned_characters(campaign_id)

    async def assign_character(self, campaign_id: UUID, character_id: UUID) -> None:
        await self._repo.assign_character(campaign_id, character_id)

    async def remove_character(self, campaign_id: UUID, character_id: UUID) -> None:
        await self._repo.remove_character(campaign_id, character_id)
