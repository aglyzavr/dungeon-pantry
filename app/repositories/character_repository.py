import copy
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

from app.models.character import Character


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
            select(Character).where(Character.id == character_id)
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
