from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from app.config import get_settings


class Base(DeclarativeBase):
    """
    Base class for all SQLAlchemy ORM models.
    All models in app/models/ will inherit from this.
    """
    pass


def create_engine_and_session():
    settings = get_settings()

    engine = create_async_engine(
        settings.database_url,
        echo=settings.is_development,  # logs all SQL in dev, silent in prod
        pool_size=10,
        max_overflow=5,
        pool_pre_ping=True,  # detects stale connections before using them
    )

    session_factory = async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False,  # avoids lazy-load errors after commit
    )

    return engine, session_factory


engine, async_session_factory = create_engine_and_session()


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    FastAPI dependency that yields a database session per request
    and guarantees it is closed even if an exception occurs.
    Usage: db: AsyncSession = Depends(get_db)
    """
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
