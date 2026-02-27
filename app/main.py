import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.config import get_settings
from app.database import engine

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Startup and shutdown logic.
    - Startup: verify DB connection, log confirmation.
    - Shutdown: cleanly dispose of the connection pool.
    """
    settings = get_settings()
    logger.info("🚀 Starting DnD Campaign Manager [env=%s]", settings.app_env)

    # Verify DB is reachable at startup (fail fast)
    try:
        async with engine.connect() as conn:
            await conn.execute(__import__("sqlalchemy").text("SELECT 1"))
        logger.info("✅ PostgreSQL connection verified")
    except Exception as e:
        logger.critical("❌ Cannot connect to database: %s", e)
        raise

    yield  # application is running

    await engine.dispose()
    logger.info("🛑 Database connections closed. Goodbye.")


def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(
        title="DnD Campaign Manager",
        version="0.1.0",
        # Disable auto-generated /docs in production
        docs_url="/docs" if settings.is_development else None,
        redoc_url="/redoc" if settings.is_development else None,
        lifespan=lifespan,
    )

    # Static files (Tailwind CSS output, etc.)
    app.mount("/static", StaticFiles(directory="app/static", check_dir=False), name="static")

    # Register routers here as we build them in future steps
    _register_routes(app)

    return app


def _register_routes(app: FastAPI) -> None:
    from fastapi import Request
    from fastapi.responses import JSONResponse

    @app.get("/health", tags=["System"])
    async def health_check():
        """Liveness probe — used by NAS uptime monitors and Docker healthcheck."""
        return JSONResponse({"status": "ok", "service": "dnd-campaign-manager"})


app = create_app()
