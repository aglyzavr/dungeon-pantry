import copy
import json
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

from app.models.character import Character, CampaignCharacter
from app.repositories.campaign_repository import CampaignRepository
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
        self._campaign_repo = CampaignRepository(db)

    # D&D 5e canonical skills per ability. Keys must match the dot-access names
    # used in _sheet_body.html (e.g. sheet.dexterity.ability_scores.sleight_of_hand).
    _DEFAULT_SKILLS: dict[str, list[str]] = {
        "strength":     ["athletics"],
        "dexterity":    ["acrobatics", "sleight_of_hand", "stealth"],
        "constitution": [],
        "intelligence": ["arcana", "history", "investigation", "nature", "religion"],
        "wisdom":       ["animal_handling", "insight", "medicine", "perception", "survival"],
        "charisma":     ["deception", "intimidation", "performance", "persuasion"],
    }

    @staticmethod
    def _default_skill_entry() -> dict:
        return {"bonus": 0, "proficient": False, "advantage": "none"}

    @staticmethod
    def _safe_non_negative_int(value, default=0):
        try:
            return max(0, int(value))
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _safe_non_negative_float(value, default=0.0):
        try:
            return max(0.0, float(value))
        except (TypeError, ValueError):
            return default
    
    @staticmethod
    def _blank_sheet() -> dict:
        """Return a blank character sheet skeleton with empty/default values.

        Each call returns an independent copy so callers can mutate freely.
        The returned dict intentionally does NOT pass ``validate_mandatory_fields``
        (empty name, zero max-HP) so the form enforces all required fields.
        """
        return {
            "character_identity": {
                "character_name": "",
                "background": "",
                "class": {"name": "", "subclass": ""},
                "species": {"name": "", "subtype": ""},
            },
            "character_level": {"level": 1, "xp": "0"},
            "armor_class": 10,
            "initiative": "+0",
            "speed": "30 ft",
            "size": "Medium",
            "proficiency_bonus": 2,
            "heroic_inspiration": False,
            "passive_perception": 10,
            "passive_investigation": 10,
            "passive_insight": 10,
            "vitality": {
                "hit_points": {"current": 0, "max": 0, "temp": 0},
                "hit_dice": {"total": "1d8", "spent": "0"},
                "death_saves": {"successes": 0, "failures": 0},
            },
            "strength": {
                "score": 10, "modifier": 0, "saving_throw": 0, "saving_throw_proficient": False,
                "ability_scores": {"athletics": {"bonus": 0, "proficient": False, "advantage": "none"}},
            },
            "dexterity": {
                "score": 10, "modifier": 0, "saving_throw": 0, "saving_throw_proficient": False,
                "ability_scores": {
                    "acrobatics": {"bonus": 0, "proficient": False, "advantage": "none"},
                    "sleight_of_hand": {"bonus": 0, "proficient": False, "advantage": "none"},
                    "stealth": {"bonus": 0, "proficient": False, "advantage": "none"},
                },
            },
            "constitution": {"score": 10, "modifier": 0, "saving_throw": 0, "saving_throw_proficient": False},
            "intelligence": {
                "score": 10, "modifier": 0, "saving_throw": 0, "saving_throw_proficient": False,
                "ability_scores": {
                    "arcana": {"bonus": 0, "proficient": False, "advantage": "none"},
                    "history": {"bonus": 0, "proficient": False, "advantage": "none"},
                    "investigation": {"bonus": 0, "proficient": False, "advantage": "none"},
                    "nature": {"bonus": 0, "proficient": False, "advantage": "none"},
                    "religion": {"bonus": 0, "proficient": False, "advantage": "none"},
                },
            },
            "wisdom": {
                "score": 10, "modifier": 0, "saving_throw": 0, "saving_throw_proficient": False,
                "ability_scores": {
                    "animal_handling": {"bonus": 0, "proficient": False, "advantage": "none"},
                    "insight": {"bonus": 0, "proficient": False, "advantage": "none"},
                    "medicine": {"bonus": 0, "proficient": False, "advantage": "none"},
                    "perception": {"bonus": 0, "proficient": False, "advantage": "none"},
                    "survival": {"bonus": 0, "proficient": False, "advantage": "none"},
                },
            },
            "charisma": {
                "score": 10, "modifier": 0, "saving_throw": 0, "saving_throw_proficient": False,
                "ability_scores": {
                    "deception": {"bonus": 0, "proficient": False, "advantage": "none"},
                    "intimidation": {"bonus": 0, "proficient": False, "advantage": "none"},
                    "performance": {"bonus": 0, "proficient": False, "advantage": "none"},
                    "persuasion": {"bonus": 0, "proficient": False, "advantage": "none"},
                },
            },
            "equipment_training_proficiencies": {"armor_training": [], "weapons": [], "tools": []},
            "languages": "",
            "defenses": "",
            "class_features": "",
            "species_traits": "",
            "feats": "",
            "class_resources": [],
            "appearance": "",
            "backstory_and_personality": {
                "backstory": "",
                "personality": "",
                "alignment": "",
                "ideals": "",
                "bonds": "",
                "flaws": "",
            },
            "equipment": {
                "equipment_list": [],
                "throwable_cases": [],
                "weapons": [],
                "armor": [],
                "magic_item_attunement": [],
            },
            "spell_slots": {},
            "coins": {"cp": 0, "sp": 0, "ep": 0, "gp": 0, "pp": 0},
        }

    @staticmethod
    def _calculate_spell_slots(character_class: str, character_level: int) -> dict:
        """
        Calculate spell slots based on character class and level according to D&D 5e rules.
        Preserves expended slots where possible.
        
        Args:
            character_class: The character's class name
            character_level: The character's level (1-20)
            
        Returns:
            Dictionary with spell slot levels (level_1 through level_9) containing total and expended counts
        """
        # Full caster spell slot progression (Wizard, Sorcerer, Bard, Cleric, Druid)
        FULL_CASTER_SLOTS = {
            1:  [2, 0, 0, 0, 0, 0, 0, 0, 0],
            2:  [3, 0, 0, 0, 0, 0, 0, 0, 0],
            3:  [4, 2, 0, 0, 0, 0, 0, 0, 0],
            4:  [4, 3, 0, 0, 0, 0, 0, 0, 0],
            5:  [4, 3, 2, 0, 0, 0, 0, 0, 0],
            6:  [4, 3, 3, 0, 0, 0, 0, 0, 0],
            7:  [4, 3, 3, 1, 0, 0, 0, 0, 0],
            8:  [4, 3, 3, 2, 0, 0, 0, 0, 0],
            9:  [4, 3, 3, 3, 1, 0, 0, 0, 0],
            10: [4, 3, 3, 3, 2, 0, 0, 0, 0],
            11: [4, 3, 3, 3, 2, 1, 0, 0, 0],
            12: [4, 3, 3, 3, 2, 1, 0, 0, 0],
            13: [4, 3, 3, 3, 2, 1, 1, 0, 0],
            14: [4, 3, 3, 3, 2, 1, 1, 0, 0],
            15: [4, 3, 3, 3, 2, 1, 1, 1, 0],
            16: [4, 3, 3, 3, 2, 1, 1, 1, 0],
            17: [4, 3, 3, 3, 2, 1, 1, 1, 1],
            18: [4, 3, 3, 3, 3, 1, 1, 1, 1],
            19: [4, 3, 3, 3, 3, 2, 1, 1, 1],
            20: [4, 3, 3, 3, 3, 2, 2, 1, 1],
        }
        
        # Class categorization — use exact set membership to avoid false positives
        # (e.g. "bard" matching inside "standard")
        FULL_CASTERS = {'wizard', 'sorcerer', 'bard', 'cleric', 'druid'}
        HALF_CASTERS = {'paladin', 'ranger'}
        THIRD_CASTERS = {'artificer', 'eldritch knight', 'arcane trickster'}
        
        # Normalize class name for comparison
        class_lower = character_class.lower().strip()
        
        # Determine effective caster level
        effective_level = 0
        if class_lower in FULL_CASTERS:
            effective_level = character_level
        elif class_lower in HALF_CASTERS:
            # Half casters start at level 2
            if character_level >= 2:
                effective_level = (character_level + 1) // 2
        elif class_lower in THIRD_CASTERS:
            # Third casters start at level 3
            if character_level >= 3:
                effective_level = (character_level + 2) // 3
        
        # Build spell slots dictionary
        spell_slots = {}
        if effective_level > 0 and effective_level in FULL_CASTER_SLOTS:
            slots_array = FULL_CASTER_SLOTS[effective_level]
            for i, total in enumerate(slots_array, start=1):
                spell_slots[f"level_{i}"] = {
                    "total": total,
                    "expended": 0
                }
        else:
            # Non-caster or level 0 - set all slots to 0
            for i in range(1, 10):
                spell_slots[f"level_{i}"] = {
                    "total": 0,
                    "expended": 0
                }
        
        return spell_slots

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
        """Get a character for viewing. Any logged-in user can view any character."""
        character = await self._repo.get_by_id(character_id)
        if character is None:
            raise CharacterNotFound(f"Character {character_id} not found")
        return character

    def _check_write_permission(self, character: Character, user_id: UUID, is_dm: bool) -> None:
        """Check if user has permission to modify a character.
        Only DMs and the character owner can modify.
        """
        if not is_dm and character.owner_id != user_id:
            raise CharacterPermissionError("You do not have permission to modify this character")

    async def _get_sheet_data(
        self, character_id: UUID, campaign_id: UUID | None = None
    ) -> dict:
        """Get sheet_data for a character, optionally from a campaign context.
        
        Args:
            character_id: The character's ID
            campaign_id: Optional campaign ID. If provided, returns CampaignCharacter.sheet_data.
                        If None, returns Character.sheet_data.
        
        Returns:
            The sheet_data dict
        
        Raises:
            CharacterNotFound if the character or (campaign-)character association doesn't exist
        """
        if campaign_id is not None:
            cc = await self._repo.get_campaign_character(campaign_id, character_id)
            if cc is None:
                raise CharacterNotFound(
                    f"Character {character_id} not found in campaign {campaign_id}"
                )
            return copy.deepcopy(cc.sheet_data)
        else:
            character = await self._repo.get_by_id(character_id)
            if character is None:
                raise CharacterNotFound(f"Character {character_id} not found")
            return copy.deepcopy(character.sheet_data)

    async def _save_sheet_data(
        self, character_id: UUID, sheet_data: dict, campaign_id: UUID | None = None
    ) -> None:
        """Save sheet_data for a character, optionally to a campaign context.
        
        Args:
            character_id: The character's ID
            sheet_data: The new sheet_data to save
            campaign_id: Optional campaign ID. If provided, updates CampaignCharacter.sheet_data.
                        If None, updates Character.sheet_data.
        """
        if campaign_id is not None:
            await self._repo.update_campaign_character_sheet(campaign_id, character_id, sheet_data)
        else:
            character = await self._repo.get_by_id(character_id)
            if character is None:
                raise CharacterNotFound(f"Character {character_id} not found")
            await self._repo.save_sheet_data(character, sheet_data)

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

    async def create_from_upload(self, raw_content: bytes, owner_id: UUID) -> Character:
        """Parse raw uploaded file content as JSON, validate, and create a character."""
        try:
            raw_json = raw_content.decode("utf-8")
        except UnicodeDecodeError:
            raise CharacterValidationError(["Invalid JSON file. Please upload a valid character sheet."])

        try:
            data = json.loads(raw_json)
        except json.JSONDecodeError:
            raise CharacterValidationError(["Invalid JSON file. Please upload a valid character sheet."])

        return await self.create(sheet_data=data, owner_id=owner_id)

    async def adjust_hp(self, character: Character, delta: int | None, absolute: int | None) -> Character:
        data = copy.deepcopy(character.sheet_data)
        hp = data["vitality"]["hit_points"]
        hp_max = int(hp.get("max", 0))
        current = int(hp.get("current", 0))
        temp = int(hp.get("temp", 0) or 0)

        if absolute is not None:
            # set current HP directly (temp unaffected)
            new_current = max(0, min(absolute, hp_max))
        elif delta is not None:
            if delta < 0:
                # taking damage - spend temporary HP first
                dmg = -delta
                if temp >= dmg:
                    # all damage absorbed by temp
                    temp -= dmg
                    dmg = 0
                else:
                    dmg -= temp
                    temp = 0
                new_current = max(0, current - dmg)
            else:
                # healing only affects current HP
                new_current = min(hp_max, current + delta)
        else:
            return character

        hp["current"] = new_current
        hp["temp"] = temp
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
        self._check_write_permission(character, user_id, is_dm)
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

    @staticmethod
    def _apply_short_rest(data: dict) -> None:
        """Restore uses_current to uses_max for all short-rest resources (mutates data in-place)."""
        for res in data.get("class_resources", []):
            if isinstance(res, dict) and res.get("recharge") == "short_rest":
                uses_max = int(res.get("uses_max", 1))
                res["uses_current"] = uses_max

    @staticmethod
    def _apply_long_rest(data: dict) -> None:
        """Apply long-rest recovery rules (mutates data in-place):
        - Restore HP to max, clear temp HP
        - Reset death saves
        - Restore all spell slots (expended -> 0)
        - Restore class resources with recharge in short_rest, long_rest, or dawn
        - Recover half of spent hit dice (minimum 1)
        """
        # HP
        hp = data.get("vitality", {}).get("hit_points", {})
        if isinstance(hp, dict):
            hp_max = int(hp.get("max", 0))
            hp["current"] = hp_max
            hp["temp"] = 0

        # Death saves
        saves = data.get("vitality", {}).get("death_saves", {})
        if isinstance(saves, dict):
            saves["successes"] = 0
            saves["failures"] = 0

        # Spell slots
        spell_slots = data.get("spell_slots", {})
        if isinstance(spell_slots, dict):
            for slot in spell_slots.values():
                if isinstance(slot, dict):
                    slot["expended"] = 0

        # Class resources
        _LONG_REST_RECHARGE = {"short_rest", "long_rest", "dawn"}
        for res in data.get("class_resources", []):
            if isinstance(res, dict) and res.get("recharge") in _LONG_REST_RECHARGE:
                uses_max = int(res.get("uses_max", 1))
                res["uses_current"] = uses_max

        # Hit dice: recover max(1, floor(total_count / 2)) spent dice
        hit_dice = data.get("vitality", {}).get("hit_dice", {})
        if isinstance(hit_dice, dict):
            total_str = str(hit_dice.get("total", "1d8"))
            # Parse "XdY" → X (e.g. "4d8" → 4, "d8" → 1, "1d8" → 1)
            parts = total_str.lower().split("d")
            try:
                count_str = parts[0].strip()
                total_count = int(count_str) if count_str else 1
            except (ValueError, IndexError):
                total_count = 1
            recovery = max(1, total_count // 2)
            spent = int(hit_dice.get("spent", 0))
            hit_dice["spent"] = max(0, spent - recovery)

    async def perform_short_rest(
        self, character_id: UUID, user_id: UUID, is_dm: bool
    ) -> Character:
        character = await self.get_character(character_id, user_id, is_dm)
        self._check_write_permission(character, user_id, is_dm)
        data = copy.deepcopy(character.sheet_data)
        self._apply_short_rest(data)
        return await self._repo.save_sheet_data(character, data)

    async def perform_long_rest(
        self, character_id: UUID, user_id: UUID, is_dm: bool
    ) -> Character:
        character = await self.get_character(character_id, user_id, is_dm)
        self._check_write_permission(character, user_id, is_dm)
        data = copy.deepcopy(character.sheet_data)
        self._apply_long_rest(data)
        return await self._repo.save_sheet_data(character, data)

    async def perform_campaign_short_rest(
        self, campaign_id: UUID, character_id: UUID, user_id: UUID, is_dm: bool
    ) -> CampaignCharacter:
        cc = await self._get_campaign_char_for_write(campaign_id, character_id, user_id, is_dm)
        data = copy.deepcopy(cc.sheet_data)
        self._apply_short_rest(data)
        return await self._flush_campaign_cc(cc, data)

    async def perform_campaign_long_rest(
        self, campaign_id: UUID, character_id: UUID, user_id: UUID, is_dm: bool
    ) -> CampaignCharacter:
        cc = await self._get_campaign_char_for_write(campaign_id, character_id, user_id, is_dm)
        data = copy.deepcopy(cc.sheet_data)
        self._apply_long_rest(data)
        return await self._flush_campaign_cc(cc, data)

    async def use_class_resource(
        self, character_id: UUID, user_id: UUID, is_dm: bool, resource_index: int, delta: int
    ) -> Character:
        character = await self.get_character(character_id, user_id, is_dm)
        self._check_write_permission(character, user_id, is_dm)
        data = copy.deepcopy(character.sheet_data)
        resources = data.get("class_resources", [])
        if 0 <= resource_index < len(resources):
            res = resources[resource_index]
            uses_max = int(res.get("uses_max", 1))
            uses_current = int(res.get("uses_current", uses_max))
            res["uses_current"] = max(0, min(uses_max, uses_current + delta))
        return await self._repo.save_sheet_data(character, data)

    async def update_campaign_class_resource(
        self, campaign_id: UUID, character_id: UUID, user_id: UUID, is_dm: bool,
        resource_index: int, delta: int
    ) -> CampaignCharacter:
        cc = await self._get_campaign_char_for_write(campaign_id, character_id, user_id, is_dm)
        data = copy.deepcopy(cc.sheet_data)
        resources = data.get("class_resources", [])
        if 0 <= resource_index < len(resources):
            res = resources[resource_index]
            uses_max = int(res.get("uses_max", 1))
            uses_current = int(res.get("uses_current", uses_max))
            res["uses_current"] = max(0, min(uses_max, uses_current + delta))
        return await self._flush_campaign_cc(cc, data)

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
        if player_id is None:
            await self._campaign_repo.remove_character_from_all(character_id)
        await self._repo.flush()

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
        equipment = data["equipment"]
        if not isinstance(equipment.get("equipment_list"), list):
            equipment["equipment_list"] = []
        if not isinstance(equipment.get("magic_item_attunement"), list):
            equipment["magic_item_attunement"] = []
        if not isinstance(equipment.get("throwable_cases"), list):
            equipment["throwable_cases"] = []
        if not isinstance(equipment.get("weapons"), list):
            equipment["weapons"] = []
        if not isinstance(equipment.get("armor"), list):
            equipment["armor"] = []

        normalized_armor = []
        for piece in equipment["armor"]:
            if not isinstance(piece, dict):
                continue
            normalized_piece = copy.deepcopy(piece)
            normalized_piece.setdefault("name", "")
            normalized_piece["weight"] = self._safe_non_negative_float(normalized_piece.get("weight", 0), 0.0)
            normalized_piece["armor_class"] = self._safe_non_negative_int(normalized_piece.get("armor_class", 0), 0)
            normalized_piece.setdefault("notes", "")
            normalized_armor.append(normalized_piece)
        equipment["armor"] = normalized_armor

        normalized_weapons = []
        for weapon in equipment["weapons"]:
            if not isinstance(weapon, dict):
                continue
            normalized_weapon = copy.deepcopy(weapon)
            normalized_weapon.setdefault("name", "")
            normalized_weapon["weight"] = self._safe_non_negative_float(normalized_weapon.get("weight", 0), 0.0)
            normalized_weapon.setdefault("damage", "")
            normalized_weapon.setdefault("damage_type", "")
            normalized_weapon.setdefault("properties", "")
            normalized_weapons.append(normalized_weapon)
        equipment["weapons"] = normalized_weapons

        normalized_cases = []
        for case in equipment["throwable_cases"]:
            if not isinstance(case, dict):
                continue
            normalized_case = copy.deepcopy(case)
            normalized_case.setdefault("name", "")
            normalized_case["weight"] = self._safe_non_negative_float(normalized_case.get("weight", 0), 0.0)
            items = normalized_case.get("items", [])
            if not isinstance(items, list):
                items = []
            normalized_items = []
            for item in items:
                if not isinstance(item, dict):
                    continue
                normalized_item = copy.deepcopy(item)
                normalized_item.setdefault("name", "")
                normalized_item["weight"] = self._safe_non_negative_float(normalized_item.get("weight", 0), 0.0)
                normalized_item["quantity"] = self._safe_non_negative_int(normalized_item.get("quantity", 1), 1)
                normalized_items.append(normalized_item)
            normalized_case["items"] = normalized_items
            normalized_cases.append(normalized_case)
        equipment["throwable_cases"] = normalized_cases

        if not isinstance(data.get("spell_slots"), dict):
            data["spell_slots"] = {}
        # coins structure expected by _sheet_body.html
        if not isinstance(data.get("coins"), dict):
            data["coins"] = {"cp": 0, "sp": 0, "ep": 0, "gp": 0, "pp": 0}

        # class_resources list with per-entry normalization
        if not isinstance(data.get("class_resources"), list):
            data["class_resources"] = []
        for res in data["class_resources"]:
            if isinstance(res, dict):
                res.setdefault("name", "")
                res.setdefault("action_type", "none")
                atype = res["action_type"]
                if atype not in ("action", "bonus_action", "reaction", "none"):
                    res["action_type"] = "none"
                res.setdefault("uses_max", 1)
                res.setdefault("uses_current", res["uses_max"])
                res.setdefault("recharge", "")
                res.setdefault("description", "")

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

        # Normalize ability scores — ensure all skills in ability_scores are dicts with proper structure
        for ability_name in ("strength", "dexterity", "constitution", "intelligence", "wisdom", "charisma"):
            ability = data.setdefault(ability_name, {})
            if not isinstance(ability, dict):
                ability = {}
                data[ability_name] = ability

            default_skills = self._DEFAULT_SKILLS.get(ability_name, [])

            # If no ability_scores key yet, seed it with the canonical D&D 5e skills
            if "ability_scores" not in ability and default_skills:
                ability["ability_scores"] = {
                    skill: self._default_skill_entry() for skill in default_skills
                }

            ability_scores = ability.get("ability_scores")
            if isinstance(ability_scores, dict):
                # Ensure every canonical skill exists (add missing ones)
                for skill in default_skills:
                    if skill not in ability_scores:
                        ability_scores[skill] = self._default_skill_entry()

                # Normalise each skill entry
                for skill_name, skill_data in ability_scores.items():
                    if not isinstance(skill_data, dict):
                        ability_scores[skill_name] = {
                            "bonus": int(skill_data) if isinstance(skill_data, (int, float)) else 0,
                            "proficient": False,
                            "advantage": "none",
                        }
                    else:
                        skill_data.setdefault("bonus", 0)
                        skill_data.setdefault("proficient", False)
                        skill_data.setdefault("advantage", "none")

        return data


    async def update_hp(
        self, character_id: UUID, user_id: UUID, is_dm: bool, payload
    ) -> Character:
        character = await self.get_character(character_id, user_id, is_dm)
        self._check_write_permission(character, user_id, is_dm)
        return await self.adjust_hp(character, payload.delta, payload.value)


    async def update_death_save(
        self, character_id: UUID, user_id: UUID, is_dm: bool, payload
    ) -> Character:
        character = await self.get_character(character_id, user_id, is_dm)
        self._check_write_permission(character, user_id, is_dm)
        return await self.toggle_death_save(character, payload.save_type, payload.action)


    async def update_spell_slot(
        self, character_id: UUID, user_id: UUID, is_dm: bool, payload
    ) -> Character:
        character = await self.get_character(character_id, user_id, is_dm)
        self._check_write_permission(character, user_id, is_dm)
        return await self.adjust_spell_slot(character, payload.level, payload.delta)

    async def update_temp_hp(
        self, character_id: UUID, user_id: UUID, is_dm: bool, delta: int | None, absolute: int | None
    ) -> Character:
        character = await self.get_character(character_id, user_id, is_dm)
        self._check_write_permission(character, user_id, is_dm)
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
        self._check_write_permission(character, user_id, is_dm)
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
        self._check_write_permission(character, user_id, is_dm)
        data = copy.deepcopy(character.sheet_data)
        data["shield_equipped"] = not bool(data.get("shield_equipped", False))
        return await self._repo.save_sheet_data(character, data)

    async def update_defenses(
        self, character_id: UUID, defenses: str, user_id: UUID, is_dm: bool
    ) -> Character:
        character = await self.get_character(character_id, user_id, is_dm)
        self._check_write_permission(character, user_id, is_dm)
        data = copy.deepcopy(character.sheet_data)
        data["defenses"] = defenses
        return await self._repo.save_sheet_data(character, data)

    async def update_conditions(
        self, character_id: UUID, conditions: list, user_id: UUID, is_dm: bool
    ) -> Character:
        character = await self.get_character(character_id, user_id, is_dm)
        self._check_write_permission(character, user_id, is_dm)
        data = copy.deepcopy(character.sheet_data)
        data["conditions"] = conditions
        return await self._repo.save_sheet_data(character, data)

    async def update_throwable_case_quantity(
        self, character_id: UUID, user_id: UUID, is_dm: bool,
        case_index: int, item_index: int, delta: int
    ) -> Character:
        """Adjust the quantity of an item in a throwable case by delta."""
        character = await self.get_character(character_id, user_id, is_dm)
        self._check_write_permission(character, user_id, is_dm)
        data = copy.deepcopy(character.sheet_data)
        cases = data.get("equipment", {}).get("throwable_cases", [])
        if 0 <= case_index < len(cases):
            items = cases[case_index].get("items", [])
            if 0 <= item_index < len(items):
                items[item_index]["quantity"] = max(0, int(items[item_index].get("quantity", 0)) + delta)
        return await self._repo.save_sheet_data(character, data)

    async def update_portrait(self, character_id: UUID, portrait_data: bytes, mime_type: str) -> Character:
        """Update character portrait data stored in database"""
        character = await self._repo.get_by_id(character_id)
        if character is None:
            raise CharacterNotFound(f"Character {character_id} not found")
        character.portrait_data = portrait_data
        character.portrait_mime_type = mime_type
        character.portrait_path = None  # Clear legacy field
        await self._repo.flush()
        return character

    async def update_sheet_data(self, character_id: UUID, sheet_data: dict) -> Character:
        """Update the entire character sheet data"""
        character = await self._repo.get_by_id(character_id)
        if character is None:
            raise CharacterNotFound(f"Character {character_id} not found")
        
        errors = validate_mandatory_fields(sheet_data)
        if errors:
            raise CharacterValidationError(errors)
        
        sheet_data = self._normalize_sheet(sheet_data)
        return await self._repo.save_sheet_data(character, sheet_data)

    async def build_sheet_from_form(self, sheet_data: dict, form) -> dict:
        """Build a complete sheet_data dict from the submitted form"""
        sheet = copy.deepcopy(sheet_data)
        
        # Helper to safely get form values
        def get_form(key: str, default=""):
            val = form.get(key, default)
            return val if val != "" else default
        
        def get_int(key: str, default=0):
            try:
                return int(get_form(key, str(default)))
            except (ValueError, TypeError):
                return default
        
        def get_bool(key: str):
            return get_form(key) in ["on", "true", "True", "1"]
        
        # Character Identity
        sheet["character_identity"] = {
            "character_name": get_form("character_name"),
            "background": get_form("background"),
            "class": {
                "name": get_form("class_name"),
                "subclass": get_form("class_subclass", "")
            },
            "species": {
                "name": get_form("species_name"),
                "subtype": get_form("species_subtype", "")
            }
        }
        
        # Character Level
        sheet["character_level"] = {
            "level": get_int("level", 1),
            "xp": get_form("xp", "0")
        }
        
        # Basic stats
        sheet["armor_class"] = get_int("armor_class", 10)
        sheet["initiative"] = get_form("initiative", "+0")
        sheet["speed"] = get_form("speed", "30 ft")
        sheet["size"] = get_form("size", "Medium")
        sheet["proficiency_bonus"] = get_int("proficiency_bonus", 2)
        sheet["heroic_inspiration"] = get_bool("heroic_inspiration")
        
        # Passive senses
        sheet["passive_perception"] = get_int("passive_perception", 10)
        sheet["passive_investigation"] = get_int("passive_investigation", 10)
        sheet["passive_insight"] = get_int("passive_insight", 10)
        
        # Vitality
        sheet["vitality"] = {
            "hit_points": {
                "current": get_int("hp_current", 1),
                "max": get_int("hp_max", 1),
                "temp": get_int("hp_temp", 0)
            },
            "hit_dice": {
                "total": get_form("hit_dice_total", "1d8"),
                "spent": get_form("hit_dice_spent", "0")
            },
            "death_saves": {
                "successes": sheet.get("vitality", {}).get("death_saves", {}).get("successes", 0),
                "failures": sheet.get("vitality", {}).get("death_saves", {}).get("failures", 0)
            }
        }
        
        # Ability scores
        for ability in ["strength", "dexterity", "constitution", "intelligence", "wisdom", "charisma"]:
            score = get_int(f"{ability}_score", 10)
            modifier = get_int(f"{ability}_modifier", 0)
            save_throw = get_int(f"{ability}_save", modifier)
            save_prof = get_bool(f"{ability}_save_prof")
            
            sheet[ability] = {
                "score": score,
                "modifier": modifier,
                "saving_throw": save_throw,
                "saving_throw_proficient": save_prof
            }
            
            # Skills for the ability (if any)
            ability_data = sheet_data.get(ability, {})
            if "ability_scores" in ability_data:
                sheet[ability]["ability_scores"] = {}
                for skill_name in ability_data["ability_scores"].keys():
                    skill_key = f"{ability}_{skill_name.replace(' ', '_').replace('_of_', '_')}"
                    bonus = get_int(f"{skill_key}_bonus", 0)
                    prof = get_bool(f"{skill_key}_prof")
                    advantage = get_form(f"{skill_key}_advantage", "none")
                    if advantage not in ("advantage", "disadvantage"):
                        advantage = "none"
                    
                    sheet[ability]["ability_scores"][skill_name] = {
                        "bonus": bonus,
                        "proficient": prof,
                        "advantage": advantage
                    }
        
        # Equipment & proficiencies
        sheet["equipment_training_proficiencies"] = {
            "armor_training": [x.strip() for x in get_form("armor_training", "").split(",") if x.strip()],
            "weapons": [x.strip() for x in get_form("weapons", "").split(",") if x.strip()],
            "tools": [x.strip() for x in get_form("tools", "").split(",") if x.strip()]
        }
        
        # Languages
        sheet["languages"] = get_form("languages", "")
        
        # Defenses
        sheet["defenses"] = get_form("defenses", "")
        
        # Features and traits
        sheet["class_features"] = get_form("class_features", "")
        sheet["species_traits"] = get_form("species_traits", "")
        sheet["feats"] = get_form("feats", "")

        # Class resources (submitted as JSON from the edit form)
        resources_raw = str(get_form("class_resources_json", "")).strip()
        if resources_raw:
            try:
                submitted_resources = json.loads(resources_raw)
            except (json.JSONDecodeError, TypeError):
                submitted_resources = None
            if isinstance(submitted_resources, list):
                normalized_resources = []
                for res in submitted_resources:
                    if not isinstance(res, dict):
                        continue
                    res_name = str(res.get("name", "")).strip()
                    if not res_name:
                        continue
                    atype = str(res.get("action_type", "")).strip()
                    if atype not in ("action", "bonus_action", "reaction", "none"):
                        atype = "none"
                    try:
                        uses_max = max(1, int(res.get("uses_max", 1)))
                    except (TypeError, ValueError):
                        uses_max = 1
                    try:
                        uses_current = max(0, min(uses_max, int(res.get("uses_current", uses_max))))
                    except (TypeError, ValueError):
                        uses_current = uses_max
                    normalized_resources.append({
                        "name": res_name,
                        "action_type": atype,
                        "uses_max": uses_max,
                        "uses_current": uses_current,
                        "recharge": str(res.get("recharge", "")).strip(),
                        "description": str(res.get("description", "")).strip(),
                    })
                sheet["class_resources"] = normalized_resources
        else:
            sheet["class_resources"] = sheet_data.get("class_resources", [])
        
        # Appearance and backstory
        sheet["appearance"] = get_form("appearance", "")
        sheet["backstory_and_personality"] = {
            "backstory": get_form("backstory", ""),
            "personality": get_form("personality", ""),
            "alignment": get_form("alignment", ""),
            "ideals": get_form("ideals", ""),
            "bonds": get_form("bonds", ""),
            "flaws": get_form("flaws", ""),
        }
        
        # Equipment
        equipment_list = [x.strip() for x in get_form("equipment_list", "").split(",") if x.strip()]

        # Throwable cases (submitted as JSON from the edit form)
        throwable_cases = []
        cases_raw = str(get_form("throwable_cases_json", "")).strip()
        if cases_raw:
            try:
                submitted_cases = json.loads(cases_raw)
            except (json.JSONDecodeError, TypeError):
                submitted_cases = None
            if isinstance(submitted_cases, list):
                for case in submitted_cases:
                    if not isinstance(case, dict):
                        continue
                    case_name = str(case.get("name", "")).strip()
                    if not case_name:
                        continue
                    case_weight = self._safe_non_negative_float(case.get("weight", 0), 0.0)
                    items = []
                    for item in (case.get("items") or []):
                        if not isinstance(item, dict):
                            continue
                        item_name = str(item.get("name", "")).strip()
                        if not item_name:
                            continue
                        item_weight = self._safe_non_negative_float(item.get("weight", 0), 0.0)
                        items.append({
                            "name": item_name,
                            "quantity": self._safe_non_negative_int(item.get("quantity", 0), 0),
                            "weight": item_weight,
                            "note": str(item.get("note", "")).strip(),
                        })
                    throwable_cases.append({"name": case_name, "weight": case_weight, "items": items})
        else:
            throwable_cases = sheet.get("equipment", {}).get("throwable_cases", [])

        # Weapons (submitted as JSON from the edit form)
        weapons = []
        weapons_raw = str(get_form("weapons_json", "")).strip()
        if weapons_raw:
            try:
                submitted_weapons = json.loads(weapons_raw)
            except (json.JSONDecodeError, TypeError):
                submitted_weapons = None
            if isinstance(submitted_weapons, list):
                for weapon in submitted_weapons:
                    if not isinstance(weapon, dict):
                        continue
                    weapon_name = str(weapon.get("name", "")).strip()
                    if not weapon_name:
                        continue
                    w_action_type = str(weapon.get("action_type", "")).strip()
                    if w_action_type not in ("action", "bonus_action", "reaction", "none"):
                        w_action_type = "none"
                    weapon_weight = self._safe_non_negative_float(weapon.get("weight", 0), 0.0)
                    weapons.append({
                        "name": weapon_name,
                        "damage": str(weapon.get("damage", "")).strip(),
                        "damage_type": str(weapon.get("damage_type", "")).strip(),
                        "properties": str(weapon.get("properties", "")).strip(),
                        "range": str(weapon.get("range", "")).strip(),
                        "atk_bonus": str(weapon.get("atk_bonus", "")).strip(),
                        "weight": weapon_weight,
                        "action_type": w_action_type,
                    })
        else:
            weapons = sheet.get("equipment", {}).get("weapons", [])

        # Armor (submitted as JSON from the edit form)
        armor = []
        armor_raw = str(get_form("armor_json", "")).strip()
        if armor_raw:
            try:
                submitted_armor = json.loads(armor_raw)
            except (json.JSONDecodeError, TypeError):
                submitted_armor = None
            if isinstance(submitted_armor, list):
                for piece in submitted_armor:
                    if not isinstance(piece, dict):
                        continue
                    piece_name = str(piece.get("name", "")).strip()
                    if not piece_name:
                        continue
                    piece_weight = self._safe_non_negative_float(piece.get("weight", 0), 0.0)
                    piece_ac = self._safe_non_negative_int(piece.get("armor_class", 0), 0)
                    armor.append({
                        "name": piece_name,
                        "weight": piece_weight,
                        "armor_class": piece_ac,
                        "notes": str(piece.get("notes", "")).strip(),
                    })
        else:
            armor = sheet.get("equipment", {}).get("armor", [])

        sheet["equipment"] = {
            "equipment_list": equipment_list,
            "magic_item_attunement": sheet.get("equipment", {}).get("magic_item_attunement", []),
            "throwable_cases": throwable_cases,
            "weapons": weapons,
            "armor": armor,
        }
        
        # Coins
        sheet["coins"] = {
            "cp": get_int("coins_cp", 0),
            "sp": get_int("coins_sp", 0),
            "ep": get_int("coins_ep", 0),
            "gp": get_int("coins_gp", 0),
            "pp": get_int("coins_pp", 0)
        }

        # Spells (submitted as JSON from the edit form)
        spells_raw = str(get_form("spells_json", "")).strip()
        if spells_raw:
            try:
                submitted_spells = json.loads(spells_raw)
            except (json.JSONDecodeError, TypeError):
                submitted_spells = None

            if isinstance(submitted_spells, list):
                normalized_spells = []
                for spell in submitted_spells:
                    if not isinstance(spell, dict):
                        continue

                    name = str(spell.get("name", "")).strip()
                    if not name:
                        continue

                    raw_level = str(spell.get("level", "0")).strip()
                    level = int(raw_level) if raw_level.isdigit() else (raw_level.lower() or "0")

                    crrm = spell.get("crrm") if isinstance(spell.get("crrm"), dict) else {}
                    action_type = str(spell.get("action_type", "")).strip()
                    if action_type not in ("action", "bonus_action", "reaction", "none"):
                        action_type = "bonus_action" if spell.get("bonus_action") else "none"
                    normalized_spells.append(
                        {
                            "name": name,
                            "level": level,
                            "attack_save": str(spell.get("attack_save", "")).strip(),
                            "casting_time": str(spell.get("casting_time", "")).strip(),
                            "range": str(spell.get("range", "")).strip(),
                            "components": str(spell.get("components", "")).strip(),
                            "duration": str(spell.get("duration", "")).strip(),
                            "notes": str(spell.get("notes", "")).strip(),
                            "action_type": action_type,
                            "crrm": {
                                "concentration": bool(crrm.get("concentration", False)),
                                "ritual": bool(crrm.get("ritual", False)),
                            },
                        }
                    )

                sheet["cantrips_and_prepared_spells"] = normalized_spells
        
        # Attacks & Cantrips (submitted as JSON from the edit form)
        attacks_raw = str(get_form("attacks_json", "")).strip()
        if attacks_raw:
            try:
                submitted_attacks = json.loads(attacks_raw)
            except (json.JSONDecodeError, TypeError):
                submitted_attacks = []

            if isinstance(submitted_attacks, list):
                normalized_attacks = []
                for attack in submitted_attacks:
                    if not isinstance(attack, dict):
                        continue

                    name = str(attack.get("name", "")).strip()
                    if not name:
                        continue

                    action_type = str(attack.get("action_type", "")).strip()
                    if action_type not in ("action", "bonus_action", "reaction"):
                        action_type = "bonus_action" if attack.get("bonus_action") else "action"

                    source_type = str(attack.get("source_type", "")).strip()
                    if source_type not in ("manual", "spell", "equipment"):
                        source_type = "manual"

                    normalized_attacks.append(
                        {
                            "name": name,
                            "atk_bonus_or_dc": str(attack.get("atk_bonus_or_dc", "")).strip(),
                            "damage_and_type": str(attack.get("damage_and_type", "")).strip(),
                            "range": str(attack.get("range", "")).strip(),
                            "notes": str(attack.get("notes", "")).strip(),
                            "action_type": action_type,
                            "source_type": source_type,
                            "source_name": str(attack.get("source_name", "")).strip(),
                        }
                    )

                sheet["weapons_damage_cantrips"] = normalized_attacks
        else:
            # Preserve existing attacks if no attack data was submitted
            if "weapons_damage_cantrips" in sheet_data:
                sheet["weapons_damage_cantrips"] = sheet_data["weapons_damage_cantrips"]
        
        # Parse spell slot totals from the form (user-specified; no auto-calculation from class/level)
        spell_slots_json_str = str(form.get("spell_slots_json", "")).strip()
        old_spell_slots = sheet_data.get("spell_slots", {})
        if spell_slots_json_str:
            try:
                totals = json.loads(spell_slots_json_str)
                if isinstance(totals, list):
                    new_slots = {}
                    for i, raw_total in enumerate(totals[:9], start=1):
                        key = f"level_{i}"
                        total = max(0, min(99, int(raw_total or 0)))
                        old_expended = int((old_spell_slots.get(key) or {}).get("expended", 0))
                        new_slots[key] = {
                            "total": total,
                            "expended": min(old_expended, total),
                        }
                    sheet["spell_slots"] = new_slots
                else:
                    sheet["spell_slots"] = old_spell_slots
            except (json.JSONDecodeError, ValueError, TypeError):
                sheet["spell_slots"] = old_spell_slots
        else:
            sheet["spell_slots"] = old_spell_slots
        
        # Preserve other existing complex structures (spellcasting ability, etc.)
        # Note: weapons_damage_cantrips is now handled via the attacks_json form field
        for key in ["spellcasting_ability"]:
            if key in sheet_data:
                sheet[key] = sheet_data[key]
        
        return sheet

    # ── Campaign-specific write helpers ───────────────────────────────────────

    async def _get_campaign_char_for_write(
        self, campaign_id: UUID, character_id: UUID, user_id: UUID, is_dm: bool
    ) -> CampaignCharacter:
        """Load CampaignCharacter with character+campaign eagerly loaded and check write permission."""
        cc = await self._campaign_repo.get_campaign_character_with_association(campaign_id, character_id)
        if cc is None:
            raise CharacterNotFound(
                f"Character {character_id} not found in campaign {campaign_id}"
            )
        self._check_write_permission(cc.character, user_id, is_dm)
        return cc

    async def _flush_campaign_cc(self, cc: CampaignCharacter, data: dict) -> CampaignCharacter:
        """Persist updated sheet_data on a CampaignCharacter and return it."""
        cc.sheet_data = data
        flag_modified(cc, "sheet_data")
        await self._repo.flush()
        return cc

    # ── Campaign-aware update methods ─────────────────────────────────────────

    async def update_campaign_hp(
        self, campaign_id: UUID, character_id: UUID, user_id: UUID, is_dm: bool, payload
    ) -> CampaignCharacter:
        cc = await self._get_campaign_char_for_write(campaign_id, character_id, user_id, is_dm)
        data = copy.deepcopy(cc.sheet_data)
        hp = data["vitality"]["hit_points"]
        hp_max = int(hp.get("max", 0))
        current = int(hp.get("current", 0))
        temp = int(hp.get("temp", 0) or 0)
        if payload.value is not None:
            hp["current"] = max(0, min(payload.value, hp_max))
        elif payload.delta is not None:
            delta = payload.delta
            if delta < 0:
                dmg = -delta
                if temp >= dmg:
                    temp -= dmg
                    dmg = 0
                else:
                    dmg -= temp
                    temp = 0
                hp["current"] = max(0, current - dmg)
            else:
                hp["current"] = min(hp_max, current + delta)
            hp["temp"] = temp
        return await self._flush_campaign_cc(cc, data)

    async def update_campaign_death_save(
        self, campaign_id: UUID, character_id: UUID, user_id: UUID, is_dm: bool, payload
    ) -> CampaignCharacter:
        cc = await self._get_campaign_char_for_write(campaign_id, character_id, user_id, is_dm)
        if payload.save_type not in ("successes", "failures"):
            return cc
        data = copy.deepcopy(cc.sheet_data)
        saves = data["vitality"]["death_saves"]
        current = int(saves.get(payload.save_type, 0))
        if payload.action == "add":
            saves[payload.save_type] = min(3, current + 1)
        elif payload.action == "remove":
            saves[payload.save_type] = max(0, current - 1)
        return await self._flush_campaign_cc(cc, data)

    async def toggle_campaign_inspiration(
        self, campaign_id: UUID, character_id: UUID, user_id: UUID, is_dm: bool
    ) -> CampaignCharacter:
        cc = await self._get_campaign_char_for_write(campaign_id, character_id, user_id, is_dm)
        data = copy.deepcopy(cc.sheet_data)
        data["heroic_inspiration"] = not bool(data.get("heroic_inspiration", False))
        return await self._flush_campaign_cc(cc, data)

    async def update_campaign_spell_slot(
        self, campaign_id: UUID, character_id: UUID, user_id: UUID, is_dm: bool, payload
    ) -> CampaignCharacter:
        cc = await self._get_campaign_char_for_write(campaign_id, character_id, user_id, is_dm)
        data = copy.deepcopy(cc.sheet_data)
        key = f"level_{payload.level}"
        if "spell_slots" not in data or not isinstance(data.get("spell_slots"), dict):
            data["spell_slots"] = {}
        slot = data.get("spell_slots", {}).get(key, {})
        total = int(slot.get("total", 0))
        current = int(slot.get("expended", 0))
        slot["expended"] = max(0, min(total, current + payload.delta))
        data["spell_slots"][key] = slot
        return await self._flush_campaign_cc(cc, data)

    async def update_campaign_temp_hp(
        self, campaign_id: UUID, character_id: UUID, user_id: UUID, is_dm: bool,
        delta: int | None, absolute: int | None
    ) -> CampaignCharacter:
        cc = await self._get_campaign_char_for_write(campaign_id, character_id, user_id, is_dm)
        data = copy.deepcopy(cc.sheet_data)
        hp = data["vitality"]["hit_points"]
        current_temp = int(hp.get("temp") or 0)
        if absolute is not None:
            hp["temp"] = max(0, absolute)
        elif delta is not None:
            hp["temp"] = max(0, current_temp + delta)
        return await self._flush_campaign_cc(cc, data)

    async def update_campaign_max_hp(
        self, campaign_id: UUID, character_id: UUID, user_id: UUID, is_dm: bool, value: int
    ) -> CampaignCharacter:
        cc = await self._get_campaign_char_for_write(campaign_id, character_id, user_id, is_dm)
        data = copy.deepcopy(cc.sheet_data)
        hp = data["vitality"]["hit_points"]
        hp["max"] = max(1, value)
        hp["current"] = min(int(hp.get("current", 0)), hp["max"])
        return await self._flush_campaign_cc(cc, data)

    async def toggle_campaign_shield(
        self, campaign_id: UUID, character_id: UUID, user_id: UUID, is_dm: bool
    ) -> CampaignCharacter:
        cc = await self._get_campaign_char_for_write(campaign_id, character_id, user_id, is_dm)
        data = copy.deepcopy(cc.sheet_data)
        data["shield_equipped"] = not bool(data.get("shield_equipped", False))
        return await self._flush_campaign_cc(cc, data)

    async def update_campaign_defenses(
        self, campaign_id: UUID, character_id: UUID, defenses: str, user_id: UUID, is_dm: bool
    ) -> CampaignCharacter:
        cc = await self._get_campaign_char_for_write(campaign_id, character_id, user_id, is_dm)
        data = copy.deepcopy(cc.sheet_data)
        data["defenses"] = defenses
        return await self._flush_campaign_cc(cc, data)

    async def update_campaign_conditions(
        self, campaign_id: UUID, character_id: UUID, conditions: list, user_id: UUID, is_dm: bool
    ) -> CampaignCharacter:
        cc = await self._get_campaign_char_for_write(campaign_id, character_id, user_id, is_dm)
        data = copy.deepcopy(cc.sheet_data)
        data["conditions"] = conditions
        return await self._flush_campaign_cc(cc, data)

    async def update_campaign_throwable_case_quantity(
        self, campaign_id: UUID, character_id: UUID, user_id: UUID, is_dm: bool,
        case_index: int, item_index: int, delta: int
    ) -> CampaignCharacter:
        cc = await self._get_campaign_char_for_write(campaign_id, character_id, user_id, is_dm)
        data = copy.deepcopy(cc.sheet_data)
        cases = data.get("equipment", {}).get("throwable_cases", [])
        if 0 <= case_index < len(cases):
            items = cases[case_index].get("items", [])
            if 0 <= item_index < len(items):
                items[item_index]["quantity"] = max(
                    0, int(items[item_index].get("quantity", 0)) + delta
                )
        return await self._flush_campaign_cc(cc, data)

    async def update_campaign_sheet_data(
        self, campaign_id: UUID, character_id: UUID, sheet_data: dict, user_id: UUID, is_dm: bool
    ) -> CampaignCharacter:
        """Replace the entire campaign-specific sheet with validated data."""
        cc = await self._get_campaign_char_for_write(campaign_id, character_id, user_id, is_dm)
        errors = validate_mandatory_fields(sheet_data)
        if errors:
            raise CharacterValidationError(errors)
        sheet_data = self._normalize_sheet(sheet_data)
        return await self._flush_campaign_cc(cc, sheet_data)

    async def update_campaign_portrait(
        self, campaign_id: UUID, character_id: UUID,
        portrait_data: bytes, mime_type: str, user_id: UUID, is_dm: bool
    ) -> CampaignCharacter:
        """Store a portrait image on the campaign-specific character instance."""
        cc = await self._get_campaign_char_for_write(campaign_id, character_id, user_id, is_dm)
        cc.portrait_data = portrait_data
        cc.portrait_mime_type = mime_type
        await self._repo.flush()
        return cc
