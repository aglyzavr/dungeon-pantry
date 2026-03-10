from uuid import UUID
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile, status
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.i18n import error_response, render_template
from app.middleware.auth import require_dm, require_login
from app.schemas.auth import UserSession
from app.schemas.character import (
    HPUpdate, DeathSaveUpdate, SpellSlotUpdate,
    TempHPUpdate, MaxHPUpdate, ThrowableCaseQtyUpdate,
)
from jinja2 import TemplateError
from app.services.character_service import (
    CharacterNotFound,
    CharacterPermissionError,
    CharacterValidationError,
    CharacterService,
)
from app.services.player_service import PlayerService

router = APIRouter(prefix="/characters", tags=["Characters"])
templates = Jinja2Templates(directory="app/templates")


def _can_edit(current_user: UserSession, character) -> bool:
    """Check if the current user has edit permission on a character."""
    return current_user.is_dm or character.owner_id == current_user.user_id


def _service(db: AsyncSession = Depends(get_db)) -> CharacterService:
    return CharacterService(db)


def _player_service(db: AsyncSession = Depends(get_db)) -> PlayerService:
    return PlayerService(db)


# ── List (DM only) ────────────────────────────────────────────────────────

@router.get("", response_class=HTMLResponse)
async def character_list(
    request: Request,
    current_user: UserSession = Depends(require_dm),
    service: CharacterService = Depends(_service),
):
    characters = await service.list_all()
    return render_template(
        templates,
        "characters/list.html",
        {
            "request": request,
            "current_user": current_user,
            "characters": characters,
        },
        language=current_user.language,
    )


# ── Upload form ───────────────────────────────────────────────────────────

@router.get("/upload", response_class=HTMLResponse)
async def upload_form(
    request: Request,
    current_user: UserSession = Depends(require_dm),
):
    return render_template(
        templates,
        "characters/upload.html",
        {
            "request": request,
            "current_user": current_user,
            "error": None,
        },
        language=current_user.language,
    )


@router.post("/upload", response_class=HTMLResponse)
async def upload_character(
    request: Request,
    file: UploadFile = File(...),
    current_user: UserSession = Depends(require_dm),
    service: CharacterService = Depends(_service),
):
    # File size guard — 1MB max
    contents = await file.read(1_048_577)
    if len(contents) > 1_048_576:
        return render_template(
            templates,
            "characters/upload.html",
            {
                "request": request,
                "current_user": current_user,
                "error": "File too large. Maximum size is 1MB.",
            },
            language=current_user.language,
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        )

    try:
        character = await service.create_from_upload(
            raw_content=contents,
            owner_id=current_user.user_id,
        )
    except CharacterValidationError as e:
        return render_template(
            templates,
            "characters/upload.html",
            {
                "request": request,
                "current_user": current_user,
                "error": "; ".join(e.errors),
            },
            language=current_user.language,
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        )

    return RedirectResponse(
        url=f"/characters/{character.id}",
        status_code=status.HTTP_303_SEE_OTHER,
    )


# ── Sheet view ────────────────────────────────────────────────────────────

@router.get("/{character_id}", response_class=HTMLResponse)
async def character_sheet(
    request: Request,
    character_id: UUID,
    current_user: UserSession = Depends(require_login),
    service: CharacterService = Depends(_service),
    player_service: PlayerService = Depends(_player_service),
    db: AsyncSession = Depends(get_db),
):
    try:
        character = await service.get_character(
            character_id, current_user.user_id, current_user.is_dm
        )
    except CharacterNotFound:
        return RedirectResponse(url="/characters", status_code=status.HTTP_303_SEE_OTHER)

    if current_user.is_dm:
        await db.refresh(character, ["share_links", "campaigns"])
    else:
        await db.refresh(character, ["campaigns"])

    # Load players for assignment dropdown (DM only)
    players = await player_service.list_players() if current_user.is_dm else []

    # Determine if user can edit and view full details
    can_edit = _can_edit(current_user, character)
    is_readonly = not can_edit  # If can't edit, it's read-only mode
    
    # Pass full sheet data to template - template conditionals handle visibility
    # No backend filtering needed, all 'is_readonly' sections are hidden in views

    try:
        resp = render_template(
            templates,
            "characters/sheet.html",
            {
                "request": request,
                "current_user": current_user,
                "character": character,
                "sheet": character.sheet_data,
                "players": players,
                "campaigns": character.campaigns,
                "can_edit": can_edit,
                "is_readonly": is_readonly,
            },
            language=current_user.language,
        )
        return resp
    except TemplateError as e:
        return error_response(
            request, 500,
            error_message="There was an error loading this character sheet. This might be due to corrupted data or a temporary issue.",
            error_detail=str(e),
            back_url="/characters",
            back_label="Back to Characters",
            language=current_user.language,
        )


