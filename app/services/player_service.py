from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.character import Character
from app.models.user import User
from app.schemas.player import PlayerCreate
from app.services.auth_service import hash_password


class UsernameAlreadyExists(Exception):
    pass


class PlayerNotFound(Exception):
    pass


class CharacterNotFound(Exception):
    pass


class PlayerService:
    def __init__(self, db: AsyncSession):
        self._db = db

    async def list_players(self) -> list[User]:
        result = await self._db.execute(
            select(User)
            .where(User.role == "player")
            .order_by(User.created_at.desc())
        )
        return list(result.scalars().all())

    async def get_player(self, player_id: UUID) -> User:
        result = await self._db.execute(
            select(User).where(
                User.id == player_id,
                User.role == "player",
            )
        )
        user = result.scalar_one_or_none()
        if user is None:
            raise PlayerNotFound(f"Player {player_id} not found")
        return user

    async def create_player(self, data: PlayerCreate) -> User:
        existing = await self._db.execute(
            select(User).where(User.username == data.username)
        )
        if existing.scalar_one_or_none():
            raise UsernameAlreadyExists(
                f"Username '{data.username}' is already taken"
            )
        user = User(
            username=data.username,
            password_hash=hash_password(data.password),
            role="player",
        )
        self._db.add(user)
        await self._db.flush()
        return user

    async def update_password(self, player_id: UUID, new_password: str) -> None:
        user = await self.get_player(player_id)
        user.password_hash = hash_password(new_password)
        await self._db.flush()

    async def delete_player(self, player_id: UUID) -> None:
        user = await self.get_player(player_id)
        await self._db.delete(user)
        await self._db.flush()

    async def assign_character(
        self, player_id: UUID, character_id: UUID | None
    ) -> None:
        # Verify the player exists
        await self.get_player(player_id)

        # Verify the character exists before doing any mutations
        if character_id is not None:
            result = await self._db.execute(
                select(Character).where(Character.id == character_id)
            )
            new_character = result.scalar_one_or_none()
            if new_character is None:
                raise CharacterNotFound(f"Character {character_id} not found")

        # Unassign any character currently owned by this player
        result = await self._db.execute(
            select(Character).where(Character.owner_id == player_id)
        )
        for character in result.scalars().all():
            character.owner_id = None

        # Assign the new character
        if character_id is not None:
            new_character.owner_id = player_id

        await self._db.flush()

    async def get_all_characters(self) -> list[Character]:
        result = await self._db.execute(
            select(Character).order_by(Character.created_at.desc())
        )
        return list(result.scalars().all())
