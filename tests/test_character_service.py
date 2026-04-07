"""Tests for CharacterService business logic (no live database required).

All repository calls are replaced with AsyncMock so these tests run without
a PostgreSQL connection.
"""
import copy
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.character_service import (
    CharacterPermissionError,
    CharacterService,
    CharacterValidationError,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_character(sheet_data: dict | None = None, owner_id: uuid.UUID | None = None):
    char = MagicMock()
    char.id = uuid.uuid4()
    char.owner_id = owner_id or uuid.uuid4()
    char.sheet_data = sheet_data or _base_sheet()
    return char


def _base_sheet() -> dict:
    return {
        "character_identity": {
            "character_name": "Test Hero",
            "class": {"name": "Fighter"},
            "species": {"name": "Human"},
        },
        "character_level": {"level": 5},
        "vitality": {
            "hit_points": {"current": 30, "max": 40, "temp": 0},
            "death_saves": {"successes": 0, "failures": 0},
        },
        "heroic_inspiration": False,
        "spell_slots": {
            "level_1": {"total": 4, "expended": 1},
            "level_2": {"total": 3, "expended": 0},
        },
        "equipment": {"throwable_cases": [], "weapons": []},
    }


def _make_service():
    """Return a CharacterService with all DB calls mocked out."""
    db = AsyncMock()
    service = CharacterService(db)
    service._repo = AsyncMock()
    service._campaign_repo = AsyncMock()
    return service


# ---------------------------------------------------------------------------
# _calculate_spell_slots (static method — pure logic)
# ---------------------------------------------------------------------------


class TestCalculateSpellSlots:
    def _calc(self, cls: str, level: int) -> dict:
        return CharacterService._calculate_spell_slots(cls, level)

    # Full casters
    def test_wizard_level_1(self):
        slots = self._calc("wizard", 1)
        assert slots["level_1"]["total"] == 2
        assert slots["level_1"]["expended"] == 0

    def test_wizard_level_5(self):
        slots = self._calc("wizard", 5)
        assert slots["level_1"]["total"] == 4
        assert slots["level_3"]["total"] == 2

    def test_wizard_level_20(self):
        slots = self._calc("wizard", 20)
        assert slots["level_9"]["total"] == 1

    def test_cleric_is_full_caster(self):
        slots = self._calc("cleric", 3)
        assert slots["level_2"]["total"] == 2

    def test_bard_is_full_caster(self):
        slots = self._calc("bard", 3)
        assert slots["level_1"]["total"] == 4

    # Half casters
    def test_paladin_level_1_no_slots(self):
        slots = self._calc("paladin", 1)
        assert all(v["total"] == 0 for v in slots.values())

    def test_paladin_level_2_has_slots(self):
        slots = self._calc("paladin", 2)
        assert slots["level_1"]["total"] == 2

    def test_ranger_level_5(self):
        slots = self._calc("ranger", 5)
        assert slots["level_1"]["total"] == 4

    # Third casters
    def test_artificer_level_1_no_slots(self):
        slots = self._calc("artificer", 1)
        assert all(v["total"] == 0 for v in slots.values())

    def test_artificer_level_3_has_slots(self):
        slots = self._calc("artificer", 3)
        assert slots["level_1"]["total"] == 2

    # Non-caster
    def test_fighter_has_no_slots(self):
        slots = self._calc("fighter", 10)
        assert all(v["total"] == 0 for v in slots.values())

    def test_non_caster_returns_all_nine_levels(self):
        slots = self._calc("barbarian", 5)
        assert len(slots) == 9

    def test_full_caster_returns_all_nine_levels(self):
        slots = self._calc("wizard", 9)
        assert len(slots) == 9

    def test_expended_initialised_to_zero(self):
        slots = self._calc("sorcerer", 5)
        assert all(v["expended"] == 0 for v in slots.values())


# ---------------------------------------------------------------------------
# _normalize_sheet (instance method but doesn't touch DB)
# ---------------------------------------------------------------------------


class TestNormalizeSheet:
    def setup_method(self):
        self.service = _make_service()

    def test_adds_missing_vitality(self):
        result = self.service._normalize_sheet({})
        assert "vitality" in result
        assert "hit_points" in result["vitality"]

    def test_adds_coins_defaults(self):
        result = self.service._normalize_sheet({})
        assert result["coins"] == {"cp": 0, "sp": 0, "ep": 0, "gp": 0, "pp": 0}

    def test_does_not_overwrite_existing_coins(self):
        data = {"coins": {"cp": 5, "sp": 10, "ep": 0, "gp": 100, "pp": 2}}
        result = self.service._normalize_sheet(data)
        assert result["coins"]["gp"] == 100

    def test_adds_spell_slots_if_missing(self):
        result = self.service._normalize_sheet({})
        assert result["spell_slots"] == {}

    def test_adds_languages_if_missing(self):
        result = self.service._normalize_sheet({})
        assert result["languages"] == []

    def test_does_not_mutate_original(self):
        original = {"coins": {"gp": 99}}
        self.service._normalize_sheet(original)
        assert original == {"coins": {"gp": 99}}

    def test_normalises_flat_skill_data(self):
        data = {
            "strength": {
                "ability_scores": {
                    "athletics": 3
                }
            }
        }
        result = self.service._normalize_sheet(data)
        athletics = result["strength"]["ability_scores"]["athletics"]
        assert isinstance(athletics, dict)
        assert athletics["bonus"] == 3
        assert athletics["proficient"] is False
        assert athletics["advantage"] == "none"

    def test_normalises_skill_missing_keys(self):
        data = {
            "dexterity": {
                "ability_scores": {
                    "acrobatics": {"bonus": 4}
                }
            }
        }
        result = self.service._normalize_sheet(data)
        acrobatics = result["dexterity"]["ability_scores"]["acrobatics"]
        assert acrobatics["proficient"] is False
        assert acrobatics["advantage"] == "none"

    def test_adds_throwable_cases_if_missing(self):
        data = {"equipment": {}}
        result = self.service._normalize_sheet(data)
        assert result["equipment"]["throwable_cases"] == []

    def test_adds_weapons_if_missing(self):
        data = {"equipment": {}}
        result = self.service._normalize_sheet(data)
        assert result["equipment"]["weapons"] == []

    def test_backfills_legacy_equipment_item_fields(self):
        data = {
            "equipment": {
                "armor": [{"name": "Chain Mail"}],
                "weapons": [{"name": "Longsword", "damage": "1d8"}],
                "throwable_cases": [
                    {"name": "Quiver", "items": [{"name": "Arrow"}]}
                ],
            }
        }

        result = self.service._normalize_sheet(data)

        armor = result["equipment"]["armor"][0]
        weapon = result["equipment"]["weapons"][0]
        thrown_item = result["equipment"]["throwable_cases"][0]["items"][0]

        assert armor["weight"] == 0
        assert armor["armor_class"] == 0
        assert armor["notes"] == ""
        assert weapon["weight"] == 0
        assert weapon["properties"] == ""
        assert thrown_item["weight"] == 0
        assert thrown_item["quantity"] == 1

    def test_seeds_ability_scores_when_missing(self):
        """Abilities without ability_scores must get the canonical D&D 5e skill list."""
        result = self.service._normalize_sheet({})
        assert "ability_scores" in result["strength"]
        assert "athletics" in result["strength"]["ability_scores"]
        assert "ability_scores" in result["dexterity"]
        assert "acrobatics" in result["dexterity"]["ability_scores"]
        assert "sleight_of_hand" in result["dexterity"]["ability_scores"]
        assert "stealth" in result["dexterity"]["ability_scores"]

    def test_constitution_gets_no_ability_scores(self):
        """Constitution has no D&D 5e skills; ability_scores must not be created."""
        result = self.service._normalize_sheet({})
        assert "ability_scores" not in result.get("constitution", {})

    def test_wisdom_skills_seeded(self):
        result = self.service._normalize_sheet({})
        scores = result["wisdom"]["ability_scores"]
        for skill in ("animal_handling", "insight", "medicine", "perception", "survival"):
            assert skill in scores
            assert scores[skill] == {"bonus": 0, "proficient": False, "advantage": "none"}

    def test_seeded_skills_have_correct_defaults(self):
        result = self.service._normalize_sheet({})
        entry = result["dexterity"]["ability_scores"]["stealth"]
        assert entry["bonus"] == 0
        assert entry["proficient"] is False
        assert entry["advantage"] == "none"

    def test_existing_skills_not_overwritten(self):
        data = {
            "dexterity": {
                "score": 16,
                "ability_scores": {
                    "stealth": {"bonus": 5, "proficient": True, "advantage": "advantage"}
                },
            }
        }
        result = self.service._normalize_sheet(data)
        stealth = result["dexterity"]["ability_scores"]["stealth"]
        assert stealth["bonus"] == 5
        assert stealth["proficient"] is True
        assert stealth["advantage"] == "advantage"

    def test_missing_canonical_skills_added_to_existing_ability_scores(self):
        """If only some skills are present, the missing canonical ones should be added."""
        data = {
            "dexterity": {
                "ability_scores": {
                    "acrobatics": {"bonus": 3, "proficient": True, "advantage": "none"}
                }
            }
        }
        result = self.service._normalize_sheet(data)
        scores = result["dexterity"]["ability_scores"]
        assert "acrobatics" in scores
        assert scores["acrobatics"]["bonus"] == 3  # unchanged
        assert "sleight_of_hand" in scores  # added
        assert "stealth" in scores  # added


# ---------------------------------------------------------------------------
# adjust_hp
# ---------------------------------------------------------------------------


class TestAdjustHp:
    def setup_method(self):
        self.service = _make_service()

    @pytest.mark.asyncio
    async def test_heal_increases_current(self):
        char = _make_character()
        char.sheet_data["vitality"]["hit_points"] = {"current": 20, "max": 40, "temp": 0}
        saved = MagicMock()
        saved.sheet_data = copy.deepcopy(char.sheet_data)
        saved.sheet_data["vitality"]["hit_points"]["current"] = 30
        self.service._repo.save_sheet_data = AsyncMock(return_value=saved)

        result = await self.service.adjust_hp(char, delta=10, absolute=None)
        call_args = self.service._repo.save_sheet_data.call_args
        new_data = call_args[0][1]
        assert new_data["vitality"]["hit_points"]["current"] == 30

    @pytest.mark.asyncio
    async def test_heal_does_not_exceed_max(self):
        char = _make_character()
        char.sheet_data["vitality"]["hit_points"] = {"current": 38, "max": 40, "temp": 0}
        self.service._repo.save_sheet_data = AsyncMock(return_value=char)

        await self.service.adjust_hp(char, delta=10, absolute=None)
        new_data = self.service._repo.save_sheet_data.call_args[0][1]
        assert new_data["vitality"]["hit_points"]["current"] == 40

    @pytest.mark.asyncio
    async def test_damage_reduces_current(self):
        char = _make_character()
        char.sheet_data["vitality"]["hit_points"] = {"current": 30, "max": 40, "temp": 0}
        self.service._repo.save_sheet_data = AsyncMock(return_value=char)

        await self.service.adjust_hp(char, delta=-5, absolute=None)
        new_data = self.service._repo.save_sheet_data.call_args[0][1]
        assert new_data["vitality"]["hit_points"]["current"] == 25

    @pytest.mark.asyncio
    async def test_damage_does_not_go_below_zero(self):
        char = _make_character()
        char.sheet_data["vitality"]["hit_points"] = {"current": 3, "max": 40, "temp": 0}
        self.service._repo.save_sheet_data = AsyncMock(return_value=char)

        await self.service.adjust_hp(char, delta=-10, absolute=None)
        new_data = self.service._repo.save_sheet_data.call_args[0][1]
        assert new_data["vitality"]["hit_points"]["current"] == 0

    @pytest.mark.asyncio
    async def test_temp_hp_absorbs_damage_first(self):
        char = _make_character()
        char.sheet_data["vitality"]["hit_points"] = {"current": 30, "max": 40, "temp": 5}
        self.service._repo.save_sheet_data = AsyncMock(return_value=char)

        await self.service.adjust_hp(char, delta=-3, absolute=None)
        new_data = self.service._repo.save_sheet_data.call_args[0][1]
        hp = new_data["vitality"]["hit_points"]
        assert hp["temp"] == 2
        assert hp["current"] == 30

    @pytest.mark.asyncio
    async def test_temp_hp_fully_consumed_remainder_hits_current(self):
        char = _make_character()
        char.sheet_data["vitality"]["hit_points"] = {"current": 30, "max": 40, "temp": 5}
        self.service._repo.save_sheet_data = AsyncMock(return_value=char)

        await self.service.adjust_hp(char, delta=-8, absolute=None)
        new_data = self.service._repo.save_sheet_data.call_args[0][1]
        hp = new_data["vitality"]["hit_points"]
        assert hp["temp"] == 0
        assert hp["current"] == 27

    @pytest.mark.asyncio
    async def test_absolute_sets_current(self):
        char = _make_character()
        char.sheet_data["vitality"]["hit_points"] = {"current": 10, "max": 40, "temp": 5}
        self.service._repo.save_sheet_data = AsyncMock(return_value=char)

        await self.service.adjust_hp(char, delta=None, absolute=25)
        new_data = self.service._repo.save_sheet_data.call_args[0][1]
        assert new_data["vitality"]["hit_points"]["current"] == 25

    @pytest.mark.asyncio
    async def test_absolute_clamps_to_max(self):
        char = _make_character()
        char.sheet_data["vitality"]["hit_points"] = {"current": 10, "max": 40, "temp": 5}
        self.service._repo.save_sheet_data = AsyncMock(return_value=char)

        await self.service.adjust_hp(char, delta=None, absolute=999)
        new_data = self.service._repo.save_sheet_data.call_args[0][1]
        assert new_data["vitality"]["hit_points"]["current"] == 40

    @pytest.mark.asyncio
    async def test_absolute_clamps_to_zero(self):
        char = _make_character()
        char.sheet_data["vitality"]["hit_points"] = {"current": 10, "max": 40, "temp": 5}
        self.service._repo.save_sheet_data = AsyncMock(return_value=char)

        await self.service.adjust_hp(char, delta=None, absolute=-5)
        new_data = self.service._repo.save_sheet_data.call_args[0][1]
        assert new_data["vitality"]["hit_points"]["current"] == 0

    @pytest.mark.asyncio
    async def test_absolute_does_not_affect_temp(self):
        char = _make_character()
        char.sheet_data["vitality"]["hit_points"] = {"current": 10, "max": 40, "temp": 5}
        self.service._repo.save_sheet_data = AsyncMock(return_value=char)

        await self.service.adjust_hp(char, delta=None, absolute=20)
        new_data = self.service._repo.save_sheet_data.call_args[0][1]
        assert new_data["vitality"]["hit_points"]["temp"] == 5

    @pytest.mark.asyncio
    async def test_no_delta_no_absolute_returns_unchanged(self):
        char = _make_character()
        result = await self.service.adjust_hp(char, delta=None, absolute=None)
        assert result is char
        self.service._repo.save_sheet_data.assert_not_called()


# ---------------------------------------------------------------------------
# toggle_death_save
# ---------------------------------------------------------------------------


class TestToggleDeathSave:
    def setup_method(self):
        self.service = _make_service()

    @pytest.mark.asyncio
    async def test_add_success(self):
        char = _make_character()
        char.sheet_data["vitality"]["death_saves"] = {"successes": 1, "failures": 0}
        self.service._repo.save_sheet_data = AsyncMock(return_value=char)

        await self.service.toggle_death_save(char, "successes", "add")
        new_data = self.service._repo.save_sheet_data.call_args[0][1]
        assert new_data["vitality"]["death_saves"]["successes"] == 2

    @pytest.mark.asyncio
    async def test_add_success_caps_at_3(self):
        char = _make_character()
        char.sheet_data["vitality"]["death_saves"] = {"successes": 3, "failures": 0}
        self.service._repo.save_sheet_data = AsyncMock(return_value=char)

        await self.service.toggle_death_save(char, "successes", "add")
        new_data = self.service._repo.save_sheet_data.call_args[0][1]
        assert new_data["vitality"]["death_saves"]["successes"] == 3

    @pytest.mark.asyncio
    async def test_remove_failure(self):
        char = _make_character()
        char.sheet_data["vitality"]["death_saves"] = {"successes": 0, "failures": 2}
        self.service._repo.save_sheet_data = AsyncMock(return_value=char)

        await self.service.toggle_death_save(char, "failures", "remove")
        new_data = self.service._repo.save_sheet_data.call_args[0][1]
        assert new_data["vitality"]["death_saves"]["failures"] == 1

    @pytest.mark.asyncio
    async def test_remove_floors_at_0(self):
        char = _make_character()
        char.sheet_data["vitality"]["death_saves"] = {"successes": 0, "failures": 0}
        self.service._repo.save_sheet_data = AsyncMock(return_value=char)

        await self.service.toggle_death_save(char, "failures", "remove")
        new_data = self.service._repo.save_sheet_data.call_args[0][1]
        assert new_data["vitality"]["death_saves"]["failures"] == 0

    @pytest.mark.asyncio
    async def test_invalid_save_type_returns_unchanged(self):
        char = _make_character()
        result = await self.service.toggle_death_save(char, "invalid_type", "add")
        assert result is char
        self.service._repo.save_sheet_data.assert_not_called()


# ---------------------------------------------------------------------------
# adjust_spell_slot
# ---------------------------------------------------------------------------


class TestAdjustSpellSlot:
    def setup_method(self):
        self.service = _make_service()

    @pytest.mark.asyncio
    async def test_expend_slot(self):
        char = _make_character()
        char.sheet_data["spell_slots"] = {"level_1": {"total": 4, "expended": 1}}
        self.service._repo.save_sheet_data = AsyncMock(return_value=char)

        await self.service.adjust_spell_slot(char, level=1, delta=1)
        new_data = self.service._repo.save_sheet_data.call_args[0][1]
        assert new_data["spell_slots"]["level_1"]["expended"] == 2

    @pytest.mark.asyncio
    async def test_recover_slot(self):
        char = _make_character()
        char.sheet_data["spell_slots"] = {"level_2": {"total": 3, "expended": 2}}
        self.service._repo.save_sheet_data = AsyncMock(return_value=char)

        await self.service.adjust_spell_slot(char, level=2, delta=-1)
        new_data = self.service._repo.save_sheet_data.call_args[0][1]
        assert new_data["spell_slots"]["level_2"]["expended"] == 1

    @pytest.mark.asyncio
    async def test_expended_cannot_exceed_total(self):
        char = _make_character()
        char.sheet_data["spell_slots"] = {"level_3": {"total": 2, "expended": 2}}
        self.service._repo.save_sheet_data = AsyncMock(return_value=char)

        await self.service.adjust_spell_slot(char, level=3, delta=5)
        new_data = self.service._repo.save_sheet_data.call_args[0][1]
        assert new_data["spell_slots"]["level_3"]["expended"] == 2

    @pytest.mark.asyncio
    async def test_expended_cannot_go_below_zero(self):
        char = _make_character()
        char.sheet_data["spell_slots"] = {"level_1": {"total": 4, "expended": 0}}
        self.service._repo.save_sheet_data = AsyncMock(return_value=char)

        await self.service.adjust_spell_slot(char, level=1, delta=-5)
        new_data = self.service._repo.save_sheet_data.call_args[0][1]
        assert new_data["spell_slots"]["level_1"]["expended"] == 0

    @pytest.mark.asyncio
    async def test_missing_spell_slots_dict_initialised(self):
        char = _make_character()
        char.sheet_data["spell_slots"] = "corrupted"
        self.service._repo.save_sheet_data = AsyncMock(return_value=char)

        await self.service.adjust_spell_slot(char, level=1, delta=1)
        new_data = self.service._repo.save_sheet_data.call_args[0][1]
        assert isinstance(new_data["spell_slots"], dict)


# ---------------------------------------------------------------------------
# _check_write_permission
# ---------------------------------------------------------------------------


class TestCheckWritePermission:
    def setup_method(self):
        self.service = _make_service()

    def test_owner_can_write(self):
        owner_id = uuid.uuid4()
        char = _make_character(owner_id=owner_id)
        # Should not raise
        self.service._check_write_permission(char, owner_id, is_dm=False)

    def test_dm_can_write_any_character(self):
        char = _make_character()
        other_id = uuid.uuid4()
        # DM should not raise even if IDs differ
        self.service._check_write_permission(char, other_id, is_dm=True)

    def test_non_owner_non_dm_raises(self):
        char = _make_character()
        other_id = uuid.uuid4()
        with pytest.raises(CharacterPermissionError):
            self.service._check_write_permission(char, other_id, is_dm=False)


# ---------------------------------------------------------------------------
# create_from_json_string
# ---------------------------------------------------------------------------


class TestCreateFromJsonString:
    def setup_method(self):
        self.service = _make_service()

    @pytest.mark.asyncio
    async def test_invalid_json_raises(self):
        with pytest.raises(CharacterValidationError) as exc_info:
            await self.service.create_from_json_string("not json", uuid.uuid4())
        assert "Invalid JSON" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_valid_json_creates_character(self):
        valid_sheet = {
            "character_identity": {
                "character_name": "Gandalf",
                "class": {"name": "Wizard"},
                "species": {"name": "Maiar"},
            },
            "character_level": {"level": 20},
            "vitality": {"hit_points": {"max": 100, "current": 100}},
        }
        import json
        owner_id = uuid.uuid4()
        char = _make_character()
        self.service._repo.create = AsyncMock(return_value=char)

        result = await self.service.create_from_json_string(json.dumps(valid_sheet), owner_id)
        assert result is char
        self.service._repo.create.assert_called_once()

    @pytest.mark.asyncio
    async def test_missing_required_fields_raises(self):
        import json
        with pytest.raises(CharacterValidationError):
            await self.service.create_from_json_string(json.dumps({}), uuid.uuid4())


# ---------------------------------------------------------------------------
# use_class_resource
# ---------------------------------------------------------------------------


class TestUseClassResource:
    def setup_method(self):
        self.service = _make_service()

    def _char_with_resources(self, resources):
        sheet = _base_sheet()
        sheet["class_resources"] = resources
        owner_id = uuid.uuid4()
        char = _make_character(sheet_data=sheet, owner_id=owner_id)
        self.owner_id = owner_id
        return char

    @pytest.mark.asyncio
    async def test_use_decrements_uses_current(self):
        char = self._char_with_resources([
            {"name": "Rage", "action_type": "bonus_action", "uses_max": 3, "uses_current": 3, "recharge": "long_rest", "description": ""},
        ])
        self.service._repo.get_by_id = AsyncMock(return_value=char)
        saved = MagicMock()
        self.service._repo.save_sheet_data = AsyncMock(return_value=saved)

        result = await self.service.use_class_resource(char.id, self.owner_id, False, 0, -1)

        saved_data = self.service._repo.save_sheet_data.call_args[0][1]
        assert saved_data["class_resources"][0]["uses_current"] == 2

    @pytest.mark.asyncio
    async def test_restore_increments_uses_current(self):
        char = self._char_with_resources([
            {"name": "Rage", "action_type": "bonus_action", "uses_max": 3, "uses_current": 1, "recharge": "long_rest", "description": ""},
        ])
        self.service._repo.get_by_id = AsyncMock(return_value=char)
        self.service._repo.save_sheet_data = AsyncMock(return_value=MagicMock())

        await self.service.use_class_resource(char.id, self.owner_id, False, 0, 1)

        saved_data = self.service._repo.save_sheet_data.call_args[0][1]
        assert saved_data["class_resources"][0]["uses_current"] == 2

    @pytest.mark.asyncio
    async def test_uses_current_clamped_to_max(self):
        char = self._char_with_resources([
            {"name": "Rage", "action_type": "bonus_action", "uses_max": 3, "uses_current": 3, "recharge": "long_rest", "description": ""},
        ])
        self.service._repo.get_by_id = AsyncMock(return_value=char)
        self.service._repo.save_sheet_data = AsyncMock(return_value=MagicMock())

        await self.service.use_class_resource(char.id, self.owner_id, False, 0, 5)

        saved_data = self.service._repo.save_sheet_data.call_args[0][1]
        assert saved_data["class_resources"][0]["uses_current"] == 3

    @pytest.mark.asyncio
    async def test_uses_current_clamped_to_zero(self):
        char = self._char_with_resources([
            {"name": "Rage", "action_type": "bonus_action", "uses_max": 3, "uses_current": 0, "recharge": "long_rest", "description": ""},
        ])
        self.service._repo.get_by_id = AsyncMock(return_value=char)
        self.service._repo.save_sheet_data = AsyncMock(return_value=MagicMock())

        await self.service.use_class_resource(char.id, self.owner_id, False, 0, -10)

        saved_data = self.service._repo.save_sheet_data.call_args[0][1]
        assert saved_data["class_resources"][0]["uses_current"] == 0

    @pytest.mark.asyncio
    async def test_out_of_range_index_is_ignored(self):
        char = self._char_with_resources([
            {"name": "Rage", "action_type": "bonus_action", "uses_max": 3, "uses_current": 3, "recharge": "long_rest", "description": ""},
        ])
        self.service._repo.get_by_id = AsyncMock(return_value=char)
        self.service._repo.save_sheet_data = AsyncMock(return_value=MagicMock())

        await self.service.use_class_resource(char.id, self.owner_id, False, 99, -1)

        saved_data = self.service._repo.save_sheet_data.call_args[0][1]
        # unchanged
        assert saved_data["class_resources"][0]["uses_current"] == 3

    @pytest.mark.asyncio
    async def test_non_owner_raises(self):
        char = self._char_with_resources([])
        self.service._repo.get_by_id = AsyncMock(return_value=char)

        with pytest.raises(CharacterPermissionError):
            await self.service.use_class_resource(char.id, uuid.uuid4(), False, 0, -1)


# ---------------------------------------------------------------------------
# _apply_short_rest (static method — pure logic)
# ---------------------------------------------------------------------------


class TestApplyShortRest:
    def test_restores_short_rest_resources(self):
        data = {
            "class_resources": [
                {"name": "Second Wind", "uses_max": 1, "uses_current": 0, "recharge": "short_rest"},
            ]
        }
        CharacterService._apply_short_rest(data)
        assert data["class_resources"][0]["uses_current"] == 1

    def test_does_not_restore_long_rest_resources(self):
        data = {
            "class_resources": [
                {"name": "Rage", "uses_max": 3, "uses_current": 1, "recharge": "long_rest"},
            ]
        }
        CharacterService._apply_short_rest(data)
        assert data["class_resources"][0]["uses_current"] == 1

    def test_does_not_restore_dawn_resources(self):
        data = {
            "class_resources": [
                {"name": "Channel Divinity", "uses_max": 2, "uses_current": 0, "recharge": "dawn"},
            ]
        }
        CharacterService._apply_short_rest(data)
        assert data["class_resources"][0]["uses_current"] == 0

    def test_mixed_resources_only_short_rest_restored(self):
        data = {
            "class_resources": [
                {"name": "Second Wind", "uses_max": 1, "uses_current": 0, "recharge": "short_rest"},
                {"name": "Rage", "uses_max": 3, "uses_current": 1, "recharge": "long_rest"},
                {"name": "Bardic Inspiration", "uses_max": 4, "uses_current": 2, "recharge": "short_rest"},
            ]
        }
        CharacterService._apply_short_rest(data)
        assert data["class_resources"][0]["uses_current"] == 1
        assert data["class_resources"][1]["uses_current"] == 1  # unchanged
        assert data["class_resources"][2]["uses_current"] == 4

    def test_empty_class_resources_is_noop(self):
        data = {"class_resources": []}
        CharacterService._apply_short_rest(data)
        assert data["class_resources"] == []

    def test_missing_class_resources_is_noop(self):
        data = {}
        CharacterService._apply_short_rest(data)
        assert data == {}


# ---------------------------------------------------------------------------
# _apply_long_rest (static method — pure logic)
# ---------------------------------------------------------------------------


class TestApplyLongRest:
    def _make_data(self, **overrides) -> dict:
        base = {
            "vitality": {
                "hit_points": {"current": 20, "max": 40, "temp": 5},
                "death_saves": {"successes": 2, "failures": 1},
                "hit_dice": {"total": "4d8", "spent": "3"},
            },
            "spell_slots": {
                "level_1": {"total": 4, "expended": 3},
                "level_2": {"total": 3, "expended": 2},
            },
            "class_resources": [
                {"name": "Rage", "uses_max": 3, "uses_current": 1, "recharge": "long_rest"},
                {"name": "Second Wind", "uses_max": 1, "uses_current": 0, "recharge": "short_rest"},
                {"name": "Channel Divinity", "uses_max": 2, "uses_current": 0, "recharge": "dawn"},
            ],
        }
        base.update(overrides)
        return base

    def test_hp_restored_to_max(self):
        data = self._make_data()
        CharacterService._apply_long_rest(data)
        assert data["vitality"]["hit_points"]["current"] == 40

    def test_temp_hp_cleared(self):
        data = self._make_data()
        CharacterService._apply_long_rest(data)
        assert data["vitality"]["hit_points"]["temp"] == 0

    def test_death_saves_reset(self):
        data = self._make_data()
        CharacterService._apply_long_rest(data)
        assert data["vitality"]["death_saves"]["successes"] == 0
        assert data["vitality"]["death_saves"]["failures"] == 0

    def test_spell_slots_fully_restored(self):
        data = self._make_data()
        CharacterService._apply_long_rest(data)
        assert data["spell_slots"]["level_1"]["expended"] == 0
        assert data["spell_slots"]["level_2"]["expended"] == 0

    def test_long_rest_resources_restored(self):
        data = self._make_data()
        CharacterService._apply_long_rest(data)
        assert data["class_resources"][0]["uses_current"] == 3  # Rage

    def test_short_rest_resources_also_restored(self):
        data = self._make_data()
        CharacterService._apply_long_rest(data)
        assert data["class_resources"][1]["uses_current"] == 1  # Second Wind

    def test_dawn_resources_restored(self):
        data = self._make_data()
        CharacterService._apply_long_rest(data)
        assert data["class_resources"][2]["uses_current"] == 2  # Channel Divinity

    def test_hit_dice_recovery_4d8_recovers_2(self):
        data = self._make_data()
        CharacterService._apply_long_rest(data)
        # spent was 3, recover 2, result = 1
        assert data["vitality"]["hit_dice"]["spent"] == 1

    def test_hit_dice_recovery_1d8_recovers_1(self):
        data = self._make_data()
        data["vitality"]["hit_dice"]["total"] = "1d8"
        data["vitality"]["hit_dice"]["spent"] = "1"
        CharacterService._apply_long_rest(data)
        # spent was 1, recover max(1, 1//2) = max(1, 0) = 1, result = 0
        assert data["vitality"]["hit_dice"]["spent"] == 0

    def test_hit_dice_spent_never_goes_below_zero(self):
        data = self._make_data()
        data["vitality"]["hit_dice"]["spent"] = "0"
        CharacterService._apply_long_rest(data)
        assert data["vitality"]["hit_dice"]["spent"] == 0

    def test_hit_dice_recovery_odd_count_floors(self):
        data = self._make_data()
        data["vitality"]["hit_dice"]["total"] = "3d10"
        data["vitality"]["hit_dice"]["spent"] = "3"
        CharacterService._apply_long_rest(data)
        # recover max(1, 3//2) = max(1,1) = 1; 3-1=2
        assert data["vitality"]["hit_dice"]["spent"] == 2

    def test_empty_spell_slots_is_noop(self):
        data = self._make_data()
        data["spell_slots"] = {}
        CharacterService._apply_long_rest(data)
        assert data["spell_slots"] == {}

    def test_no_class_resources_is_noop(self):
        data = self._make_data()
        data["class_resources"] = []
        CharacterService._apply_long_rest(data)
        assert data["class_resources"] == []


# ---------------------------------------------------------------------------
# perform_short_rest / perform_long_rest (async, uses mock repo)
# ---------------------------------------------------------------------------


class TestPerformShortRest:
    def setup_method(self):
        self.service = _make_service()

    @pytest.mark.asyncio
    async def test_calls_save_with_updated_data(self):
        owner_id = uuid.uuid4()
        sheet = _base_sheet()
        sheet["class_resources"] = [
            {"name": "Second Wind", "uses_max": 1, "uses_current": 0, "recharge": "short_rest"},
        ]
        char = _make_character(sheet_data=sheet, owner_id=owner_id)
        self.service._repo.get_by_id = AsyncMock(return_value=char)
        saved = MagicMock()
        self.service._repo.save_sheet_data = AsyncMock(return_value=saved)

        result = await self.service.perform_short_rest(char.id, owner_id, False)

        assert result is saved
        saved_data = self.service._repo.save_sheet_data.call_args[0][1]
        assert saved_data["class_resources"][0]["uses_current"] == 1

    @pytest.mark.asyncio
    async def test_non_owner_raises(self):
        owner_id = uuid.uuid4()
        char = _make_character(owner_id=owner_id)
        self.service._repo.get_by_id = AsyncMock(return_value=char)

        with pytest.raises(CharacterPermissionError):
            await self.service.perform_short_rest(char.id, uuid.uuid4(), False)


class TestPerformLongRest:
    def setup_method(self):
        self.service = _make_service()

    @pytest.mark.asyncio
    async def test_restores_hp_and_spell_slots(self):
        owner_id = uuid.uuid4()
        sheet = _base_sheet()
        sheet["vitality"]["hit_points"] = {"current": 10, "max": 40, "temp": 5}
        sheet["spell_slots"] = {"level_1": {"total": 4, "expended": 3}}
        sheet["class_resources"] = []
        char = _make_character(sheet_data=sheet, owner_id=owner_id)
        self.service._repo.get_by_id = AsyncMock(return_value=char)
        saved = MagicMock()
        self.service._repo.save_sheet_data = AsyncMock(return_value=saved)

        result = await self.service.perform_long_rest(char.id, owner_id, False)

        assert result is saved
        saved_data = self.service._repo.save_sheet_data.call_args[0][1]
        assert saved_data["vitality"]["hit_points"]["current"] == 40
        assert saved_data["vitality"]["hit_points"]["temp"] == 0
        assert saved_data["spell_slots"]["level_1"]["expended"] == 0

    @pytest.mark.asyncio
    async def test_non_owner_raises(self):
        owner_id = uuid.uuid4()
        char = _make_character(owner_id=owner_id)
        self.service._repo.get_by_id = AsyncMock(return_value=char)

        with pytest.raises(CharacterPermissionError):
            await self.service.perform_long_rest(char.id, uuid.uuid4(), False)

