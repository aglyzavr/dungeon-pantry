import copy
import json
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.character import Character
from app.repositories.character_repository import CharacterRepository
from app.schemas.character import validate_mandatory_fields


class CharacterNotFound(Exception):
    pass


class CharacterPermissionError(Exception):
    pass


class CharacterValidationError(Exception):
    def __init__(self, errors: list[str]):
        self.errors = errors
        super().__init__(", ".join(errors))


class CharacterService:
    def __init__(self, db: AsyncSession):
        self._repo = CharacterRepository(db)

    async def list_all(self) -> list[Character]:
        return await self._repo.get_all()

    async def list_for_user(self, user_id: UUID) -> list[Character]:
        return await self._repo.get_by_owner(user_id)

    async def get_character(self, character_id: UUID, requesting_user_id: str, is_dm: bool) -> Character:
        character = await self._repo.get_by_id(character_id)
        if character is None:
            raise CharacterNotFound(f"Character {character_id} not found")
        if not is_dm and str(character.owner_id) != requesting_user_id:
            raise CharacterPermissionError("You do not have access to this character")
        return character

    async def create_from_json_string(self, raw_json: str, owner_id: UUID) -> Character:
        try:
            data = json.loads(raw_json)
        except json.JSONDecodeError as e:
            raise CharacterValidationError([f"Invalid JSON: {e}"])

        errors = validate_mandatory_fields(data)
        if errors:
            raise CharacterValidationError(errors)

        return await self._repo.create(owner_id=owner_id, sheet_data=data)

    async def adjust_hp(self, character: Character, delta: int | None, absolute: int | None) -> Character:
        data = copy.deepcopy(character.sheet_data)
        hp = data["vitality"]["hit_points"]
        hp_max = int(hp.get("max", 0))

        if absolute is not None:
            new_hp = max(0, min(absolute, hp_max))
        elif delta is not None:
            new_hp = max(0, min(int(hp.get("current", 0)) + delta, hp_max))
        else:
            return character

        hp["current"] = new_hp
        return await self._repo.save_sheet_data(character, data)

    async def toggle_death_save(self, character: Character, save_type: str, action: str) -> Character:
        if save_type not in ("successes", "failures"):
            return character
        data = copy.deepcopy(character.sheet_data)
        saves = data["vitality"]["death_saves"]
        current = int(saves.get(save_type, 0))
        if action == "add":
            saves[save_type] = min(3, current + 1)
        elif action == "remove":
            saves[save_type] = max(0, current - 1)
        return await self._repo.save_sheet_data(character, data)

    async def toggle_inspiration(self, character: Character) -> Character:
        data = copy.deepcopy(character.sheet_data)
        data["heroic_inspiration"] = not bool(data.get("heroic_inspiration", False))
        return await self._repo.save_sheet_data(character, data)

    async def adjust_spell_slot(self, character: Character, level: int, delta: int) -> Character:
        data = copy.deepcopy(character.sheet_data)
        key = f"level_{level}"
        slot = data.get("spell_slots", {}).get(key, {})
        total = int(slot.get("total", 0))
        current = int(slot.get("expended", 0))
        slot["expended"] = max(0, min(total, current + delta))
        data["spell_slots"][key] = slot
        return await self._repo.save_sheet_data(character, data)

    async def delete_character(self, character_id: UUID) -> None:
        character = await self._repo.get_by_id(character_id)
        if character is None:
            raise CharacterNotFound(f"Character {character_id} not found")
        await self._repo.delete(character)
