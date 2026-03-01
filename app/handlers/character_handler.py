import json
import os
from uuid import UUID
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile, status
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession
from app.services.player_service import PlayerService, PlayerNotFound

from app.database import get_db
from app.middleware.auth import require_dm, require_login
from app.schemas.auth import UserSession
from app.schemas.character import HPUpdate, DeathSaveUpdate, SpellSlotUpdate, validate_mandatory_fields
from app.services.character_service import (
    CharacterNotFound,
    CharacterPermissionError,
    CharacterService,
)

router = APIRouter(prefix="/characters", tags=["Characters"])
templates = Jinja2Templates(directory="app/templates")


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
    return templates.TemplateResponse("characters/list.html", {
        "request": request,
        "current_user": current_user,
        "characters": characters,
    })


# ── Upload form ───────────────────────────────────────────────────────────

@router.get("/upload", response_class=HTMLResponse)
async def upload_form(
    request: Request,
    current_user: UserSession = Depends(require_dm),
):
    return templates.TemplateResponse("characters/upload.html", {
        "request": request,
        "current_user": current_user,
        "error": None,
    })


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
        return templates.TemplateResponse(
            "characters/upload.html",
            {"request": request, "current_user": current_user,
             "error": "File too large. Maximum size is 1MB."},
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        )

    try:
        data = json.loads(contents.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return templates.TemplateResponse(
            "characters/upload.html",
            {"request": request, "current_user": current_user,
             "error": "Invalid JSON file. Please upload a valid character sheet."},
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        )

    errors = validate_mandatory_fields(data)
    if errors:
        return templates.TemplateResponse(
            "characters/upload.html",
            {"request": request, "current_user": current_user,
             "error": "Validation failed: " + "; ".join(errors)},
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        )

    # create the character after normalization/validation; if the DB write
    # succeeds we'll simply redirect.  Any template errors will be caught later
    # when the user views the sheet (and our character_sheet handler now
    # displays a helpful message).
    character = await service.create(
        sheet_data=data,
        owner_id=UUID(current_user.user_id),
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
            character_id, UUID(current_user.user_id), current_user.is_dm
        )
    except CharacterNotFound:
        return RedirectResponse(url="/characters", status_code=status.HTTP_303_SEE_OTHER)

    if current_user.is_dm:
        await db.refresh(character, ["share_links"])

    # Load players for assignment dropdown (DM only)
    players = await player_service.list_players() if current_user.is_dm else []

    # produce the template; construction of TemplateResponse already renders
    # the Jinja template, so wrap instantiation in try/except to catch any
    # rendering issues.
    try:
        resp = templates.TemplateResponse("characters/sheet.html", {
            "request": request,
            "current_user": current_user,
            "character": character,
            "sheet": character.sheet_data,
            "players": players,
            "can_edit": current_user.is_dm or str(character.owner_id) == current_user.user_id,
        })
        return resp
    except Exception as e:
        return templates.TemplateResponse("characters/upload.html", {
            "request": request,
            "current_user": current_user,
            "errors": [f"Unable to display character: {e}"]
        }, status_code=status.HTTP_500_INTERNAL_SERVER_ERROR)

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
            character_id, UUID(current_user.user_id), current_user.is_dm
        )
    except CharacterNotFound:
        return RedirectResponse(url="/characters", status_code=status.HTTP_303_SEE_OTHER)

    # Check if user can edit (DM or character owner)
    can_edit = current_user.is_dm or str(character.owner_id) == current_user.user_id
    if not can_edit:
        return RedirectResponse(url=f"/characters/{character_id}", status_code=status.HTTP_303_SEE_OTHER)

    return templates.TemplateResponse("characters/edit.html", {
        "request": request,
        "current_user": current_user,
        "character": character,
        "sheet": character.sheet_data,
    })


