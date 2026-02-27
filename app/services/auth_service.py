import logging
from datetime import timedelta

import bcrypt
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.repositories.user_repository import UserRepository
from app.schemas.auth import UserSession

logger = logging.getLogger(__name__)


def hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))


def _get_serializer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(
        secret_key=get_settings().session_secret_key,
        salt="session",
    )


def create_session_token(session: UserSession) -> str:
    return _get_serializer().dumps(session.model_dump())


def decode_session_token(token: str) -> UserSession | None:
    settings = get_settings()
    max_age = timedelta(days=settings.session_duration_days).total_seconds()
    try:
        data = _get_serializer().loads(token, max_age=max_age)
        return UserSession(**data)
    except (SignatureExpired, BadSignature):
        return None


async def authenticate_user(
    db: AsyncSession, username: str, password: str
) -> UserSession | None:
    repo = UserRepository(db)
    user = await repo.get_by_username(username)
    if user is None or not verify_password(password, user.password_hash):
        return None
    return UserSession(
        user_id=str(user.id),
        username=user.username,
        role=user.role,
    )


async def seed_dm_user(db: AsyncSession) -> None:
    settings = get_settings()
    repo = UserRepository(db)

    if await repo.exists_any_dm():
        return

    dm_username = getattr(settings, "dm_seed_username", "dm")
    dm_password = getattr(settings, "dm_seed_password", None)

    if not dm_password:
        logger.warning(
            "⚠️  No DM_SEED_PASSWORD set in .env — skipping DM seed."
        )
        return

    await repo.create(
        username=dm_username,
        password_hash=hash_password(dm_password),
        role="dm",
    )
    await db.commit()
    logger.info("✅ DM seed user '%s' created", dm_username)
