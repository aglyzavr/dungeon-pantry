from fastapi import Cookie, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.schemas.auth import UserSession
from app.services.auth_service import decode_session_token

SESSION_COOKIE_NAME = "dnd_session"


def get_current_user(
    request: Request,
    dnd_session: str | None = Cookie(default=None, alias=SESSION_COOKIE_NAME),
) -> UserSession | None:
    """
    Soft auth dependency — returns the current user or None.
    Use this when a route should behave differently for logged-in vs anonymous users.
    """
    if not dnd_session:
        return None
    return decode_session_token(dnd_session)


def require_login(
    user: UserSession | None = Depends(get_current_user),
) -> UserSession:
    """
    Hard auth dependency — redirects to /login if not authenticated.
    Use on any route that requires a logged-in user (player or DM).
    """
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_303_SEE_OTHER,
            headers={"Location": "/login"},
        )
    return user


def require_dm(
    user: UserSession = Depends(require_login),
) -> UserSession:
    """
    DM-only guard — returns 403 if the user is not a DM.
    Use on any route that only the DM can access.
    """
    if not user.is_dm:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="DM access required",
        )
    return user