# ── Delete ────────────────────────────────────────────────────────────────

@router.post("/{character_id}/delete", response_class=HTMLResponse)
async def character_delete(
    character_id: UUID,
    current_user: UserSession = Depends(require_dm),
    service: CharacterService = Depends(_service),
):
    try:
        await service.delete(character_id)
    except CharacterNotFound:
        pass
    return RedirectResponse(url="/characters", status_code=status.HTTP_303_SEE_OTHER)


# ── Edit character ────────────────────────────────────────────────────────

@router.get("/{character_id}/edit", response_class=HTMLResponse)
async def edit_character_form(
    request: Request,
    character_id: UUID,
    current_user: UserSession = Depends(require_login),
    service: CharacterService = Depends(_service),
):
    try:
        character = await service.get_character(
            character_id, current_user.user_id, current_user.is_dm
        )
    except CharacterNotFound:
        return RedirectResponse(url="/characters", status_code=status.HTTP_303_SEE_OTHER)

    # Check if user can edit (DM or character owner)
    can_edit = _can_edit(current_user, character)
    if not can_edit:
        return RedirectResponse(url=f"/characters/{character_id}", status_code=status.HTTP_303_SEE_OTHER)

    return render_template(
        templates,
        "characters/edit.html",
        {
            "request": request,
            "current_user": current_user,
            "character": character,
            "sheet": character.sheet_data,
        },
        language=current_user.language,
    )


@router.post("/{character_id}/edit", response_class=HTMLResponse)
async def edit_character_submit(
    request: Request,
    character_id: UUID,
    current_user: UserSession = Depends(require_login),
    service: CharacterService = Depends(_service),
):
    try:
        character = await service.get_character(
            character_id, current_user.user_id, current_user.is_dm
        )
    except CharacterNotFound:
        return RedirectResponse(url="/characters", status_code=status.HTTP_303_SEE_OTHER)

    # Check if user can edit
    can_edit = _can_edit(current_user, character)
    if not can_edit:
        return RedirectResponse(url=f"/characters/{character_id}", status_code=status.HTTP_303_SEE_OTHER)

    form = await request.form()
    
    try:
        updated_sheet = await service.build_sheet_from_form(character, form)
        await service.update_sheet_data(character_id, updated_sheet)
        return RedirectResponse(
            url=f"/characters/{character_id}",
            status_code=status.HTTP_303_SEE_OTHER,
        )
    except CharacterValidationError as e:
        return render_template(
            templates,
            "characters/edit.html",
            {
                "request": request,
                "current_user": current_user,
                "character": character,
                "sheet": character.sheet_data,
                "error": "Validation failed: " + "; ".join(e.errors),
            },
            language=current_user.language,
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        )
    except (CharacterNotFound, ValueError, KeyError) as e:
        return render_template(
            templates,
            "characters/edit.html",
            {
                "request": request,
                "current_user": current_user,
                "character": character,
                "sheet": character.sheet_data,
                "error": f"Error updating character: {str(e)}",
            },
            language=current_user.language,
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        )


# ── Vitals: HP ────────────────────────────────────────────────────────────

@router.post("/{character_id}/vitals/hp", response_class=HTMLResponse)
async def update_hp(
    request: Request,
    character_id: UUID,
    current_user: UserSession = Depends(require_login),
    service: CharacterService = Depends(_service),
):
    form = await request.form()
    payload = HPUpdate(
        delta=form.get("delta"),
        value=form.get("value"),
    )

    try:
        character = await service.update_hp(
            character_id, current_user.user_id, current_user.is_dm, payload
        )
    except (CharacterNotFound, CharacterPermissionError):
        return error_response(request, 403, language=current_user.language)

    return render_template(
        templates,
        "characters/_vitals.html",
        {
            "request": request,
            "current_user": current_user,
            "character": character,
            "sheet": character.sheet_data,
            "can_edit": _can_edit(current_user, character),
        },
        language=current_user.language,
    )


