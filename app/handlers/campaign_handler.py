from pathlib import Path
import logging
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile, status
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.i18n import error_response, render_template
from app.middleware.auth import require_dm, require_login
from app.schemas.auth import UserSession
from app.schemas.campaign import CampaignCreate, CampaignUpdate
from app.schemas.character import (
    DeathSaveUpdate, HPUpdate, MaxHPUpdate,
    SpellSlotUpdate, TempHPUpdate, ThrowableCaseQtyUpdate, ClassResourceUpdate,
)
from app.services.campaign_service import CampaignNotFound, CampaignService, CharacterNotFound
from app.services.character_service import (
    CharacterPermissionError,
    CharacterService,
    CharacterValidationError,
)

router = APIRouter(prefix="/campaigns", tags=["Campaigns"])
templates = Jinja2Templates(directory="app/templates")
logger = logging.getLogger(__name__)


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
        logger.warning("Attempted to delete non-existent campaign %s", campaign_id)
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
    except (CampaignNotFound, CharacterNotFound) as e:
        logger.warning("assign_character failed for campaign %s: %s", campaign_id, e)
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
    except (CampaignNotFound, CharacterNotFound) as e:
        logger.warning("remove_character failed for campaign %s: %s", campaign_id, e)
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
            "cc_portrait_data": campaign_char.portrait_data,
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


# ── Campaign character: save full edit ───────────────────────────────────────

@router.post("/{campaign_id}/characters/{character_id}/edit", response_class=HTMLResponse)
async def campaign_character_edit_submit(
    request: Request,
    campaign_id: UUID,
    character_id: UUID,
    current_user: UserSession = Depends(require_login),
    service: CampaignService = Depends(_service),
    character_service: CharacterService = Depends(_character_service),
):
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

    form = await request.form()
    try:
        updated_sheet = await character_service.build_sheet_from_form(campaign_char.sheet_data, form)
        await character_service.update_campaign_sheet_data(
            campaign_id, character_id, updated_sheet,
            current_user.user_id, current_user.is_dm,
        )
        return RedirectResponse(
            url=f"/campaigns/{campaign_id}/characters/{character_id}",
            status_code=status.HTTP_303_SEE_OTHER,
        )
    except CharacterValidationError as e:
        normalized_sheet = character_service._normalize_sheet(campaign_char.sheet_data)
        return render_template(
            templates,
            "characters/edit.html",
            {
                "request": request,
                "current_user": current_user,
                "character": character,
                "campaign": campaign,
                "sheet": normalized_sheet,
                "error": "Validation failed: " + "; ".join(e.errors),
            },
            language=current_user.language,
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        )
    except (CharacterNotFound, CharacterPermissionError, ValueError, KeyError) as e:
        normalized_sheet = character_service._normalize_sheet(campaign_char.sheet_data)
        return render_template(
            templates,
            "characters/edit.html",
            {
                "request": request,
                "current_user": current_user,
                "character": character,
                "campaign": campaign,
                "sheet": normalized_sheet,
                "error": f"Error updating character: {str(e)}",
            },
            language=current_user.language,
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        )


# ── Campaign character vitals ─────────────────────────────────────────────────

def _cc_can_edit(current_user: UserSession, cc) -> bool:
    return current_user.is_dm or cc.character.owner_id == current_user.user_id


@router.post("/{campaign_id}/characters/{character_id}/vitals/hp", response_class=HTMLResponse)
async def campaign_update_hp(
    request: Request,
    campaign_id: UUID,
    character_id: UUID,
    current_user: UserSession = Depends(require_login),
    character_service: CharacterService = Depends(_character_service),
):
    form = await request.form()
    payload = HPUpdate(delta=form.get("delta"), value=form.get("value"))
    try:
        cc = await character_service.update_campaign_hp(
            campaign_id, character_id, current_user.user_id, current_user.is_dm, payload
        )
    except (CharacterNotFound, CharacterPermissionError):
        return error_response(request, 403, language=current_user.language)
    return render_template(
        templates,
        "characters/_vitals.html",
        {
            "request": request,
            "current_user": current_user,
            "character": cc.character,
            "campaign": cc.campaign,
            "cc_portrait_data": cc.portrait_data,
            
            "sheet": cc.sheet_data,
            "can_edit": _cc_can_edit(current_user, cc),
        },
        language=current_user.language,
    )


