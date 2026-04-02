from uuid import UUID

from fastapi import APIRouter, Depends, Form, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.i18n import error_response, render_template
from app.middleware.auth import require_dm, require_login
from app.schemas.auth import UserSession
from app.schemas.campaign import CampaignCreate, CampaignUpdate
from app.services.campaign_service import CampaignNotFound, CampaignService, CharacterNotFound
from app.services.character_service import CharacterService

router = APIRouter(prefix="/campaigns", tags=["Campaigns"])
templates = Jinja2Templates(directory="app/templates")


def _service(db: AsyncSession = Depends(get_db)) -> CampaignService:
    return CampaignService(db)


def _character_service(db: AsyncSession = Depends(get_db)) -> CharacterService:
    return CharacterService(db)


# ── List ─────────────────────────────────────────────────────────────────────

@router.get("", response_class=HTMLResponse)
async def campaign_list(
    request: Request,
    current_user: UserSession = Depends(require_login),
    service: CampaignService = Depends(_service),
):
    campaigns = await service.list_campaigns(
        user_id=current_user.user_id,
        is_dm=current_user.is_dm,
    )
    return render_template(templates, "campaigns/list.html", {
        "request": request,
        "current_user": current_user,
        "campaigns": campaigns,
    }, language=current_user.language)


# ── Create (NEW must be before /{campaign_id}) ────────────────────────────────

@router.get("/new", response_class=HTMLResponse)
async def campaign_new_form(
    request: Request,
    current_user: UserSession = Depends(require_dm),
):
    return render_template(templates, "campaigns/form.html", {
        "request": request,
        "current_user": current_user,
        "campaign": None,
        "error": None,
    }, language=current_user.language)


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
        campaign = await service.create_campaign(data, created_by=current_user.user_id)
        return RedirectResponse(
            url=f"/campaigns/{campaign.id}",
            status_code=status.HTTP_303_SEE_OTHER,
        )
    except ValueError as e:
        return render_template(
            templates,
            "campaigns/form.html",
            {"request": request, "current_user": current_user,
             "campaign": None, "error": str(e)},
            language=current_user.language,
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
        # Show only characters not already in THIS campaign
        unassigned_characters = await service.get_available_characters_for_campaign(campaign_id)
    except CampaignNotFound:
        return error_response(
            request, 404,
            error_message="Campaign not found.",
            back_url="/campaigns",
            back_label="Back to Campaigns",
            language=current_user.language,
        )
    return render_template(templates, "campaigns/detail.html", {
        "request": request,
        "current_user": current_user,
        "campaign": campaign,
        "unassigned_characters": unassigned_characters,
    }, language=current_user.language)


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
    return render_template(templates, "campaigns/form.html", {
        "request": request,
        "current_user": current_user,
        "campaign": campaign,
        "error": None,
    }, language=current_user.language)


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
        return render_template(
            templates,
            "campaigns/form.html",
            {"request": request, "current_user": current_user,
             "campaign": campaign, "error": str(e)},
            language=current_user.language,
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
        # Get characters not already in THIS campaign (but can be in other campaigns)
        available = await service.get_available_characters_for_campaign(campaign_id)
    except CampaignNotFound:
        return RedirectResponse(url="/campaigns", status_code=status.HTTP_303_SEE_OTHER)

    return render_template(templates, "campaigns/add_characters.html", {
        "request": request,
        "current_user": current_user,
        "campaign": campaign,
        "available": available,
    }, language=current_user.language)


@router.post("/{campaign_id}/characters", response_class=HTMLResponse)
async def assign_character(
    campaign_id: UUID,
    character_id: UUID = Form(...),
    current_user: UserSession = Depends(require_dm),
    service: CampaignService = Depends(_service),
):
    try:
        await service.assign_character(campaign_id, character_id)
    except (CampaignNotFound, CharacterNotFound):
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
    except (CampaignNotFound, CharacterNotFound):
        pass
    return RedirectResponse(
        url=f"/campaigns/{campaign_id}", status_code=status.HTTP_303_SEE_OTHER
    )


# ── Campaign-specific character view ──────────────────────────────────────────

@router.get("/{campaign_id}/characters/{character_id}", response_class=HTMLResponse)
async def campaign_character_sheet(
    request: Request,
    campaign_id: UUID,
    character_id: UUID,
    current_user: UserSession = Depends(require_login),
    service: CampaignService = Depends(_service),
    character_service: CharacterService = Depends(_character_service),
):
    """View a character as part of a specific campaign (campaign-specific data)."""
    try:
        campaign = await service.get_campaign(campaign_id)
        campaign_char = await service._repo.get_campaign_character_with_association(
            campaign_id, character_id
        )
        if campaign_char is None:
            raise CharacterNotFound(f"Character {character_id} not found in campaign {campaign_id}")
        
        character = campaign_char.character
    except (CampaignNotFound, CharacterNotFound):
        return RedirectResponse(url="/campaigns", status_code=status.HTTP_303_SEE_OTHER)

    # Use campaign-specific sheet_data, not base character sheet
    normalized_sheet = character_service._normalize_sheet(campaign_char.sheet_data)
    
    can_edit = current_user.is_dm or character.owner_id == current_user.user_id
    
    return render_template(
        templates,
        "characters/sheet.html",
        {
            "request": request,
            "current_user": current_user,
            "character": character,
            "campaign": campaign,  # Include campaign for breadcrumb
            "sheet": normalized_sheet,
            "can_edit": can_edit,
            "is_readonly": not can_edit,
        },
        language=current_user.language,
    )


@router.get("/{campaign_id}/characters/{character_id}/edit", response_class=HTMLResponse)
async def campaign_character_edit_form(
    request: Request,
    campaign_id: UUID,
    character_id: UUID,
    current_user: UserSession = Depends(require_dm),
    service: CampaignService = Depends(_service),
    character_service: CharacterService = Depends(_character_service),
):
    """Edit a character as part of a specific campaign (campaign-specific data)."""
    try:
        campaign = await service.get_campaign(campaign_id)
        campaign_char = await service._repo.get_campaign_character_with_association(
            campaign_id, character_id
        )
        if campaign_char is None:
            raise CharacterNotFound(f"Character {character_id} not found in campaign {campaign_id}")
        
        character = campaign_char.character
    except (CampaignNotFound, CharacterNotFound):
        return RedirectResponse(url="/campaigns", status_code=status.HTTP_303_SEE_OTHER)

    # Use campaign-specific sheet_data
    normalized_sheet = character_service._normalize_sheet(campaign_char.sheet_data)
    
    return render_template(
        templates,
        "characters/edit.html",
        {
            "request": request,
            "current_user": current_user,
            "character": character,
            "campaign": campaign,  # Include campaign context
            "sheet": normalized_sheet,
        },
        language=current_user.language,
    )
