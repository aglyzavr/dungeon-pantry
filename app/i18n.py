"""Translation utilities for i18n support."""
import gettext
from pathlib import Path
from typing import Optional

from fastapi import Request
from fastapi.templating import Jinja2Templates
from starlette.responses import Response

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

