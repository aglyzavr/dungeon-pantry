import copy
from uuid import UUID
from datetime import datetime, timezone

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.campaign import Campaign
from app.models.character import Character, CampaignCharacter


class CampaignRepository:
    def __init__(self, db: AsyncSession):
        self._db = db

    async def get_all(self) -> list[Campaign]:
        result = await self._db.execute(
            select(Campaign).order_by(Campaign.created_at.desc())
        )
        return list(result.scalars().all())

    async def get_for_user(self, user_id: UUID, is_dm: bool) -> list[Campaign]:
        """Return campaigns visible to *user_id*.

        Dungeon masters see every campaign. Players only see campaigns in which
        they have at least one character assigned. A join is performed through
        the association table to avoid loading unrelated campaigns.
        """
        if is_dm:
            return await self.get_all()

        # non-dm: join through characters owned by the user
        result = await self._db.execute(
            select(Campaign)
            .join(CampaignCharacter, Campaign.id == CampaignCharacter.campaign_id)
            .join(Character, CampaignCharacter.character_id == Character.id)
            .where(Character.owner_id == user_id)
            .order_by(Campaign.created_at.desc())
            .distinct()
        )
        return list(result.scalars().all())

    async def get_by_id(self, campaign_id: UUID) -> Campaign | None:
        result = await self._db.execute(
            select(Campaign)
            .where(Campaign.id == campaign_id)
            .options(selectinload(Campaign.character_associations).selectinload(CampaignCharacter.character))
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

    async def get_unassigned_characters(self) -> list[Character]:
        """Return all available characters (can be added to multiple campaigns).
        
        This returns ALL characters, allowing the same character to be assigned
        to multiple campaigns with independent data per campaign.
        """
        result = await self._db.execute(
            select(Character)
            .order_by(Character.created_at.desc())
        )
        return list(result.scalars().all())
    
    async def get_characters_not_in_campaign(self, campaign_id: UUID) -> list[Character]:
        """Return characters not already assigned to a specific campaign.
        
        Useful for filtering out duplicates within a single campaign,
        while still allowing the same character in other campaigns.
        """
        already_assigned = select(CampaignCharacter.character_id).where(
            CampaignCharacter.campaign_id == campaign_id
        )
        result = await self._db.execute(
            select(Character)
            .where(Character.id.not_in(already_assigned))
            .order_by(Character.created_at.desc())
        )
        return list(result.scalars().all())

    async def assign_character(
        self, campaign_id: UUID, character_id: UUID, sheet_data: dict
    ) -> CampaignCharacter:
        """Create a CampaignCharacter association with initial sheet_data.
        
        The caller is responsible for providing sheet_data (typically copied from
        the base Character's sheet_data).
        """
        campaign_char = CampaignCharacter(
            campaign_id=campaign_id,
            character_id=character_id,
            sheet_data=sheet_data,
        )
        self._db.add(campaign_char)
        await self._db.flush()
        return campaign_char

    async def remove_character(self, campaign_id: UUID, character_id: UUID) -> None:
        """Remove a character from a campaign by deleting its CampaignCharacter association."""
        await self._db.execute(
            delete(CampaignCharacter).where(
                CampaignCharacter.campaign_id == campaign_id,
                CampaignCharacter.character_id == character_id,
            )
        )
        await self._db.flush()

    async def remove_character_from_all(self, character_id: UUID) -> None:
        """Remove a character from every campaign it belongs to."""
        await self._db.execute(
            delete(CampaignCharacter).where(
                CampaignCharacter.character_id == character_id,
            )
        )
        await self._db.flush()

    async def get_campaign_character_with_association(
        self, campaign_id: UUID, character_id: UUID
    ) -> CampaignCharacter | None:
        """Get a CampaignCharacter with eager-loaded Character and Campaign.
        
        Used for campaign-specific character views where we need both the
        base Character data and the campaign-specific sheet_data.
        """
        result = await self._db.execute(
            select(CampaignCharacter)
            .where(
                CampaignCharacter.campaign_id == campaign_id,
                CampaignCharacter.character_id == character_id,
            )
            .options(
                selectinload(CampaignCharacter.character),
                selectinload(CampaignCharacter.campaign),
            )
        )
        return result.scalar_one_or_none()