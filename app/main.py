import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.config import get_settings
from app.database import async_session_factory, engine
from app.services.auth_service import seed_dm_user

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    logger.info("🚀 Starting DnD Campaign Manager [env=%s]", settings.app_env)

    try:
        async with engine.connect() as conn:
            await conn.execute(__import__("sqlalchemy").text("SELECT 1"))
        logger.info("✅ PostgreSQL connection verified")
    except Exception as e:
        logger.critical("❌ Cannot connect to database: %s", e)
        raise

    # Seed the DM user if none exists
    async with async_session_factory() as db:
        await seed_dm_user(db)

    yield

    await engine.dispose()
    logger.info("🛑 Database connections closed. Goodbye.")


def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(
        title="DnD Campaign Manager",
        version="0.1.0",
        docs_url="/docs" if settings.is_development else None,
        redoc_url="/redoc" if settings.is_development else None,
        lifespan=lifespan,
    )

    app.mount("/static", StaticFiles(directory="app/static", check_dir=False), name="static")

    _register_routes(app)
    return app


def _register_routes(app: FastAPI) -> None:
    from fastapi import Request
    from app.handlers.auth_handler import router as auth_router

    app.include_router(auth_router)

    @app.get("/health", tags=["System"])
    async def health_check():
        return JSONResponse({"status": "ok", "service": "dnd-campaign-manager"})


app = create_app()
