import copy
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified
from sqlalchemy.orm import selectinload

from app.models.character import Character, CampaignCharacter


class CharacterRepository:
    def __init__(self, db: AsyncSession):
        self._db = db

    async def get_all(self) -> list[Character]:
        result = await self._db.execute(
            select(Character).order_by(Character.created_at.desc())
        )
        return list(result.scalars().all())

    async def get_by_owner(self, owner_id: UUID) -> list[Character]:
        result = await self._db.execute(
            select(Character)
            .where(Character.owner_id == owner_id)
            .order_by(Character.created_at.desc())
        )
        return list(result.scalars().all())

    async def get_by_id(self, character_id: UUID) -> Character | None:
        result = await self._db.execute(
            select(Character)
            .where(Character.id == character_id)
            .options(selectinload(Character.campaign_associations).selectinload(CampaignCharacter.campaign))
        )
        return result.scalar_one_or_none()

    async def create(self, owner_id: UUID, sheet_data: dict) -> Character:
        character = Character(owner_id=owner_id, sheet_data=sheet_data)
        self._db.add(character)
        await self._db.flush()
        return character

    async def save_sheet_data(self, character: Character, new_data: dict) -> Character:
        """
        Replaces sheet_data entirely and forces SQLAlchemy to detect
        the JSONB mutation — required because dict mutation in-place
        is invisible to SQLAlchemy's change tracking.
        """
        character.sheet_data = new_data
        flag_modified(character, "sheet_data")
        await self._db.flush()
        return character

    async def delete(self, character: Character) -> None:
        await self._db.delete(character)
        await self._db.flush()

    # ── Per-campaign character data ────────────────────────────────────────────

    async def get_campaign_character(
        self, campaign_id: UUID, character_id: UUID
    ) -> CampaignCharacter | None:
        """Fetch the CampaignCharacter association for a specific campaign/character pair."""
        result = await self._db.execute(
            select(CampaignCharacter)
            .where(CampaignCharacter.campaign_id == campaign_id)
            .where(CampaignCharacter.character_id == character_id)
        )
        return result.scalar_one_or_none()

    async def update_campaign_character_sheet(
        self, campaign_id: UUID, character_id: UUID, sheet_data: dict
    ) -> CampaignCharacter:
        """Update the sheet_data for a campaign-specific character instance."""
        cc = await self.get_campaign_character(campaign_id, character_id)
        if cc is None:
            raise ValueError(
                f"CampaignCharacter not found for campaign {campaign_id}, character {character_id}"
            )
        cc.sheet_data = sheet_data
        flag_modified(cc, "sheet_data")
        await self._db.flush()
        return cc

    async def update_campaign_character_portrait(
        self,
        campaign_id: UUID,
        character_id: UUID,
        portrait_data: bytes | None,
        mime_type: str | None,
    ) -> CampaignCharacter:
        """Update portrait_data and mime_type for a campaign-specific character instance."""
        cc = await self.get_campaign_character(campaign_id, character_id)
        if cc is None:
            raise ValueError(
                f"CampaignCharacter not found for campaign {campaign_id}, character {character_id}"
            )
        cc.portrait_data = portrait_data
        cc.portrait_mime_type = mime_type
        await self._db.flush()
        return cc

    async def flush(self) -> None:
        """Flush pending changes to the database without committing."""
        await self._db.flush()

    async def update_owner(self, character_id: UUID, owner_id: UUID | None) -> None:
        """Directly update the owner of a character."""
        character = await self.get_by_id(character_id)
        if character is None:
            raise ValueError(f"Character {character_id} not found")
        character.owner_id = owner_id
        await self._db.flush()
