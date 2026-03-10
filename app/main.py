import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.exceptions import HTTPException as StarletteHTTPException

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

    from app.middleware.csrf import CSRFMiddleware
    app.add_middleware(CSRFMiddleware)

    app.mount("/static", StaticFiles(directory="app/static", check_dir=False), name="static")
    _register_exception_handlers(app)
    _register_routes(app)
    return app


def _register_exception_handlers(app: FastAPI) -> None:
    from app.i18n import error_response

    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(request: Request, exc: StarletteHTTPException):
        # Let redirects pass through unchanged
        if exc.status_code == 307 and "Location" in (exc.headers or {}):
            return RedirectResponse(
                url=exc.headers["Location"],
                status_code=307,
            )

        # Render HTML error page for browser-facing errors
        language = "en"
        if hasattr(request.state, "current_user_language"):
            language = request.state.current_user_language

        return error_response(
            request,
            exc.status_code,
            error_message=exc.detail if isinstance(exc.detail, str) else None,
            language=language,
        )


def _register_routes(app: FastAPI) -> None:
    from app.handlers.auth_handler import router as auth_router
    from app.handlers.campaign_handler import router as campaign_router
    from app.handlers.character_handler import router as character_router
    from app.handlers.player_handler import router as player_router
    from app.handlers.share_handler import router as share_router
    from app.handlers.settings_handler import router as settings_router

    app.include_router(auth_router)
    app.include_router(campaign_router)
    app.include_router(character_router)
    app.include_router(player_router)
    app.include_router(share_router)
    app.include_router(settings_router)

    @app.get("/health", tags=["System"])
    async def health_check():
        return JSONResponse({"status": "ok", "service": "dnd-campaign-manager"})

    @app.get("/")
    async def root():
        # Root always redirects to campaign list — the real home page
        return RedirectResponse(url="/campaigns")


app = create_app()
