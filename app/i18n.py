"""Translation utilities for i18n support."""
import gettext
from pathlib import Path
from typing import Optional

from fastapi import Request
from fastapi.templating import Jinja2Templates
from starlette.responses import Response

# Module-level templates instance for error_response (avoids circular imports)
_error_templates = Jinja2Templates(directory="app/templates")

# Path to translations
LOCALES_DIR = Path(__file__).parent / "locales"

# Cache for translation objects
_translations = {}


def get_translator(language: str = "en"):
    """Get a translator for the specified language.
    
    Args:
        language: Language code ('en' or 'ru')
        
    Returns:
        A gettext translation object
    """
    if language not in _translations:
        try:
            _translations[language] = gettext.translation(
                "messages",
                localedir=str(LOCALES_DIR),
                languages=[language],
                fallback=(language == "en"),
            )
        except FileNotFoundError:
            # Fallback to English or NullTranslations
            _translations[language] = gettext.NullTranslations()
    
    return _translations[language]


def translate(message: str, language: str = "en") -> str:
    """Translate a message to the specified language.
    
    Args:
        message: The message to translate
        language: Target language code
        
    Returns:
        Translated message
    """
    translator = get_translator(language)
    return translator.gettext(message)


def get_jinja_env_globals(language: str = "en"):
    """Get Jinja2 global functions for translations.
    
    Args:
        language: Language code for translations
        
    Returns:
        Dictionary of global functions to add to Jinja2 environment
    """
    translator = get_translator(language)
    return {
        "_": translator.gettext,
        "gettext": translator.gettext,
        "ngettext": translator.ngettext,
    }


def render_template(
    templates: Jinja2Templates,
    name: str,
    context: dict,
    language: str = "en",
    status_code: int = 200,
) -> Response:
    """Render a template with translation support.
    
    Args:
        templates: Jinja2Templates instance
        name: Template name
        context: Template context (must include 'request')
        language: Language code for translations
        status_code: HTTP status code
        
    Returns:
        TemplateResponse with translations injected
    """
    # Inject translation functions into context
    translator = get_translator(language)
    context["_"] = translator.gettext
    context["gettext"] = translator.gettext
    context["ngettext"] = translator.ngettext
    
    return templates.TemplateResponse(
        name,
        context,
        status_code=status_code,
    )


# ── Default error messages per status code ────────────────────────────────

_ERROR_DEFAULTS = {
    403: ("Forbidden", "You don't have permission to access this resource."),
    404: ("Not Found", "The page or resource you're looking for doesn't exist."),
    410: ("Gone", "This resource is no longer available."),
    422: ("Invalid Request", "The submitted data could not be processed."),
    500: ("Server Error", "Something went wrong. Please try again later."),
}


def error_response(
    request: Request,
    status_code: int,
    error_message: str | None = None,
    error_detail: str | None = None,
    back_url: str | None = None,
    back_label: str | None = None,
    language: str = "en",
) -> Response:
    """Render a consistent full-page error using the shared error template."""
    default_title, default_message = _ERROR_DEFAULTS.get(
        status_code, ("Error", "An unexpected error occurred.")
    )

    # Try to get current_user for navbar rendering
    current_user = None
    try:
        from app.services.auth_service import decode_session_token
        session_cookie = request.cookies.get("dnd_session")
        if session_cookie:
            current_user = decode_session_token(session_cookie)
            if current_user and not language:
                language = current_user.language
    except Exception:
        pass

    context = {
        "request": request,
        "current_user": current_user,
        "status_code": status_code,
        "error_title": default_title,
        "error_message": error_message or default_message,
        "error_detail": error_detail,
        "back_url": back_url,
        "back_label": back_label,
    }

    return render_template(
        _error_templates,
        "error.html",
        context,
        language=language,
        status_code=status_code,
    )

