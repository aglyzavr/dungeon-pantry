from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.campaign import Campaign
from app.models.character import Character
from app.repositories.campaign_repository import CampaignRepository
from app.schemas.campaign import CampaignCreate, CampaignUpdate


class CampaignNotFound(Exception):
    pass


class CharacterNotFound(Exception):
    pass


class CampaignService:
    def __init__(self, db: AsyncSession):
        self._db = db
        self._repo = CampaignRepository(db)

    async def list_campaigns(
        self, *, user_id: UUID | None = None, is_dm: bool = False
    ) -> list[Campaign]:
        """Return campaigns visible to the given user.

        - If *is_dm* is True we ignore *user_id* and return every campaign.
        - Otherwise a user_id must be provided and we ask the repository to
          restrict to campaigns where the user's characters are assigned.
        """
        if user_id is None or is_dm:
            # passing ``None`` covers callers that still invoke the old API; the
            # repository method will simply return all campaigns in the DM case.
            return await self._repo.get_all()

        return await self._repo.get_for_user(user_id, is_dm)

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

    async def get_unassigned_characters(self) -> list[Character]:
        """Return all available characters for assignment to campaigns.
        
        Characters can be assigned to multiple campaigns with independent data,
        so this returns ALL characters (not just those without any campaign).
        """
        return await self._repo.get_unassigned_characters()

    async def get_available_characters_for_campaign(self, campaign_id: UUID) -> list[Character]:
        """Return characters not already assigned to a specific campaign.
        
        This filters out characters already in THIS campaign, while still allowing
        them to be shown in other campaigns for multi-campaign assignment.
        """
        campaign = await self._repo.get_by_id(campaign_id)
        if campaign is None:
            raise CampaignNotFound(f"Campaign {campaign_id} not found")
        return await self._repo.get_characters_not_in_campaign(campaign_id)

    async def assign_character(self, campaign_id: UUID, character_id: UUID) -> None:
        """Assign a character to a campaign.
        
        Creates a CampaignCharacter with an independent copy of the character's
        current sheet_data and portrait fields.
        """
        campaign = await self._repo.get_by_id(campaign_id)
        if campaign is None:
            raise CampaignNotFound(f"Campaign {campaign_id} not found")
        result = await self._db.execute(
            select(Character).where(Character.id == character_id)
        )
        character = result.scalar_one_or_none()
        if character is None:
            raise CharacterNotFound(f"Character {character_id} not found")
        
        # Copy the character's current sheet_data as the starting point
        await self._repo.assign_character(campaign_id, character_id, character.sheet_data)

    async def remove_character(self, campaign_id: UUID, character_id: UUID) -> None:
        campaign = await self._repo.get_by_id(campaign_id)
        if campaign is None:
            raise CampaignNotFound(f"Campaign {campaign_id} not found")
        await self._repo.remove_character(campaign_id, character_id)