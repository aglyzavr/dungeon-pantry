from uuid import UUID

from fastapi import APIRouter, Depends, Form, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import ValidationError

from app.database import get_db
from app.middleware.auth import require_dm
from app.schemas.auth import UserSession
from app.schemas.player import PlayerCreate
from app.services.player_service import (
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
    return templates.TemplateResponse("players/list.html", {
        "request": request,
        "current_user": current_user,
        "players": players,
        "characters": characters,
    })


# ── New form ──────────────────────────────────────────────────────────────

@router.get("/new", response_class=HTMLResponse)  # ← was "/players/new"
async def player_new_form(
    request: Request,
    user: UserSession = Depends(require_dm),
):
    return templates.TemplateResponse("players/form.html", {
        "request": request,
        "current_user": user,
        "messages": [],
        "player": None,
        "form": {},
        "errors": {},
        "all_characters": [],
    })



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

    return templates.TemplateResponse("players/form.html", {
        "request": request,
        "current_user": current_user,
        "messages": [],
        "player": None,
        "form": {"username": username},
        "errors": errors,
        "all_characters": [],
    }, status_code=status.HTTP_422_UNPROCESSABLE_ENTITY)


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
    except PlayerNotFound:
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