# ── Vitals: Death saves ───────────────────────────────────────────────────

@router.post("/{character_id}/vitals/death-save", response_class=HTMLResponse)
async def update_death_save(
    request: Request,
    character_id: UUID,
    current_user: UserSession = Depends(require_login),
    service: CharacterService = Depends(_service),
    db: AsyncSession = Depends(get_db),
):
    form = await request.form()
    payload = DeathSaveUpdate(
        save_type=form.get("save_type"),
        action=form.get("action"),
    )

    try:
        character = await service.update_death_save(
            character_id, current_user.user_id, current_user.is_dm, payload
        )
    except (CharacterNotFound, CharacterPermissionError):
        return error_response(request, 403, language=current_user.language)

    await db.refresh(character, ["campaigns"])

    return render_template(
        templates,
        "characters/_sheet_header.html",
        {
            "request": request,
            "current_user": current_user,
            "character": character,
            "sheet": character.sheet_data,
            "campaigns": character.campaigns,
            "can_edit": _can_edit(current_user, character),
        },
        language=current_user.language,
    )


# ── Vitals: Inspiration ───────────────────────────────────────────────────

@router.post("/{character_id}/vitals/inspiration", response_class=HTMLResponse)
async def toggle_inspiration(
    request: Request,
    character_id: UUID,
    current_user: UserSession = Depends(require_login),
    service: CharacterService = Depends(_service),
    db: AsyncSession = Depends(get_db),
):
    try:
        character = await service.toggle_inspiration(
            character_id, current_user.user_id, current_user.is_dm
        )
    except (CharacterNotFound, CharacterPermissionError):
        return error_response(request, 403, language=current_user.language)

    await db.refresh(character, ["campaigns"])

    return render_template(
        templates,
        "characters/_sheet_header.html",
        {
            "request": request,
            "current_user": current_user,
            "character": character,
            "sheet": character.sheet_data,
            "campaigns": character.campaigns,
            "can_edit": _can_edit(current_user, character),
        },
        language=current_user.language,
    )


# ── Vitals: Spell slots ───────────────────────────────────────────────────

@router.post("/{character_id}/vitals/spell-slot", response_class=HTMLResponse)
async def update_spell_slot(
    request: Request,
    character_id: UUID,
    current_user: UserSession = Depends(require_login),
    service: CharacterService = Depends(_service),
):
    form = await request.form()
    payload = SpellSlotUpdate(
        level=int(form.get("level")),
        delta=int(form.get("delta")),
    )

    try:
        character = await service.update_spell_slot(
            character_id, current_user.user_id, current_user.is_dm, payload
        )
    except (CharacterNotFound, CharacterPermissionError):
        return error_response(request, 403, language=current_user.language)

    return render_template(
        templates,
        "characters/_sheet_body.html",
        {
            "request": request,
            "current_user": current_user,
            "character": character,
            "sheet": character.sheet_data,
            "can_edit": _can_edit(current_user, character),
        },
        language=current_user.language,
    )


# ── Vitals: Temp HP ───────────────────────────────────────────────────────

@router.post("/{character_id}/vitals/temp-hp", response_class=HTMLResponse)
async def update_temp_hp(
    request: Request,
    character_id: UUID,
    current_user: UserSession = Depends(require_login),
    service: CharacterService = Depends(_service),
):
    form = await request.form()
    payload = TempHPUpdate(
        delta=form.get("delta"),
        value=form.get("value"),
    )

    try:
        character = await service.update_temp_hp(
            character_id, current_user.user_id, current_user.is_dm,
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
            "character": character,
            "sheet": character.sheet_data,
            "can_edit": _can_edit(current_user, character),
        },
        language=current_user.language,
    )


# ── Vitals: Max HP (DM only) ──────────────────────────────────────────────