@router.post("/{campaign_id}/characters/{character_id}/vitals/death-save", response_class=HTMLResponse)
async def campaign_update_death_save(
    request: Request,
    campaign_id: UUID,
    character_id: UUID,
    current_user: UserSession = Depends(require_login),
    character_service: CharacterService = Depends(_character_service),
):
    form = await request.form()
    payload = DeathSaveUpdate(save_type=form.get("save_type"), action=form.get("action"))
    try:
        cc = await character_service.update_campaign_death_save(
            campaign_id, character_id, current_user.user_id, current_user.is_dm, payload
        )
    except (CharacterNotFound, CharacterPermissionError):
        return error_response(request, 403, language=current_user.language)
    return render_template(
        templates,
        "characters/_sheet_header.html",
        {
            "request": request,
            "current_user": current_user,
            "character": cc.character,
            "campaign": cc.campaign,
            "cc_portrait_data": cc.portrait_data,
            "sheet": cc.sheet_data,
            "can_edit": _cc_can_edit(current_user, cc),
        },
        language=current_user.language,
    )


@router.post("/{campaign_id}/characters/{character_id}/vitals/inspiration", response_class=HTMLResponse)
async def campaign_toggle_inspiration(
    request: Request,
    campaign_id: UUID,
    character_id: UUID,
    current_user: UserSession = Depends(require_login),
    character_service: CharacterService = Depends(_character_service),
):
    try:
        cc = await character_service.toggle_campaign_inspiration(
            campaign_id, character_id, current_user.user_id, current_user.is_dm
        )
    except (CharacterNotFound, CharacterPermissionError):
        return error_response(request, 403, language=current_user.language)
    return render_template(
        templates,
        "characters/_sheet_header.html",
        {
            "request": request,
            "current_user": current_user,
            "character": cc.character,
            "campaign": cc.campaign,
            "cc_portrait_data": cc.portrait_data,
            "sheet": cc.sheet_data,
            "can_edit": _cc_can_edit(current_user, cc),
        },
        language=current_user.language,
    )


@router.post("/{campaign_id}/characters/{character_id}/vitals/spell-slot", response_class=HTMLResponse)
async def campaign_update_spell_slot(
    request: Request,
    campaign_id: UUID,
    character_id: UUID,
    current_user: UserSession = Depends(require_login),
    character_service: CharacterService = Depends(_character_service),
):
    form = await request.form()
    payload = SpellSlotUpdate(level=int(form.get("level")), delta=int(form.get("delta")))
    try:
        cc = await character_service.update_campaign_spell_slot(
            campaign_id, character_id, current_user.user_id, current_user.is_dm, payload
        )
    except (CharacterNotFound, CharacterPermissionError):
        return error_response(request, 403, language=current_user.language)
    return render_template(
        templates,
        "characters/_sheet_body.html",
        {
            "request": request,
            "current_user": current_user,
            "character": cc.character,
            "campaign": cc.campaign,
            "cc_portrait_data": cc.portrait_data,
            "sheet": character_service._normalize_sheet(cc.sheet_data),
            "can_edit": _cc_can_edit(current_user, cc),
            "is_readonly": not _cc_can_edit(current_user, cc),
        },
        language=current_user.language,
    )


@router.post("/{campaign_id}/characters/{character_id}/vitals/temp-hp", response_class=HTMLResponse)
async def campaign_update_temp_hp(
    request: Request,
    campaign_id: UUID,
    character_id: UUID,
    current_user: UserSession = Depends(require_login),
    character_service: CharacterService = Depends(_character_service),
):
    form = await request.form()
    payload = TempHPUpdate(delta=form.get("delta"), value=form.get("value"))
    try:
        cc = await character_service.update_campaign_temp_hp(
            campaign_id, character_id, current_user.user_id, current_user.is_dm,
            payload.delta, payload.value,
        )
    except (CharacterNotFound, CharacterPermissionError):
        return error_response(request, 403, language=current_user.language)
    return render_template(
        templates,
        "characters/_vitals.html",
        {
            "request": request,
            "current_user": current_user,
            "character": cc.character,
            "campaign": cc.campaign,
            "cc_portrait_data": cc.portrait_data,
            "sheet": cc.sheet_data,
            "can_edit": _cc_can_edit(current_user, cc),
        },
        language=current_user.language,
    )


