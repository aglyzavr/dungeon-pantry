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


class PlayerService:
    def __init__(self, db: AsyncSession):
        self._db = db

    async def list_players(self) -> list[User]:
        result = await self._db.execute(
            select(User)
            .where(User.is_dm == False)  # noqa: E712
            .order_by(User.created_at.desc())
        )
        return list(result.scalars().all())

    async def get_player(self, player_id: UUID) -> User:
        result = await self._db.execute(
            select(User).where(
                User.id == player_id,
                User.is_dm == False,  # noqa: E712
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
            hashed_password=hash_password(data.password),
            is_dm=False,
        )
        self._db.add(user)
        await self._db.flush()
        return user

    async def delete_player(self, player_id: UUID) -> None:
        user = await self.get_player(player_id)
        await self._db.delete(user)
        await self._db.flush()

    async def assign_character(
        self, player_id: UUID, character_id: UUID
    ) -> None:
        result = await self._db.execute(
            select(Character).where(Character.id == character_id)
        )
        character = result.scalar_one_or_none()
        if character is None:
            return
        character.owner_id = player_id
        await self._db.flush()

    async def get_all_characters(self) -> list[Character]:
        result = await self._db.execute(
            select(Character).order_by(Character.created_at.desc())
        )
        return list(result.scalars().all())
