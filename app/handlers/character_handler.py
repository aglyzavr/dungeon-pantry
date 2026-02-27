import json
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession

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
    db: AsyncSession = Depends(get_db),
):
    try:
        character = await service.get_character(
            character_id, UUID(current_user.user_id), current_user.is_dm
        )
    except CharacterNotFound:
        return RedirectResponse(url="/characters", status_code=status.HTTP_303_SEE_OTHER)
    except CharacterPermissionError:
        return RedirectResponse(url="/campaigns", status_code=status.HTTP_303_SEE_OTHER)

    # Eagerly load share links for DM view
    if current_user.is_dm:
        await db.refresh(character, ["share_links"])

    return templates.TemplateResponse("characters/sheet.html", {
        "request": request,
        "current_user": current_user,
        "character": character,
        "sheet": character.sheet_data,
        "can_edit": current_user.is_dm or str(character.owner_id) == current_user.user_id,
    })


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

    return templates.TemplateResponse("characters/_vitals.html", {
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

    return templates.TemplateResponse("characters/_vitals.html", {
        "request": request,
        "current_user": current_user,
        "character": character,
        "sheet": character.sheet_data,
        "can_edit": current_user.is_dm or str(character.owner_id) == current_user.user_id,
    })
