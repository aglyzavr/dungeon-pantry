"""Tests for schema validation helpers and Pydantic models."""
import pytest
from pydantic import ValidationError

from app.schemas import validate_non_empty
from app.schemas.character import (
    DeathSaveUpdate,
    HPUpdate,
    MaxHPUpdate,
    SpellSlotUpdate,
    SpellSlotTotalUpdate,
    TempHPUpdate,
    ThrowableCaseQtyUpdate,
    get_skill_advantage,
    get_skill_bonus,
    is_proficient,
    validate_mandatory_fields,
)


# ---------------------------------------------------------------------------
# validate_non_empty
# ---------------------------------------------------------------------------


class TestValidateNonEmpty:
    def test_valid_string(self):
        assert validate_non_empty("hello") == "hello"

    def test_strips_whitespace(self):
        assert validate_non_empty("  hi  ") == "hi"

    def test_empty_string_raises(self):
        with pytest.raises(ValueError):
            validate_non_empty("")

    def test_whitespace_only_raises(self):
        with pytest.raises(ValueError):
            validate_non_empty("   ")


# ---------------------------------------------------------------------------
# validate_mandatory_fields
# ---------------------------------------------------------------------------


def _valid_data() -> dict:
    return {
        "character_identity": {
            "character_name": "Aragorn",
            "class": {"name": "Ranger"},
            "species": {"name": "Human"},
        },
        "character_level": {"level": 5},
        "vitality": {
            "hit_points": {"max": 45, "current": 30},
        },
    }


class TestValidateMandatoryFields:
    def test_valid_returns_no_errors(self):
        assert validate_mandatory_fields(_valid_data()) == []

    def test_missing_character_name(self):
        data = _valid_data()
        data["character_identity"]["character_name"] = "  "
        errors = validate_mandatory_fields(data)
        assert any("character_name" in e for e in errors)

    def test_missing_class_name(self):
        data = _valid_data()
        data["character_identity"]["class"] = {}
        errors = validate_mandatory_fields(data)
        assert any("class" in e for e in errors)

    def test_class_not_a_dict(self):
        data = _valid_data()
        data["character_identity"]["class"] = "Rogue"
        errors = validate_mandatory_fields(data)
        assert any("class" in e for e in errors)

    def test_missing_species_name(self):
        data = _valid_data()
        data["character_identity"]["species"] = {}
        errors = validate_mandatory_fields(data)
        assert any("species" in e for e in errors)

    def test_hp_max_zero(self):
        data = _valid_data()
        data["vitality"]["hit_points"]["max"] = 0
        errors = validate_mandatory_fields(data)
        assert any("hit_points.max" in e for e in errors)

    def test_hp_max_negative(self):
        data = _valid_data()
        data["vitality"]["hit_points"]["max"] = -5
        errors = validate_mandatory_fields(data)
        assert any("hit_points.max" in e for e in errors)

    def test_hp_current_negative(self):
        data = _valid_data()
        data["vitality"]["hit_points"]["current"] = -1
        errors = validate_mandatory_fields(data)
        assert any("hit_points.current" in e for e in errors)

    def test_hp_current_zero_is_valid(self):
        data = _valid_data()
        data["vitality"]["hit_points"]["current"] = 0
        assert validate_mandatory_fields(data) == []

    def test_level_out_of_range_low(self):
        data = _valid_data()
        data["character_level"]["level"] = 0
        errors = validate_mandatory_fields(data)
        assert any("level" in e for e in errors)

    def test_level_out_of_range_high(self):
        data = _valid_data()
        data["character_level"]["level"] = 21
        errors = validate_mandatory_fields(data)
        assert any("level" in e for e in errors)

    def test_level_20_is_valid(self):
        data = _valid_data()
        data["character_level"]["level"] = 20
        assert validate_mandatory_fields(data) == []

    def test_level_1_is_valid(self):
        data = _valid_data()
        data["character_level"]["level"] = 1
        assert validate_mandatory_fields(data) == []

    def test_character_identity_not_a_dict(self):
        data = _valid_data()
        data["character_identity"] = "not a dict"
        errors = validate_mandatory_fields(data)
        assert errors == ["character_identity must be an object"]

    def test_multiple_errors_returned(self):
        data = _valid_data()
        data["character_identity"]["character_name"] = ""
        data["character_level"]["level"] = 0
        errors = validate_mandatory_fields(data)
        assert len(errors) >= 2


# ---------------------------------------------------------------------------
# Skill helper functions
# ---------------------------------------------------------------------------


class TestGetSkillBonus:
    def test_dict_format(self):
        assert get_skill_bonus({"bonus": 3}) == 3

    def test_flat_int_format(self):
        assert get_skill_bonus(5) == 5

    def test_none_returns_zero(self):
        assert get_skill_bonus(None) == 0

    def test_dict_missing_bonus_key(self):
        assert get_skill_bonus({}) == 0

    def test_negative_bonus(self):
        assert get_skill_bonus({"bonus": -2}) == -2


