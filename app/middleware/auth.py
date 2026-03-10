from fastapi import Cookie, Depends, Request
from fastapi.responses import RedirectResponse
from starlette.exceptions import HTTPException

from app.schemas.auth import UserSession
from app.services.auth_service import decode_session_token

SESSION_COOKIE_NAME = "dnd_session"


def get_current_user(
    request: Request,
    dnd_session: str | None = Cookie(default=None, alias=SESSION_COOKIE_NAME),
) -> UserSession | None:
    if not dnd_session:
        return None
    return decode_session_token(dnd_session)


def require_login(
    request: Request,
    user: UserSession | None = Depends(get_current_user),
) -> UserSession:
    if user is None:
        # Redirect to login instead of returning JSON 401
        raise HTTPException(status_code=307, headers={"Location": "/login"})
    return user


def require_dm(
    request: Request,
    user: UserSession = Depends(require_login),
) -> UserSession:
    if not user.is_dm:
        raise HTTPException(status_code=403, detail="DM access required")
    return user