@router.post("/{campaign_id}/characters/{character_id}/vitals/max-hp", response_class=HTMLResponse)
async def campaign_update_max_hp(
    request: Request,
    campaign_id: UUID,
    character_id: UUID,
    current_user: UserSession = Depends(require_dm),
    character_service: CharacterService = Depends(_character_service),
):
    form = await request.form()
    payload = MaxHPUpdate(value=form.get("value", 1))
    try:
        cc = await character_service.update_campaign_max_hp(
            campaign_id, character_id, current_user.user_id, current_user.is_dm, payload.value
        )
    except (CharacterNotFound, CharacterPermissionError):
        return error_response(request, 403, language=current_user.language)
    return render_template(
        templates,
        "characters/_vitals.html",
        {
            "request": request,
            "current_user": current_user,
            "character": cc.character,
            "campaign": cc.campaign,
            "cc_portrait_data": cc.portrait_data,
            "sheet": cc.sheet_data,
            "can_edit": True,
        },
        language=current_user.language,
    )


@router.post("/{campaign_id}/characters/{character_id}/vitals/shield", response_class=HTMLResponse)
async def campaign_toggle_shield(
    request: Request,
    campaign_id: UUID,
    character_id: UUID,
    current_user: UserSession = Depends(require_login),
    character_service: CharacterService = Depends(_character_service),
):
    try:
        cc = await character_service.toggle_campaign_shield(
            campaign_id, character_id, current_user.user_id, current_user.is_dm
        )
    except (CharacterNotFound, CharacterPermissionError):
        return error_response(request, 403, language=current_user.language)
    return render_template(
        templates,
        "characters/_vitals.html",
        {
            "request": request,
            "current_user": current_user,
            "character": cc.character,
            "campaign": cc.campaign,
            "cc_portrait_data": cc.portrait_data,
            "sheet": cc.sheet_data,
            "can_edit": _cc_can_edit(current_user, cc),
        },
        language=current_user.language,
    )


@router.post("/{campaign_id}/characters/{character_id}/vitals/defenses", response_class=HTMLResponse)
async def campaign_update_defenses(
    request: Request,
    campaign_id: UUID,
    character_id: UUID,
    defenses: str = Form(""),
    current_user: UserSession = Depends(require_login),
    character_service: CharacterService = Depends(_character_service),
):
    try:
        cc = await character_service.update_campaign_defenses(
            campaign_id, character_id, defenses, current_user.user_id, current_user.is_dm
        )
    except (CharacterNotFound, CharacterPermissionError):
        return error_response(request, 403, language=current_user.language)
    return render_template(
        templates,
        "characters/_sheet_body.html",
        {
            "request": request,
            "current_user": current_user,
            "character": cc.character,
            "campaign": cc.campaign,
            "cc_portrait_data": cc.portrait_data,
            "sheet": character_service._normalize_sheet(cc.sheet_data),
            "can_edit": _cc_can_edit(current_user, cc),
            "is_readonly": not _cc_can_edit(current_user, cc),
        },
        language=current_user.language,
    )


@router.post("/{campaign_id}/characters/{character_id}/vitals/conditions", response_class=HTMLResponse)
async def campaign_update_conditions(
    request: Request,
    campaign_id: UUID,
    character_id: UUID,
    current_user: UserSession = Depends(require_login),
    character_service: CharacterService = Depends(_character_service),
):
    form = await request.form()
    conditions = form.getlist("conditions")
    try:
        cc = await character_service.update_campaign_conditions(
            campaign_id, character_id, conditions, current_user.user_id, current_user.is_dm
        )
    except (CharacterNotFound, CharacterPermissionError):
        return error_response(request, 403, language=current_user.language)
    return render_template(
        templates,
        "characters/_sheet_body.html",
        {
            "request": request,
            "current_user": current_user,
            "character": cc.character,
            "campaign": cc.campaign,
            "cc_portrait_data": cc.portrait_data,
            "sheet": character_service._normalize_sheet(cc.sheet_data),
            "can_edit": _cc_can_edit(current_user, cc),
            "is_readonly": not _cc_can_edit(current_user, cc),
        },
        language=current_user.language,
    )


