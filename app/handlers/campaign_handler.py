from uuid import UUID

from fastapi import APIRouter, Depends, Form, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.middleware.auth import require_dm, require_login
from app.schemas.auth import UserSession
from app.schemas.campaign import CampaignCreate, CampaignUpdate
from app.services.campaign_service import CampaignNotFound, CampaignService

router = APIRouter(prefix="/campaigns", tags=["Campaigns"])
templates = Jinja2Templates(directory="app/templates")


def _service(db: AsyncSession = Depends(get_db)) -> CampaignService:
    return CampaignService(db)


# ── List ─────────────────────────────────────────────────────────────────────

@router.get("", response_class=HTMLResponse)
async def campaign_list(
    request: Request,
    current_user: UserSession = Depends(require_login),
    service: CampaignService = Depends(_service),
):
    campaigns = await service.list_campaigns()
    return templates.TemplateResponse("campaigns/list.html", {
        "request": request,
        "current_user": current_user,
        "campaigns": campaigns,
    })


# ── Create (NEW must be before /{campaign_id}) ────────────────────────────────

@router.get("/new", response_class=HTMLResponse)
async def campaign_new_form(
    request: Request,
    current_user: UserSession = Depends(require_dm),
):
    return templates.TemplateResponse("campaigns/form.html", {
        "request": request,
        "current_user": current_user,
        "campaign": None,
        "error": None,
    })


@router.post("", response_class=HTMLResponse)
async def campaign_create(
    request: Request,
    current_user: UserSession = Depends(require_dm),
    name: str = Form(...),
    description: str = Form(""),
    service: CampaignService = Depends(_service),
):
    try:
        data = CampaignCreate(name=name, description=description or None)
        campaign = await service.create_campaign(data, created_by=UUID(current_user.user_id))
        return RedirectResponse(
            url=f"/campaigns/{campaign.id}",
            status_code=status.HTTP_303_SEE_OTHER,
        )
    except ValueError as e:
        return templates.TemplateResponse(
            "campaigns/form.html",
            {"request": request, "current_user": current_user,
             "campaign": None, "error": str(e)},
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        )


# ── Detail (/{campaign_id} AFTER /new) ───────────────────────────────────────

@router.get("/{campaign_id}", response_class=HTMLResponse)
async def campaign_detail(
    request: Request,
    campaign_id: UUID,
    current_user: UserSession = Depends(require_login),
    service: CampaignService = Depends(_service),
):
    try:
        campaign = await service.get_campaign(campaign_id)
    except CampaignNotFound:
        return templates.TemplateResponse(
            "campaigns/list.html",
            {"request": request, "current_user": current_user,
             "campaigns": [], "error": "Campaign not found"},
            status_code=status.HTTP_404_NOT_FOUND,
        )
    return templates.TemplateResponse("campaigns/detail.html", {
        "request": request,
        "current_user": current_user,
        "campaign": campaign,
    })


# ── Edit ─────────────────────────────────────────────────────────────────────

@router.get("/{campaign_id}/edit", response_class=HTMLResponse)
async def campaign_edit_form(
    request: Request,
    campaign_id: UUID,
    current_user: UserSession = Depends(require_dm),
    service: CampaignService = Depends(_service),
):
    try:
        campaign = await service.get_campaign(campaign_id)
    except CampaignNotFound:
        return RedirectResponse(url="/campaigns", status_code=status.HTTP_303_SEE_OTHER)
    return templates.TemplateResponse("campaigns/form.html", {
        "request": request,
        "current_user": current_user,
        "campaign": campaign,
        "error": None,
    })


@router.post("/{campaign_id}/edit", response_class=HTMLResponse)
async def campaign_update(
    request: Request,
    campaign_id: UUID,
    current_user: UserSession = Depends(require_dm),
    name: str = Form(...),
    description: str = Form(""),
    service: CampaignService = Depends(_service),
):
    try:
        data = CampaignUpdate(name=name, description=description or None)
        await service.update_campaign(campaign_id, data)
        return RedirectResponse(
            url=f"/campaigns/{campaign_id}",
            status_code=status.HTTP_303_SEE_OTHER,
        )
    except (ValueError, CampaignNotFound) as e:
        try:
            campaign = await service.get_campaign(campaign_id)
        except CampaignNotFound:
            return RedirectResponse(url="/campaigns", status_code=status.HTTP_303_SEE_OTHER)
        return templates.TemplateResponse(
            "campaigns/form.html",
            {"request": request, "current_user": current_user,
             "campaign": campaign, "error": str(e)},
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        )


# ── Delete ───────────────────────────────────────────────────────────────────

@router.post("/{campaign_id}/delete", response_class=HTMLResponse)
async def campaign_delete(
    campaign_id: UUID,
    current_user: UserSession = Depends(require_dm),
    service: CampaignService = Depends(_service),
):
    try:
        await service.delete_campaign(campaign_id)
    except CampaignNotFound:
        pass
    return RedirectResponse(url="/campaigns", status_code=status.HTTP_303_SEE_OTHER)

# ── Character assignment ──────────────────────────────────────────────────────

@router.get("/{campaign_id}/add-characters", response_class=HTMLResponse)
async def add_characters_form(
    request: Request,
    campaign_id: UUID,
    current_user: UserSession = Depends(require_dm),
    service: CampaignService = Depends(_service),
):
    try:
        campaign = await service.get_campaign(campaign_id)
        available = await service.get_unassigned_characters(campaign_id)
    except CampaignNotFound:
        return RedirectResponse(url="/campaigns", status_code=status.HTTP_303_SEE_OTHER)

    return templates.TemplateResponse("campaigns/add_characters.html", {
        "request": request,
        "current_user": current_user,
        "campaign": campaign,
        "available": available,
    })


@router.post("/{campaign_id}/characters", response_class=HTMLResponse)
async def assign_character(
    campaign_id: UUID,
    character_id: UUID = Form(...),
    current_user: UserSession = Depends(require_dm),
    service: CampaignService = Depends(_service),
):
    try:
        await service.assign_character(campaign_id, character_id)
    except CampaignNotFound:
        pass
    return RedirectResponse(
        url=f"/campaigns/{campaign_id}", status_code=status.HTTP_303_SEE_OTHER
    )


@router.post("/{campaign_id}/characters/{character_id}/remove", response_class=HTMLResponse)
async def remove_character(
    campaign_id: UUID,
    character_id: UUID,
    current_user: UserSession = Depends(require_dm),
    service: CampaignService = Depends(_service),
):
    try:
        await service.remove_character(campaign_id, character_id)
    except CampaignNotFound:
        pass
    return RedirectResponse(
        url=f"/campaigns/{campaign_id}", status_code=status.HTTP_303_SEE_OTHER
    )
