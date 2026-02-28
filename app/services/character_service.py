import copy
import json
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.character import Character
from app.repositories.character_repository import CharacterRepository
from app.schemas.character import validate_mandatory_fields
from sqlalchemy import select


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

    async def get_character(
        self,
        character_id: UUID,
        requesting_user_id: UUID,  # ← was str
        is_dm: bool,
    ) -> Character:
        character = await self._repo.get_by_id(character_id)
        if character is None:
            raise CharacterNotFound(f"Character {character_id} not found")
        if not is_dm and character.owner_id != requesting_user_id:  # ← UUID == UUID
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

        data = self._normalize_sheet(data)
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

    async def toggle_inspiration(
        self, character_id: UUID, user_id: UUID, is_dm: bool
    ) -> Character:
        character = await self.get_character(character_id, user_id, is_dm)
        return await self._toggle_inspiration(character)


    async def _toggle_inspiration(self, character: Character) -> Character:
        data = copy.deepcopy(character.sheet_data)
        data["heroic_inspiration"] = not bool(data.get("heroic_inspiration", False))
        return await self._repo.save_sheet_data(character, data)


    async def adjust_spell_slot(self, character: Character, level: int, delta: int) -> Character:
        data = copy.deepcopy(character.sheet_data)
        key = f"level_{level}"
        # ensure the outer dict exists so we can assign into it
        if "spell_slots" not in data or not isinstance(data.get("spell_slots"), dict):
            data["spell_slots"] = {}
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

    async def assign_owner(
        self, character_id: UUID, player_id: UUID | None
    ) -> None:
        character = await self._repo.get_by_id(character_id)
        if character is None:
            raise CharacterNotFound(f"Character {character_id} not found")
        character.owner_id = player_id
        await self._repo._db.flush()

    async def create(self, sheet_data: dict, owner_id: UUID) -> Character:
        errors = validate_mandatory_fields(sheet_data)
        if errors:
            raise CharacterValidationError(errors)
        sheet_data = self._normalize_sheet(sheet_data)
        return await self._repo.create(owner_id=owner_id, sheet_data=sheet_data)


    async def delete(self, character_id: UUID) -> None:
        await self.delete_character(character_id)

    def _normalize_sheet(self, data: dict) -> dict:
        """Ensure the sheet has all of the top‑level structures the templates
        expect.  Missing fields are populated with sensible defaults so that
        rendering later never raises ``UndefinedError``.
        """
        # shallow copy to avoid mutating caller
        data = copy.deepcopy(data)

        # generic container defaults
        if not isinstance(data.get("backstory_and_personality"), dict):
            data["backstory_and_personality"] = {}
        if not isinstance(data.get("equipment"), dict):
            data["equipment"] = {"equipment_list": [], "magic_item_attunement": []}
        if not isinstance(data.get("spell_slots"), dict):
            data["spell_slots"] = {}
        # coins structure expected by _sheet_body.html
        if not isinstance(data.get("coins"), dict):
            data["coins"] = {"cp": 0, "sp": 0, "ep": 0, "gp": 0, "pp": 0}

        # spellcasting ability may be null/absent, that's fine

        # languages used directly in template
        if "languages" not in data:
            data["languages"] = []

        # ensure nested dicts under vitality
        if not isinstance(data.get("vitality"), dict):
            data["vitality"] = {}
        if not isinstance(data["vitality"].get("hit_points"), dict):
            data["vitality"]["hit_points"] = {"current": 0, "max": 0, "temp": 0}
        if not isinstance(data["vitality"].get("death_saves"), dict):
            data["vitality"]["death_saves"] = {"successes": 0, "failures": 0}

        return data


    async def update_hp(
        self, character_id: UUID, user_id: UUID, is_dm: bool, payload
    ) -> Character:
        character = await self.get_character(character_id, user_id, is_dm)
        return await self.adjust_hp(character, payload.delta, payload.value)


    async def update_death_save(
        self, character_id: UUID, user_id: UUID, is_dm: bool, payload
    ) -> Character:
        character = await self.get_character(character_id, user_id, is_dm)
        return await self.toggle_death_save(character, payload.save_type, payload.action)


    async def update_spell_slot(
        self, character_id: UUID, user_id: UUID, is_dm: bool, payload
    ) -> Character:
        character = await self.get_character(character_id, user_id, is_dm)
        return await self.adjust_spell_slot(character, payload.level, payload.delta)

    async def update_temp_hp(
        self, character_id: UUID, user_id: UUID, is_dm: bool, delta: int | None, absolute: int | None
    ) -> Character:
        character = await self.get_character(character_id, user_id, is_dm)
        data = copy.deepcopy(character.sheet_data)
        hp = data["vitality"]["hit_points"]
        current_temp = int(hp.get("temp") or 0)

        if absolute is not None:
            hp["temp"] = max(0, absolute)
        elif delta is not None:
            hp["temp"] = max(0, current_temp + delta)

        return await self._repo.save_sheet_data(character, data)


    async def update_max_hp(
        self, character_id: UUID, user_id: UUID, is_dm: bool, value: int
    ) -> Character:
        character = await self.get_character(character_id, user_id, is_dm)
        data = copy.deepcopy(character.sheet_data)
        hp = data["vitality"]["hit_points"]
        hp["max"] = max(1, value)
        # Clamp current HP to new max
        hp["current"] = min(int(hp.get("current", 0)), hp["max"])
        return await self._repo.save_sheet_data(character, data)

    async def toggle_shield(
        self, character_id: UUID, user_id: UUID, is_dm: bool
    ) -> Character:
        character = await self.get_character(character_id, user_id, is_dm)
        data = copy.deepcopy(character.sheet_data)
        data["shield_equipped"] = not bool(data.get("shield_equipped", False))
        return await self._repo.save_sheet_data(character, data)