@router.post("/{campaign_id}/characters/{character_id}/inventory/throwable-case-qty", response_class=HTMLResponse)
async def campaign_update_throwable_case_qty(
    request: Request,
    campaign_id: UUID,
    character_id: UUID,
    current_user: UserSession = Depends(require_login),
    character_service: CharacterService = Depends(_character_service),
):
    form = await request.form()
    payload = ThrowableCaseQtyUpdate(
        case_index=form.get("case_index", 0),
        item_index=form.get("item_index", 0),
        delta=form.get("delta", 0),
    )
    try:
        cc = await character_service.update_campaign_throwable_case_quantity(
            campaign_id, character_id, current_user.user_id, current_user.is_dm,
            payload.case_index, payload.item_index, payload.delta,
        )
    except (CharacterNotFound, CharacterPermissionError):
        return error_response(request, 403, language=current_user.language)
    return render_template(
        templates,
        "characters/_sheet_body.html",
        {
            "request": request,
            "current_user": current_user,
            "character": cc.character,
            "campaign": cc.campaign,
            "cc_portrait_data": cc.portrait_data,
            "sheet": character_service._normalize_sheet(cc.sheet_data),
            "can_edit": _cc_can_edit(current_user, cc),
            "is_readonly": not _cc_can_edit(current_user, cc),
        },
        language=current_user.language,
    )


# ── Campaign character class resource ─────────────────────────────────────────

@router.post("/{campaign_id}/characters/{character_id}/vitals/class-resource", response_class=HTMLResponse)
async def campaign_update_class_resource(
    request: Request,
    campaign_id: UUID,
    character_id: UUID,
    current_user: UserSession = Depends(require_login),
    character_service: CharacterService = Depends(_character_service),
):
    form = await request.form()
    payload = ClassResourceUpdate(
        resource_index=form.get("resource_index", 0),
        delta=form.get("delta", 0),
    )
    try:
        cc = await character_service.update_campaign_class_resource(
            campaign_id, character_id, current_user.user_id, current_user.is_dm,
            payload.resource_index, payload.delta,
        )
    except (CharacterNotFound, CharacterPermissionError):
        return error_response(request, 403, language=current_user.language)
    return render_template(
        templates,
        "characters/_sheet_body.html",
        {
            "request": request,
            "current_user": current_user,
            "character": cc.character,
            "campaign": cc.campaign,
            "cc_portrait_data": cc.portrait_data,
            "sheet": character_service._normalize_sheet(cc.sheet_data),
            "can_edit": _cc_can_edit(current_user, cc),
            "is_readonly": not _cc_can_edit(current_user, cc),
        },
        language=current_user.language,
    )


# ── Campaign character short rest ──────────────────────────────────────────────

@router.post("/{campaign_id}/characters/{character_id}/vitals/short-rest", response_class=HTMLResponse)
async def campaign_short_rest(
    request: Request,
    campaign_id: UUID,
    character_id: UUID,
    current_user: UserSession = Depends(require_login),
    character_service: CharacterService = Depends(_character_service),
):
    try:
        cc = await character_service.perform_campaign_short_rest(
            campaign_id, character_id, current_user.user_id, current_user.is_dm
        )
    except (CharacterNotFound, CharacterPermissionError):
        return error_response(request, 403, language=current_user.language)
    return render_template(
        templates,
        "characters/_sheet_body.html",
        {
            "request": request,
            "current_user": current_user,
            "character": cc.character,
            "campaign": cc.campaign,
            "cc_portrait_data": cc.portrait_data,
            "sheet": character_service._normalize_sheet(cc.sheet_data),
            "can_edit": _cc_can_edit(current_user, cc),
            "is_readonly": not _cc_can_edit(current_user, cc),
        },
        language=current_user.language,
    )


# ── Campaign character long rest ───────────────────────────────────────────────

@router.post("/{campaign_id}/characters/{character_id}/vitals/long-rest", response_class=HTMLResponse)
async def campaign_long_rest(
    request: Request,
    campaign_id: UUID,
    character_id: UUID,
    current_user: UserSession = Depends(require_login),
    character_service: CharacterService = Depends(_character_service),
):
    try:
        cc = await character_service.perform_campaign_long_rest(
            campaign_id, character_id, current_user.user_id, current_user.is_dm
        )
    except (CharacterNotFound, CharacterPermissionError):
        return error_response(request, 403, language=current_user.language)
    return render_template(
        templates,
        "characters/_sheet_body.html",
        {
            "request": request,
            "current_user": current_user,
            "character": cc.character,
            "campaign": cc.campaign,
            "cc_portrait_data": cc.portrait_data,
            "sheet": character_service._normalize_sheet(cc.sheet_data),
            "can_edit": _cc_can_edit(current_user, cc),
            "is_readonly": not _cc_can_edit(current_user, cc),
        },
        language=current_user.language,
    )


# ── Campaign character portrait ───────────────────────────────────────────────

