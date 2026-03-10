from uuid import UUID

from fastapi import APIRouter, Depends, Form, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import ValidationError

from app.database import get_db
from app.i18n import render_template
from app.middleware.auth import require_dm
from app.schemas.auth import UserSession
from app.schemas.player import PlayerCreate
from app.services.player_service import (
    CharacterNotFound,
    PlayerNotFound,
    PlayerService,
    UsernameAlreadyExists,
)

router = APIRouter(prefix="/players", tags=["Players"])
templates = Jinja2Templates(directory="app/templates")


def _service(db: AsyncSession = Depends(get_db)) -> PlayerService:
    return PlayerService(db)


# ── List ──────────────────────────────────────────────────────────────────

@router.get("", response_class=HTMLResponse)
async def player_list(
    request: Request,
    current_user: UserSession = Depends(require_dm),
    service: PlayerService = Depends(_service),
):
    players = await service.list_players()
    characters = await service.get_all_characters()
    return render_template(templates, "players/list.html", {
        "request": request,
        "current_user": current_user,
        "players": players,
        "characters": characters,
    }, language=current_user.language)


# ── New form ──────────────────────────────────────────────────────────────

@router.get("/new", response_class=HTMLResponse)  # ← was "/players/new"
async def player_new_form(
    request: Request,
    user: UserSession = Depends(require_dm),
):
    return render_template(templates, "players/form.html", {
        "request": request,
        "current_user": user,
        "messages": [],
        "player": None,
        "form": {},
        "errors": {},
        "all_characters": [],
    }, language=user.language)



# ── Create ────────────────────────────────────────────────────────────────

@router.post("", response_class=HTMLResponse)
async def player_create(
    request: Request,
    current_user: UserSession = Depends(require_dm),
    username: str = Form(...),
    password: str = Form(...),
    service: PlayerService = Depends(_service),
):
    errors = {}

    try:
        data = PlayerCreate(username=username, password=password)
    except ValidationError as e:
        for err in e.errors():
            field = err["loc"][0]
            errors[field] = err["msg"].replace("Value error, ", "")

    if not errors:
        try:
            await service.create_player(data)
            return RedirectResponse(url="/players", status_code=status.HTTP_303_SEE_OTHER)
        except UsernameAlreadyExists as e:
            errors["username"] = str(e)

    return render_template(templates, "players/form.html", {
        "request": request,
        "current_user": current_user,
        "messages": [],
        "player": None,
        "form": {"username": username},
        "errors": errors,
        "all_characters": [],
    }, language=current_user.language, status_code=status.HTTP_422_UNPROCESSABLE_ENTITY)


# ── Assign character ──────────────────────────────────────────────────────

@router.post("/{player_id}/assign-character", response_class=HTMLResponse)
async def assign_character(
    player_id: UUID,
    character_id: UUID = Form(...),
    current_user: UserSession = Depends(require_dm),
    service: PlayerService = Depends(_service),
):
    try:
        await service.assign_character(player_id, character_id)
    except (PlayerNotFound, CharacterNotFound):
        pass
    return RedirectResponse(url="/players", status_code=status.HTTP_303_SEE_OTHER)


# ── Delete ────────────────────────────────────────────────────────────────

@router.post("/{player_id}/delete", response_class=HTMLResponse)
async def player_delete(
    player_id: UUID,
    current_user: UserSession = Depends(require_dm),
    service: PlayerService = Depends(_service),
):
    try:
        await service.delete_player(player_id)
    except PlayerNotFound:
        pass
    return RedirectResponse(url="/players", status_code=status.HTTP_303_SEE_OTHER)

# ── Edit form ─────────────────────────────────────────────────────────────

@router.get("/{player_id}/edit", response_class=HTMLResponse)
async def player_edit_form(
    player_id: UUID,
    request: Request,
    current_user: UserSession = Depends(require_dm),
    service: PlayerService = Depends(_service),
):
    try:
        player = await service.get_player(player_id)
    except PlayerNotFound:
        return RedirectResponse(url="/players", status_code=status.HTTP_303_SEE_OTHER)

    all_characters = await service.get_all_characters()
    return render_template(templates, "players/form.html", {
        "request": request,
        "current_user": current_user,
        "player": player,
        "form": {},
        "errors": {},
        "messages": [],
        "all_characters": all_characters,
    }, language=current_user.language)


# ── Update ────────────────────────────────────────────────────────────────

@router.post("/{player_id}/edit", response_class=HTMLResponse)
async def player_update(
    player_id: UUID,
    request: Request,
    current_user: UserSession = Depends(require_dm),
    password: str = Form(""),
    confirm_password: str = Form(""),
    character_id: str = Form(""),
    service: PlayerService = Depends(_service),
):
    errors = {}

    try:
        player = await service.get_player(player_id)
    except PlayerNotFound:
        return RedirectResponse(url="/players", status_code=status.HTTP_303_SEE_OTHER)

    # Validate password only if provided
    if password:
        if len(password) < 8:
            errors["password"] = "Password must be at least 8 characters."
        elif password != confirm_password:
            errors["confirm_password"] = "Passwords do not match."

    if errors:
        all_characters = await service.get_all_characters()
        return render_template(templates, "players/form.html", {
            "request": request,
            "current_user": current_user,
            "player": player,
            "form": {},
            "errors": errors,
            "messages": [],
            "all_characters": all_characters,
        }, language=current_user.language, status_code=status.HTTP_422_UNPROCESSABLE_ENTITY)

    # Update password if provided
    if password:
        await service.update_password(player_id, password)

    # Update character assignment
    parsed_character_id = UUID(character_id) if character_id else None
    await service.assign_character(player_id, parsed_character_id)

    return RedirectResponse(url="/players", status_code=status.HTTP_303_SEE_OTHER)
