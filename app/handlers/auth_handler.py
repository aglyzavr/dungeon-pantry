from datetime import timedelta

from fastapi import APIRouter, Depends, Form, Request, Response, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database import get_db
from app.middleware.auth import SESSION_COOKIE_NAME, get_current_user
from app.schemas.auth import UserSession
from app.services.auth_service import authenticate_user, create_session_token

router = APIRouter(tags=["Auth"])
templates = Jinja2Templates(directory="app/templates")


@router.get("/login", response_class=HTMLResponse)
async def login_page(
    request: Request,
    user: UserSession | None = Depends(get_current_user),
):
    """Show login page. Redirect to home if already logged in."""
    if user:
        return RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)
    return templates.TemplateResponse(
        "auth/login.html", {"request": request, "error": None}
    )


@router.post("/login", response_class=HTMLResponse)
async def login_submit(
    request: Request,
    response: Response,
    username: str = Form(...),
    password: str = Form(...),
    db: AsyncSession = Depends(get_db),
):
    """Process login form. Set session cookie on success."""
    session = await authenticate_user(db, username, password)

    if session is None:
        # Generic error message — never reveal whether username or password was wrong
        return templates.TemplateResponse(
            "auth/login.html",
            {"request": request, "error": "Invalid username or password"},
            status_code=status.HTTP_401_UNAUTHORIZED,
        )

    token = create_session_token(session)
    settings = get_settings()

    redirect = RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)
    redirect.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=token,
        max_age=int(timedelta(days=settings.session_duration_days).total_seconds()),
        httponly=True,   # not accessible from JavaScript — prevents XSS token theft
        samesite="lax",  # CSRF protection for a local app
        secure=False,    # set to True if you ever add HTTPS to the NAS
    )
    return redirect


@router.post("/logout")
async def logout():
    """Clear the session cookie and redirect to login."""
    response = RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)
    response.delete_cookie(SESSION_COOKIE_NAME)
    return response