ALLOWED_PORTRAIT_EXTENSIONS = {".jpg", ".jpeg", ".png"}
ALLOWED_PORTRAIT_MIME_TYPES = {"image/jpeg", "image/png"}
MAX_CAMPAIGN_PORTRAIT_SIZE = 5_242_880  # 5MB

PORTRAIT_MIME_TYPE_MAP = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
}


@router.get("/{campaign_id}/characters/{character_id}/portrait", response_class=Response)
async def campaign_character_portrait(
    campaign_id: UUID,
    character_id: UUID,
    current_user: UserSession = Depends(require_login),
    service: CampaignService = Depends(_service),
):
    """Serve campaign-specific portrait, falling back to base character portrait."""
    try:
        cc = await service._repo.get_campaign_character_with_association(campaign_id, character_id)
        if cc is None:
            raise CharacterNotFound()
    except CharacterNotFound:
        return Response(status_code=404)

    if cc.portrait_data:
        return Response(
            content=cc.portrait_data,
            media_type=cc.portrait_mime_type or "image/jpeg",
        )
    if cc.character.portrait_data:
        return Response(
            content=cc.character.portrait_data,
            media_type=cc.character.portrait_mime_type or "image/jpeg",
        )
    return Response(status_code=404)


@router.get("/{campaign_id}/characters/{character_id}/portrait/upload", response_class=HTMLResponse)
async def campaign_portrait_upload_form(
    request: Request,
    campaign_id: UUID,
    character_id: UUID,
    current_user: UserSession = Depends(require_login),
    service: CampaignService = Depends(_service),
):
    try:
        campaign = await service.get_campaign(campaign_id)
        cc = await service._repo.get_campaign_character_with_association(campaign_id, character_id)
        if cc is None:
            raise CharacterNotFound()
    except (CampaignNotFound, CharacterNotFound):
        return error_response(request, 404, language=current_user.language)

    if not (current_user.is_dm or cc.character.owner_id == current_user.user_id):
        return error_response(request, 403, language=current_user.language)

    return render_template(
        templates,
        "characters/_portrait_upload_modal.html",
        {
            "request": request,
            "character": cc.character,
            "campaign": campaign,
        },
        language=current_user.language,
    )


@router.post("/{campaign_id}/characters/{character_id}/portrait/upload", response_class=HTMLResponse)
async def campaign_upload_portrait(
    request: Request,
    campaign_id: UUID,
    character_id: UUID,
    file: UploadFile = File(...),
    current_user: UserSession = Depends(require_login),
    service: CampaignService = Depends(_service),
    character_service: CharacterService = Depends(_character_service),
):
    try:
        campaign = await service.get_campaign(campaign_id)
        cc = await service._repo.get_campaign_character_with_association(campaign_id, character_id)
        if cc is None:
            raise CharacterNotFound()
    except (CampaignNotFound, CharacterNotFound):
        return error_response(request, 404, language=current_user.language)

    if not (current_user.is_dm or cc.character.owner_id == current_user.user_id):
        return error_response(request, 403, language=current_user.language)

    file_ext = Path(file.filename).suffix.lower()
    if file_ext not in ALLOWED_PORTRAIT_EXTENSIONS:
        return render_template(
            templates,
            "characters/_portrait_upload_modal.html",
            {
                "request": request,
                "character": cc.character,
                "campaign": campaign,
                "error": "Only JPEG and PNG files are allowed.",
            },
            language=current_user.language,
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        )

    contents = await file.read(MAX_CAMPAIGN_PORTRAIT_SIZE + 1)
    if len(contents) > MAX_CAMPAIGN_PORTRAIT_SIZE:
        return render_template(
            templates,
            "characters/_portrait_upload_modal.html",
            {
                "request": request,
                "character": cc.character,
                "campaign": campaign,
                "error": "File too large. Maximum size is 5MB.",
            },
            language=current_user.language,
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        )

    mime_type = PORTRAIT_MIME_TYPE_MAP.get(file_ext, "image/jpeg")
    updated_cc = await character_service.update_campaign_portrait(
        campaign_id, character_id, contents, mime_type,
        current_user.user_id, current_user.is_dm,
    )
    return render_template(
        templates,
        "characters/_sheet_header.html",
        {
            "request": request,
            "current_user": current_user,
            "character": updated_cc.character,
            "campaign": updated_cc.campaign,
            "cc_portrait_data": updated_cc.portrait_data,
            "sheet": updated_cc.sheet_data,
            "can_edit": current_user.is_dm or updated_cc.character.owner_id == current_user.user_id,
        },
        language=current_user.language,
    )