class TestIsProficient:
    def test_proficient_true(self):
        assert is_proficient({"proficient": True}) is True

    def test_proficient_false(self):
        assert is_proficient({"proficient": False}) is False

    def test_flat_int_returns_false(self):
        assert is_proficient(3) is False

    def test_missing_key_returns_false(self):
        assert is_proficient({}) is False


class TestGetSkillAdvantage:
    def test_advantage(self):
        assert get_skill_advantage({"advantage": "advantage"}) == "advantage"

    def test_disadvantage(self):
        assert get_skill_advantage({"advantage": "disadvantage"}) == "disadvantage"

    def test_none_advantage(self):
        assert get_skill_advantage({"advantage": "none"}) == "none"

    def test_missing_key_defaults_to_none(self):
        assert get_skill_advantage({}) == "none"

    def test_flat_format_returns_none(self):
        assert get_skill_advantage(5) == "none"


# ---------------------------------------------------------------------------
# Pydantic schema models
# ---------------------------------------------------------------------------


class TestHPUpdate:
    def test_both_none(self):
        m = HPUpdate()
        assert m.delta is None
        assert m.value is None

    def test_delta_set(self):
        assert HPUpdate(delta=5).delta == 5

    def test_value_set(self):
        assert HPUpdate(value=10).value == 10

    def test_empty_string_coerced_to_none(self):
        m = HPUpdate(delta="", value="")
        assert m.delta is None
        assert m.value is None


class TestSpellSlotUpdate:
    def test_valid(self):
        m = SpellSlotUpdate(level=3, delta=-1)
        assert m.level == 3
        assert m.delta == -1

    def test_level_zero_invalid(self):
        with pytest.raises(ValidationError):
            SpellSlotUpdate(level=0, delta=1)

    def test_level_ten_invalid(self):
        with pytest.raises(ValidationError):
            SpellSlotUpdate(level=10, delta=1)

    def test_level_1_valid(self):
        assert SpellSlotUpdate(level=1, delta=1).level == 1

    def test_level_9_valid(self):
        assert SpellSlotUpdate(level=9, delta=1).level == 9


class TestSpellSlotTotalUpdate:
    def test_valid(self):
        m = SpellSlotTotalUpdate(level=3, total=4)
        assert m.level == 3
        assert m.total == 4

    def test_level_zero_invalid(self):
        with pytest.raises(ValidationError):
            SpellSlotTotalUpdate(level=0, total=1)

    def test_level_ten_invalid(self):
        with pytest.raises(ValidationError):
            SpellSlotTotalUpdate(level=10, total=1)

    def test_total_negative_invalid(self):
        with pytest.raises(ValidationError):
            SpellSlotTotalUpdate(level=1, total=-1)

    def test_total_100_invalid(self):
        with pytest.raises(ValidationError):
            SpellSlotTotalUpdate(level=1, total=100)

    def test_total_zero_valid(self):
        assert SpellSlotTotalUpdate(level=1, total=0).total == 0

    def test_total_99_valid(self):
        assert SpellSlotTotalUpdate(level=9, total=99).total == 99

    def test_level_1_valid(self):
        assert SpellSlotTotalUpdate(level=1, total=4).level == 1

    def test_level_9_valid(self):
        assert SpellSlotTotalUpdate(level=9, total=4).level == 9


class TestDeathSaveUpdate:
    def test_valid(self):
        m = DeathSaveUpdate(save_type="successes", action="add")
        assert m.save_type == "successes"
        assert m.action == "add"


class TestTempHPUpdate:
    def test_empty_string_to_none(self):
        m = TempHPUpdate(delta="", value="")
        assert m.delta is None
        assert m.value is None

    def test_values_set(self):
        m = TempHPUpdate(delta=3, value=None)
        assert m.delta == 3


class TestMaxHPUpdate:
    def test_default_value(self):
        assert MaxHPUpdate().value == 1

    def test_empty_string_defaults_to_one(self):
        assert MaxHPUpdate(value="").value == 1

    def test_none_defaults_to_one(self):
        assert MaxHPUpdate(value=None).value == 1

    def test_custom_value(self):
        assert MaxHPUpdate(value=50).value == 50


class TestThrowableCaseQtyUpdate:
    def test_defaults(self):
        m = ThrowableCaseQtyUpdate()
        assert m.case_index == 0
        assert m.item_index == 0
        assert m.delta == 0

    def test_empty_string_to_zero(self):
        m = ThrowableCaseQtyUpdate(case_index="", item_index="", delta="")
        assert m.case_index == 0
        assert m.item_index == 0
        assert m.delta == 0

    def test_values(self):
        m = ThrowableCaseQtyUpdate(case_index=1, item_index=2, delta=-1)
        assert m.case_index == 1
        assert m.item_index == 2
        assert m.delta == -1
