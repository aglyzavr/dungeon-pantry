from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User


class UserRepository:
    def __init__(self, db: AsyncSession):
        self._db = db

    async def get_by_username(self, username: str) -> User | None:
        result = await self._db.execute(
            select(User).where(User.username == username)
        )
        return result.scalar_one_or_none()

    async def get_by_id(self, user_id: UUID) -> User | None:
        result = await self._db.execute(
            select(User).where(User.id == user_id)
        )
        return result.scalar_one_or_none()

    async def exists_any_dm(self) -> bool:
        result = await self._db.execute(
            select(User).where(User.role == "dm")
        )
        return result.scalar_one_or_none() is not None

    async def create(
        self,
        username: str,
        hashed_password: str,
        is_dm: bool = False,
    ) -> User:
        user = User(
            username=username,
            hashed_password=hashed_password,
            is_dm=is_dm,
        )
        self._db.add(user)
        await self._db.flush()
        return user
