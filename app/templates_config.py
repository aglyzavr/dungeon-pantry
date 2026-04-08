"""Shared Jinja2Templates instance with custom filters."""
import markdown as _markdown
import nh3

from fastapi.templating import Jinja2Templates

# Allowed HTML tags after markdown rendering (no scripts, no events)
_ALLOWED_TAGS = {
    "p", "br", "hr",
    "h1", "h2", "h3", "h4",
    "strong", "em", "del", "code", "pre", "blockquote",
    "ul", "ol", "li",
    "a",
    "table", "thead", "tbody", "tr", "th", "td",
}

_ALLOWED_ATTRIBUTES = {
    "a": {"href", "title"},
}


def _markdown_filter(value: str) -> str:
    """Render Markdown to sanitized HTML.

    Converts the given string from Markdown to HTML using the *tables*,
    *fenced_code* and *nl2br* extensions, then strips any unsafe tags/
    attributes with nh3 so the result is safe to emit with |safe.
    """
    if not value:
        return ""
    html = _markdown.markdown(
        value,
        extensions=["tables", "fenced_code", "nl2br"],
    )
    return nh3.clean(
        html,
        tags=_ALLOWED_TAGS,
        attributes=_ALLOWED_ATTRIBUTES,
    )


templates = Jinja2Templates(directory="app/templates")
templates.env.filters["markdown"] = _markdown_filter