@router.post("/{character_id}/vitals/max-hp", response_class=HTMLResponse)
async def update_max_hp(
    request: Request,
    character_id: UUID,
    current_user: UserSession = Depends(require_dm),
    service: CharacterService = Depends(_service),
):
    form = await request.form()
    payload = MaxHPUpdate(value=form.get("value", 1))

    try:
        character = await service.update_max_hp(
            character_id, current_user.user_id, current_user.is_dm,
            payload.value,
        )
    except (CharacterNotFound, CharacterPermissionError):
        return error_response(request, 403, language=current_user.language)

    return render_template(
        templates,
        "characters/_vitals.html",
        {
            "request": request,
            "current_user": current_user,
            "character": character,
            "sheet": character.sheet_data,
            "can_edit": True,
        },
        language=current_user.language,
    )


# ── Vitals: Shield ────────────────────────────────────────────────────────

@router.post("/{character_id}/vitals/shield", response_class=HTMLResponse)
async def toggle_shield(
    request: Request,
    character_id: UUID,
    current_user: UserSession = Depends(require_login),
    service: CharacterService = Depends(_service),
):
    try:
        character = await service.toggle_shield(
            character_id, current_user.user_id, current_user.is_dm
        )
    except (CharacterNotFound, CharacterPermissionError):
        return error_response(request, 403, language=current_user.language)

    return render_template(
        templates,
        "characters/_vitals.html",
        {
            "request": request,
            "current_user": current_user,
            "character": character,
            "sheet": character.sheet_data,
            "can_edit": _can_edit(current_user, character),
        },
        language=current_user.language,
    )


# ── Vitals: Defenses ──────────────────────────────────────────────────────

@router.post("/{character_id}/vitals/defenses", response_class=HTMLResponse)
async def update_defenses(
    request: Request,
    character_id: UUID,
    defenses: str = Form(""),
    current_user: UserSession = Depends(require_login),
    service: CharacterService = Depends(_service),
):
    try:
        character = await service.update_defenses(
            character_id, defenses, current_user.user_id, current_user.is_dm
        )
    except (CharacterNotFound, CharacterPermissionError):
        return error_response(request, 403, language=current_user.language)

    return render_template(
        templates,
        "characters/_vitals.html",
        {
            "request": request,
            "current_user": current_user,
            "character": character,
            "sheet": character.sheet_data,
            "can_edit": _can_edit(current_user, character),
        },
        language=current_user.language,
    )


# ── Vitals: Conditions ────────────────────────────────────────────────────

@router.post("/{character_id}/vitals/conditions", response_class=HTMLResponse)
async def update_conditions(
    request: Request,
    character_id: UUID,
    current_user: UserSession = Depends(require_login),
    service: CharacterService = Depends(_service),
):
    form = await request.form()
    conditions = form.getlist("conditions")

    try:
        character = await service.update_conditions(
            character_id, conditions, current_user.user_id, current_user.is_dm
        )
    except (CharacterNotFound, CharacterPermissionError):
        return error_response(request, 403, language=current_user.language)

    return render_template(
        templates,
        "characters/_sheet_body.html",
        {
            "request": request,
            "current_user": current_user,
            "character": character,
            "sheet": character.sheet_data,
            "can_edit": _can_edit(current_user, character),
        },
        language=current_user.language,
    )


# ── Inventory: Throwable case item quantity ────────────────────────────────

@router.post("/{character_id}/inventory/throwable-case-qty", response_class=HTMLResponse)
async def update_throwable_case_qty(
    request: Request,
    character_id: UUID,
    current_user: UserSession = Depends(require_login),
    service: CharacterService = Depends(_service),
):
    form = await request.form()
    payload = ThrowableCaseQtyUpdate(
        case_index=form.get("case_index", 0),
        item_index=form.get("item_index", 0),
        delta=form.get("delta", 0),
    )

    try:
        character = await service.update_throwable_case_quantity(
            character_id, current_user.user_id, current_user.is_dm,
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
            "character": character,
            "sheet": character.sheet_data,
            "can_edit": _can_edit(current_user, character),
        },
        language=current_user.language,
    )


# ── Assign owner (DM only) ────────────────────────────────────────────────