@router.post("/{character_id}/edit", response_class=HTMLResponse)
async def edit_character_submit(
    request: Request,
    character_id: UUID,
    current_user: UserSession = Depends(require_login),
    service: CharacterService = Depends(_service),
):
    try:
        character = await service.get_character(
            character_id, UUID(current_user.user_id), current_user.is_dm
        )
    except CharacterNotFound:
        return RedirectResponse(url="/campaigns", status_code=status.HTTP_303_SEE_OTHER)

    # Check if user can edit
    can_edit = current_user.is_dm or str(character.owner_id) == current_user.user_id
    if not can_edit:
        return RedirectResponse(url=f"/characters/{character_id}", status_code=status.HTTP_303_SEE_OTHER)

    form = await request.form()
    
    # Build the updated sheet data from form
    try:
        updated_sheet = await service.build_sheet_from_form(character, form)
        errors = validate_mandatory_fields(updated_sheet)
        
        if errors:
            return templates.TemplateResponse(
                "characters/edit.html",
                {
                    "request": request,
                    "current_user": current_user,
                    "character": character,
                    "sheet": character.sheet_data,
                    "error": "Validation failed: " + "; ".join(errors),
                },
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            )
        
        await service.update_sheet_data(character_id, updated_sheet)
        return RedirectResponse(
            url=f"/characters/{character_id}",
            status_code=status.HTTP_303_SEE_OTHER,
        )
    except Exception as e:
        return templates.TemplateResponse(
            "characters/edit.html",
            {
                "request": request,
                "current_user": current_user,
                "character": character,
                "sheet": character.sheet_data,
                "error": f"Error updating character: {str(e)}",
            },
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
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
            character_id, UUID(current_user.user_id), current_user.is_dm, payload
        )
    except (CharacterNotFound, CharacterPermissionError):
        return HTMLResponse("Forbidden", status_code=403)

    return templates.TemplateResponse("characters/_vitals.html", {
        "request": request,
        "current_user": current_user,
        "character": character,
        "sheet": character.sheet_data,
        "can_edit": current_user.is_dm or str(character.owner_id) == current_user.user_id,
    })


# ── Vitals: Death saves ───────────────────────────────────────────────────

@router.post("/{character_id}/vitals/death-save", response_class=HTMLResponse)
async def update_death_save(
    request: Request,
    character_id: UUID,
    current_user: UserSession = Depends(require_login),
    service: CharacterService = Depends(_service),
):
    form = await request.form()
    payload = DeathSaveUpdate(
        save_type=form.get("save_type"),
        action=form.get("action"),
    )

    try:
        character = await service.update_death_save(
            character_id, UUID(current_user.user_id), current_user.is_dm, payload
        )
    except (CharacterNotFound, CharacterPermissionError):
        return HTMLResponse("Forbidden", status_code=403)

    return templates.TemplateResponse("characters/_vitals.html", {
        "request": request,
        "current_user": current_user,
        "character": character,
        "sheet": character.sheet_data,
        "can_edit": current_user.is_dm or str(character.owner_id) == current_user.user_id,
    })


# ── Vitals: Inspiration ───────────────────────────────────────────────────

@router.post("/{character_id}/vitals/inspiration", response_class=HTMLResponse)
async def toggle_inspiration(
    request: Request,
    character_id: UUID,
    current_user: UserSession = Depends(require_login),
    service: CharacterService = Depends(_service),
):
    try:
        character = await service.toggle_inspiration(
            character_id, UUID(current_user.user_id), current_user.is_dm
        )
    except (CharacterNotFound, CharacterPermissionError):
        return HTMLResponse("Forbidden", status_code=403)

    return templates.TemplateResponse("characters/_sheet_header.html", {
        "request": request,
        "current_user": current_user,
        "character": character,
        "sheet": character.sheet_data,
        "can_edit": current_user.is_dm or str(character.owner_id) == current_user.user_id,
    })


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
            character_id, UUID(current_user.user_id), current_user.is_dm, payload
        )
    except (CharacterNotFound, CharacterPermissionError):
        return HTMLResponse("Forbidden", status_code=403)

    return templates.TemplateResponse("characters/_sheet_body.html", {
        "request": request,
        "current_user": current_user,
        "character": character,
        "sheet": character.sheet_data,
        "can_edit": current_user.is_dm or str(character.owner_id) == current_user.user_id,
    })

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

# ── Vitals: Temp HP ───────────────────────────────────────────────────────

@router.post("/{character_id}/vitals/temp-hp", response_class=HTMLResponse)
async def update_temp_hp(
    request: Request,
    character_id: UUID,
    current_user: UserSession = Depends(require_login),
    service: CharacterService = Depends(_service),
):
    form = await request.form()
    delta = int(form["delta"]) if "delta" in form else None
    value = int(form["value"]) if "value" in form else None

    try:
        character = await service.update_temp_hp(
            character_id, UUID(current_user.user_id), current_user.is_dm, delta, value
        )
    except (CharacterNotFound, CharacterPermissionError):
        return HTMLResponse("Forbidden", status_code=403)

    return templates.TemplateResponse("characters/_vitals.html", {
        "request": request,
        "current_user": current_user,
        "character": character,
        "sheet": character.sheet_data,
        "can_edit": current_user.is_dm or str(character.owner_id) == current_user.user_id,
    })


