# app/services/auth_service.py
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models.user import User
from app.repositories.user_repository import UserRepository
from app.schemas.auth import UserSession


class InvalidCredentials(Exception):
    pass


def hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode(), bcrypt.gensalt()).decode()


def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode(), hashed.encode())

def create_session_token(user: User) -> str:
    settings = get_settings()
    payload = {
        "sub": str(user.id),
        "username": user.username,
        "is_dm": user.is_dm,
        "language": user.language,
        "theme": user.theme,
        "exp": datetime.now(timezone.utc) + timedelta(days=7),
    }
    return jwt.encode(payload, settings.session_secret_key, algorithm="HS256")  # ← fix


def decode_session_token(token: str) -> UserSession | None:
    settings = get_settings()
    try:
        payload = jwt.decode(token, settings.session_secret_key, algorithms=["HS256"])  # ← fix
        return UserSession(
            user_id=payload["sub"],
            username=payload["username"],
            is_dm=payload.get("is_dm", False),
            language=payload.get("language", "en"),
            theme=payload.get("theme", "light"),
        )
    except jwt.PyJWTError:
        return None


async def authenticate_user(
    db: AsyncSession, username: str, password: str
) -> User:
    repo = UserRepository(db)
    user = await repo.get_by_username(username)
    if user is None or not verify_password(password, user.password_hash):  # ← fix
        raise InvalidCredentials("Invalid username or password")
    return user


async def seed_dm_user(db: AsyncSession) -> None:
    settings = get_settings()
    repo = UserRepository(db)

    if await repo.exists_any_dm():
        return

    # the settings object exposes dm_seed_username/password
    await repo.create(
        username=settings.dm_seed_username,
        password_hash=hash_password(settings.dm_seed_password or ""),
        is_dm=True,
    )
    await db.commit()