@router.post("/{character_id}/assign", response_class=HTMLResponse)
async def assign_character_owner(
    character_id: UUID,
    player_id: str = Form(""),
    current_user: UserSession = Depends(require_dm),
    service: CharacterService = Depends(_service),
):
    parsed_player_id = UUID(player_id) if player_id else None

    try:
        await service.assign_owner(character_id, parsed_player_id)
    except CharacterNotFound:
        pass

    return RedirectResponse(
        url=f"/characters/{character_id}",
        status_code=status.HTTP_303_SEE_OTHER,
    )


# ── Portrait Upload ───────────────────────────────────────────────────────

ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png"}
ALLOWED_MIME_TYPES = {"image/jpeg", "image/png"}
MAX_PORTRAIT_SIZE = 5_242_880  # 5MB

MIME_TYPE_MAP = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
}


@router.get("/{character_id}/portrait/upload", response_class=HTMLResponse)
async def portrait_upload_form(
    request: Request,
    character_id: UUID,
    current_user: UserSession = Depends(require_login),
    service: CharacterService = Depends(_service),
):
    """Display portrait upload modal"""
    try:
        character = await service.get_character(
            character_id, current_user.user_id, current_user.is_dm
        )
    except CharacterNotFound:
        return error_response(request, 404, language=current_user.language)
    
    # Check if user can edit
    if not _can_edit(current_user, character):
        return error_response(request, 403, language=current_user.language)
    
    return render_template(
        templates,
        "characters/_portrait_upload_modal.html",
        {
            "request": request,
            "character": character,
        },
        language=current_user.language,
    )


@router.post("/{character_id}/portrait/upload", response_class=HTMLResponse)
async def upload_portrait(
    request: Request,
    character_id: UUID,
    file: UploadFile = File(...),
    current_user: UserSession = Depends(require_login),
    service: CharacterService = Depends(_service),
):
    """Handle portrait image upload and store in database"""
    try:
        character = await service.get_character(
            character_id, current_user.user_id, current_user.is_dm
        )
    except CharacterNotFound:
        return error_response(request, 404, language=current_user.language)
    
    # Check if user can edit this character
    if not _can_edit(current_user, character):
        return error_response(request, 403, language=current_user.language)

    # Validate file extension
    file_ext = Path(file.filename).suffix.lower()
    if file_ext not in ALLOWED_EXTENSIONS:
        return render_template(
            templates,
            "characters/_portrait_upload_modal.html",
            {
                "request": request,
                "character": character,
                "error": "Only JPEG and PNG files are allowed.",
            },
            language=current_user.language,
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        )

    # Read and validate file size
    contents = await file.read(MAX_PORTRAIT_SIZE + 1)
    if len(contents) > MAX_PORTRAIT_SIZE:
        return render_template(
            templates,
            "characters/_portrait_upload_modal.html",
            {
                "request": request,
                "character": character,
                "error": "File too large. Maximum size is 5MB.",
            },
            language=current_user.language,
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        )

    # Get MIME type
    mime_type = MIME_TYPE_MAP.get(file_ext, "image/jpeg")

    # Save portrait data to database
    try:
        updated_character = await service.update_portrait(character_id, contents, mime_type)
        return render_template(
            templates,
            "characters/_sheet_header.html",
            {
                "request": request,
                "current_user": current_user,
                "character": updated_character,
                "sheet": updated_character.sheet_data,
                "can_edit": _can_edit(current_user, updated_character),
            },
            language=current_user.language,
        )
    except CharacterNotFound as e:
        return render_template(
            templates,
            "characters/_portrait_upload_modal.html",
            {
                "request": request,
                "character": character,
                "error": f"Error uploading portrait: {str(e)}",
            },
            language=current_user.language,
            status_code=status.HTTP_404_NOT_FOUND,
        )


@router.get("/{character_id}/portrait", response_class=Response)
async def get_portrait(
    request: Request,
    character_id: UUID,
    current_user: UserSession = Depends(require_login),
    service: CharacterService = Depends(_service),
):
    """Retrieve portrait image from database"""
    try:
        character = await service.get_character(
            character_id, current_user.user_id, current_user.is_dm
        )
    except CharacterNotFound:
        return error_response(request, 404, language=current_user.language)

    # Return portrait from database
    if character.portrait_data:
        return Response(
            content=character.portrait_data,
            media_type=character.portrait_mime_type or "image/jpeg",
        )
    else:
        return error_response(request, 404, error_message="No portrait found.", language=current_user.language)