# ── Vitals: Max HP (DM only) ──────────────────────────────────────────────

@router.post("/{character_id}/vitals/max-hp", response_class=HTMLResponse)
async def update_max_hp(
    request: Request,
    character_id: UUID,
    current_user: UserSession = Depends(require_dm),
    service: CharacterService = Depends(_service),
):
    form = await request.form()
    value = int(form.get("value", 1))

    try:
        character = await service.update_max_hp(
            character_id, UUID(current_user.user_id), current_user.is_dm, value
        )
    except (CharacterNotFound, CharacterPermissionError):
        return HTMLResponse("Forbidden", status_code=403)

    return templates.TemplateResponse("characters/_vitals.html", {
        "request": request,
        "current_user": current_user,
        "character": character,
        "sheet": character.sheet_data,
        "can_edit": True,
    })

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
            character_id, UUID(current_user.user_id), current_user.is_dm
        )
    except (CharacterNotFound, CharacterPermissionError):
        return HTMLResponse("Forbidden", status_code=403)

    return templates.TemplateResponse("characters/_vitals.html", {
        "request": request,
        "current_user": current_user,
        "character": character,
        "sheet": character.sheet_data,
        "can_edit": current_user.is_dm or str(character.owner_id) == current_user.user_id,
    })


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
            character_id, UUID(current_user.user_id), current_user.is_dm
        )
    except CharacterNotFound:
        return HTMLResponse("Forbidden", status_code=403)
    
    # Check if user can edit this character
    can_edit = current_user.is_dm or str(character.owner_id) == current_user.user_id
    if not can_edit:
        return HTMLResponse("Forbidden", status_code=403)

    return templates.TemplateResponse("characters/_portrait_upload_modal.html", {
        "request": request,
        "character": character,
    })


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
            character_id, UUID(current_user.user_id), current_user.is_dm
        )
    except CharacterNotFound:
        return HTMLResponse("Forbidden", status_code=403)
    
    # Check if user can edit this character
    can_edit = current_user.is_dm or str(character.owner_id) == current_user.user_id
    if not can_edit:
        return HTMLResponse("Forbidden", status_code=403)

    # Validate file extension
    file_ext = Path(file.filename).suffix.lower()
    if file_ext not in ALLOWED_EXTENSIONS:
        return templates.TemplateResponse(
            "characters/_portrait_upload_modal.html",
            {
                "request": request,
                "character": character,
                "error": "Only JPEG and PNG files are allowed.",
            },
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        )

    # Read and validate file size
    contents = await file.read(MAX_PORTRAIT_SIZE + 1)
    if len(contents) > MAX_PORTRAIT_SIZE:
        return templates.TemplateResponse(
            "characters/_portrait_upload_modal.html",
            {
                "request": request,
                "character": character,
                "error": "File too large. Maximum size is 5MB.",
            },
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        )

    # Get MIME type
    mime_type = MIME_TYPE_MAP.get(file_ext, "image/jpeg")

    # Save portrait data to database
    updated_character = await service.update_portrait(character_id, contents, mime_type)

    # Return updated sheet header which will replace the old one
    return templates.TemplateResponse("characters/_sheet_header.html", {
        "request": request,
        "current_user": current_user,
        "character": updated_character,
        "sheet": updated_character.sheet_data,
        "can_edit": current_user.is_dm or str(updated_character.owner_id) == current_user.user_id,
    })


@router.get("/{character_id}/portrait", response_class=Response)
async def get_portrait(
    character_id: UUID,
    current_user: UserSession = Depends(require_login),
    service: CharacterService = Depends(_service),
):
    """Retrieve portrait image from database"""
    try:
        character = await service.get_character(
            character_id, UUID(current_user.user_id), current_user.is_dm
        )
    except CharacterNotFound:
        return Response("Not Found", status_code=404)

    # Return portrait from database
    if character.portrait_data:
        return Response(
            content=character.portrait_data,
            media_type=character.portrait_mime_type or "image/jpeg",
        )
    else:
        # No portrait uploaded
        return Response("No portrait found", status_code=404)

