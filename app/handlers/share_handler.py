from uuid import UUID

from fastapi import APIRouter, Depends, Form, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.middleware.auth import require_dm
from app.schemas.auth import UserSession
from app.services.share_link_service import (
    ShareLinkExpired,
    ShareLinkNotFound,
    ShareLinkService,
)

router = APIRouter(tags=["Share"])
templates = Jinja2Templates(directory="app/templates")


def _service(db: AsyncSession = Depends(get_db)) -> ShareLinkService:
    return ShareLinkService(db)


# ── Public read-only view ─────────────────────────────────────────────────

# ── Public read-only view ─────────────────────────────────────────────────

@router.get("/share/{token}", response_class=HTMLResponse)
async def public_sheet(
    request: Request,
    token: str,
    service: ShareLinkService = Depends(_service),
):
    try:
        link = await service.get_valid_link(token)
    except ShareLinkNotFound:
        return templates.TemplateResponse(
            "share/sheet.html",
            {
                "request": request,
                "error": "This share link does not exist.",
                "character": None,
                "sheet": None,
                "link": None,
                "current_user": None,  # ← add
            },
            status_code=status.HTTP_404_NOT_FOUND,
        )
    except ShareLinkExpired:
        return templates.TemplateResponse(
            "share/sheet.html",
            {
                "request": request,
                "error": "This share link has expired or been revoked.",
                "character": None,
                "sheet": None,
                "link": None,
                "current_user": None,  # ← add
            },
            status_code=status.HTTP_410_GONE,
        )

    character = link.character
    return templates.TemplateResponse("share/sheet.html", {
        "request": request,
        "character": character,
        "sheet": character.sheet_data,
        "link": link,
        "error": None,
        "current_user": None,  # ← add
    })



# ── DM: create share link ─────────────────────────────────────────────────

@router.post("/characters/{character_id}/share", response_class=HTMLResponse)
async def create_share_link(
    character_id: UUID,
    label: str = Form(""),
    expires_days: int = Form(0),
    current_user: UserSession = Depends(require_dm),
    service: ShareLinkService = Depends(_service),
):
    await service.create_link(
        character_id=character_id,
        label=label or None,
        expires_days=expires_days if expires_days > 0 else None,
    )
    return RedirectResponse(
        url=f"/characters/{character_id}",
        status_code=status.HTTP_303_SEE_OTHER,
    )


# ── DM: revoke share link ─────────────────────────────────────────────────

@router.post("/share/{token}/revoke", response_class=HTMLResponse)
async def revoke_share_link(
    token: str,
    character_id: UUID = Form(...),
    current_user: UserSession = Depends(require_dm),
    service: ShareLinkService = Depends(_service),
):
    try:
        await service.revoke_link(token, expected_character_id=character_id)
    except ShareLinkNotFound:
        pass
    return RedirectResponse(
        url=f"/characters/{character_id}",
        status_code=status.HTTP_303_SEE_OTHER,
    )


# ── DM: delete share link ─────────────────────────────────────────────────

@router.post("/share/{token}/delete", response_class=HTMLResponse)
async def delete_share_link(
    token: str,
    character_id: UUID = Form(...),
    current_user: UserSession = Depends(require_dm),
    service: ShareLinkService = Depends(_service),
):
    try:
        await service.delete_link(token, expected_character_id=character_id)
    except ShareLinkNotFound:
        pass
    return RedirectResponse(
        url=f"/characters/{character_id}",
        status_code=status.HTTP_303_SEE_OTHER,
    )
