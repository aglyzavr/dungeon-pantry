"""Handler for user settings."""
from datetime import timedelta
from uuid import UUID

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database import get_db
from app.i18n import render_template
from app.middleware.auth import SESSION_COOKIE_NAME, require_login
from app.schemas.auth import UserSession
from app.repositories.user_repository import UserRepository
from app.services.auth_service import create_session_token

router = APIRouter(prefix="/settings", tags=["Settings"])
templates = Jinja2Templates(directory="app/templates")


@router.get("", response_class=HTMLResponse)
async def settings_page(
    request: Request,
    current_user: UserSession = Depends(require_login),
):
    """Display user settings page."""
    return render_template(
        templates,
        "settings/settings.html",
        {
            "request": request,
            "current_user": current_user,
        },
        language=current_user.language,
    )


@router.post("/language", response_class=HTMLResponse)
async def change_language(
    request: Request,
    language: str = Form(...),
    current_user: UserSession = Depends(require_login),
    db: AsyncSession = Depends(get_db),
):
    """Change user's language preference."""
    # Validate language
    if language not in ("en", "ru"):
        return RedirectResponse(url="/settings", status_code=303)
    
    # Update user in database
    user_repo = UserRepository(db)
    user = await user_repo.get_by_id(UUID(current_user.user_id))
    if not user:
        return RedirectResponse(url="/auth/login", status_code=303)
    
    user.language = language
    await db.commit()
    
    # Create new session token with updated language
    new_token = create_session_token(user)
    settings = get_settings()
    
    # Redirect back to settings with new cookie
    response = RedirectResponse(url="/settings", status_code=303)
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=new_token,
        max_age=int(timedelta(days=settings.session_duration_days).total_seconds()),
        httponly=True,
        samesite="lax",
        secure=False,  # Match auth_handler setting
    )
    
    return response


@router.post("/theme", response_class=HTMLResponse)
async def change_theme(
    request: Request,
    theme: str = Form(...),
    current_user: UserSession = Depends(require_login),
    db: AsyncSession = Depends(get_db),
):
    """Change user's theme preference."""
    # Validate theme
    if theme not in ("light", "dark"):
        return RedirectResponse(url="/settings", status_code=303)
    
    # Update user in database
    user_repo = UserRepository(db)
    user = await user_repo.get_by_id(UUID(current_user.user_id))
    if not user:
        return RedirectResponse(url="/auth/login", status_code=303)
    
    user.theme = theme
    await db.commit()
    
    # Create new session token with updated theme
    new_token = create_session_token(user)
    settings = get_settings()
    
    # Redirect back to settings with new cookie
    response = RedirectResponse(url="/settings", status_code=303)
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=new_token,
        max_age=int(timedelta(days=settings.session_duration_days).total_seconds()),
        httponly=True,
        samesite="lax",
        secure=False,  # Match auth_handler setting
    )
    
    return response
