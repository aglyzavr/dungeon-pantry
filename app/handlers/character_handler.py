from uuid import UUID

from fastapi import APIRouter, Depends, Form, Request, UploadFile, File, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.middleware.auth import require_dm, require_login
from app.schemas.auth import UserSession
from app.schemas.character import HPUpdate, DeathSaveUpdate, SpellSlotUpdate
from app.services.character_service import (
    CharacterNotFound, CharacterPermissionError,
    CharacterService, CharacterValidationError,
)

router = APIRouter(prefix="/characters", tags=["Characters"])
templates = Jinja2Templates(directory="app/templates")


def _service(db: AsyncSession = Depends(get_db)) -> CharacterService:
    return CharacterService(db)


# ── Pool (DM only) ────────────────────────────────────────────────────────────

@router.get("", response_class=HTMLResponse)
async def character_pool(
    request: Request,
    current_user: UserSession = Depends(require_dm),
    service: CharacterService = Depends(_service),
):
    characters = await service.list_all()
    return templates.TemplateResponse("characters/pool.html", {
        "request": request,
        "current_user": current_user,
        "characters": characters,
    })


# ── Upload (new must be before /{character_id}) ───────────────────────────────

@router.get("/upload", response_class=HTMLResponse)
async def upload_form(
    request: Request,
    current_user: UserSession = Depends(require_dm),
):
    return templates.TemplateResponse("characters/upload.html", {
        "request": request,
        "current_user": current_user,
        "errors": [],
    })


@router.post("/upload", response_class=HTMLResponse)
async def upload_character(
    request: Request,
    current_user: UserSession = Depends(require_dm),
    file: UploadFile = File(...),
    service: CharacterService = Depends(_service),
):
    if not file.filename or not file.filename.endswith(".json"):
        return templates.TemplateResponse(
            "characters/upload.html",
            {"request": request, "current_user": current_user,
             "errors": ["File must be a .json file"]},
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        )

    raw = (await file.read()).decode("utf-8")
    try:
        character = await service.create_from_json_string(
            raw_json=raw, owner_id=UUID(current_user.user_id)
        )
        return RedirectResponse(
            url=f"/characters/{character.id}",
            status_code=status.HTTP_303_SEE_OTHER,
        )
    except CharacterValidationError as e:
        return templates.TemplateResponse(
            "characters/upload.html",
            {"request": request, "current_user": current_user, "errors": e.errors},
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        )


# ── Sheet view ────────────────────────────────────────────────────────────────

@router.get("/{character_id}", response_class=HTMLResponse)
async def character_sheet(
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
    except CharacterPermissionError:
        return RedirectResponse(url="/campaigns", status_code=status.HTTP_303_SEE_OTHER)

    return templates.TemplateResponse("characters/sheet.html", {
        "request": request,
        "current_user": current_user,
        "character": character,
        "sheet": character.sheet_data,
        "can_edit": current_user.is_dm or str(character.owner_id) == current_user.user_id,
    })


# ── Vitals HTMX endpoints ─────────────────────────────────────────────────────

def _vitals_response(request, current_user, character, templates):
    can_edit = current_user.is_dm or str(character.owner_id) == current_user.user_id
    return templates.TemplateResponse("characters/_vitals.html", {
        "request": request,
        "current_user": current_user,
        "character": character,
        "sheet": character.sheet_data,
        "can_edit": can_edit,
    })


@router.post("/{character_id}/vitals/hp", response_class=HTMLResponse)
async def update_hp(
    request: Request,
    character_id: UUID,
    current_user: UserSession = Depends(require_login),
    delta: int | None = Form(None),
    value: int | None = Form(None),
    service: CharacterService = Depends(_service),
):
    character = await service.get_character(character_id, current_user.user_id, current_user.is_dm)
    character = await service.adjust_hp(character, delta=delta, absolute=value)
    return _vitals_response(request, current_user, character, templates)


@router.post("/{character_id}/vitals/death-save", response_class=HTMLResponse)
async def toggle_death_save(
    request: Request,
    character_id: UUID,
    save_type: str = Form(...),
    action: str = Form(...),
    current_user: UserSession = Depends(require_login),
    service: CharacterService = Depends(_service),
):
    character = await service.get_character(character_id, current_user.user_id, current_user.is_dm)
    character = await service.toggle_death_save(character, save_type, action)
    return _vitals_response(request, current_user, character, templates)


@router.post("/{character_id}/vitals/inspiration", response_class=HTMLResponse)
async def toggle_inspiration(
    request: Request,
    character_id: UUID,
    current_user: UserSession = Depends(require_login),
    service: CharacterService = Depends(_service),
):
    character = await service.get_character(character_id, current_user.user_id, current_user.is_dm)
    character = await service.toggle_inspiration(character)
    return _vitals_response(request, current_user, character, templates)


@router.post("/{character_id}/vitals/spell-slot", response_class=HTMLResponse)
async def update_spell_slot(
    request: Request,
    character_id: UUID,
    level: int = Form(...),
    delta: int = Form(...),
    current_user: UserSession = Depends(require_login),
    service: CharacterService = Depends(_service),
):
    character = await service.get_character(character_id, current_user.user_id, current_user.is_dm)
    character = await service.adjust_spell_slot(character, level, delta)
    return _vitals_response(request, current_user, character, templates)


# ── Delete ────────────────────────────────────────────────────────────────────

@router.post("/{character_id}/delete", response_class=HTMLResponse)
async def delete_character(
    character_id: UUID,
    current_user: UserSession = Depends(require_dm),
    service: CharacterService = Depends(_service),
):
    try:
        await service.delete_character(character_id)
    except CharacterNotFound:
        pass
    return RedirectResponse(url="/characters", status_code=status.HTTP_303_SEE_OTHER)
