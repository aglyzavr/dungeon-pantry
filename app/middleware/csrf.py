import hmac
import secrets

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.i18n import error_response

CSRF_COOKIE_NAME = "csrf_token"
CSRF_FIELD_NAME = "csrf_token"
CSRF_HEADER_NAME = "x-csrf-token"
SAFE_METHODS = {"GET", "HEAD", "OPTIONS", "TRACE"}
EXEMPT_PATHS = {"/health"}


class CSRFMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        csrf_cookie = request.cookies.get(CSRF_COOKIE_NAME)
        if not csrf_cookie:
            csrf_cookie = secrets.token_hex(32)

        request.state.csrf_token = csrf_cookie

        if request.method not in SAFE_METHODS and request.url.path not in EXEMPT_PATHS:
            submitted_token = None

            content_type = request.headers.get("content-type", "")
            if "multipart/form-data" in content_type or "application/x-www-form-urlencoded" in content_type:
                form = await request.form()
                submitted_token = form.get(CSRF_FIELD_NAME)

            if not submitted_token:
                submitted_token = request.headers.get(CSRF_HEADER_NAME)

            if not submitted_token or not hmac.compare_digest(str(submitted_token), csrf_cookie):
                return error_response(
                    request, 403,
                    error_message="CSRF token missing or invalid. Please refresh the page and try again.",
                )

        response = await call_next(request)

        response.set_cookie(
            key=CSRF_COOKIE_NAME,
            value=csrf_cookie,
            httponly=False,
            samesite="lax",
            secure=False,
            path="/",
        )

        return response
