from pydantic import BaseModel, field_validator


def get_skill_bonus(skill_data) -> int:
    """Handles both old flat format (int) and new object format (dict)."""
    if isinstance(skill_data, dict):
        return int(skill_data.get("bonus", 0))
    return int(skill_data or 0)


def is_proficient(skill_data) -> bool:
    if isinstance(skill_data, dict):
        return bool(skill_data.get("proficient", False))
    return False


def get_skill_advantage(skill_data) -> str:
    """Return 'advantage', 'disadvantage', or 'none' for a skill."""
    if isinstance(skill_data, dict):
        return skill_data.get("advantage", "none")
    return "none"




def validate_mandatory_fields(data: dict) -> list[str]:
    errors = []
    identity = data.get("character_identity", {})
    if not isinstance(identity, dict):
        return ["character_identity must be an object"]
    if not str(identity.get("character_name", "")).strip():
        errors.append("character_identity.character_name is required")
    char_class = identity.get("class", {})
    if not isinstance(char_class, dict) or not str(char_class.get("name", "")).strip():
        errors.append("character_identity.class.name is required")
    species = identity.get("species", {})
    if not isinstance(species, dict) or not str(species.get("name", "")).strip():
        errors.append("character_identity.species.name is required")
    vitality = data.get("vitality", {})
    hp = vitality.get("hit_points", {}) if isinstance(vitality, dict) else {}
    try:
        if int(hp.get("max", 0)) <= 0:
            errors.append("vitality.hit_points.max must be greater than 0")
    except (TypeError, ValueError):
        errors.append("vitality.hit_points.max must be a number")
    try:
        if int(hp.get("current", -1)) < 0:
            errors.append("vitality.hit_points.current must be 0 or greater")
    except (TypeError, ValueError):
        errors.append("vitality.hit_points.current must be a number")
    char_level = data.get("character_level", {})
    try:
        level = int(char_level.get("level", 0) if isinstance(char_level, dict) else 0)
        if not (1 <= level <= 20):
            errors.append("character_level.level must be between 1 and 20")
    except (TypeError, ValueError):
        errors.append("character_level.level must be a number")
    return errors


class HPUpdate(BaseModel):
    delta: int | None = None
    value: int | None = None

    @field_validator("delta", "value", mode="before")
    @classmethod
    def coerce_none_string(cls, v):
        if v == "" or v is None:
            return None
        return v


class DeathSaveUpdate(BaseModel):
    save_type: str
    action: str


class SpellSlotUpdate(BaseModel):
    level: int
    delta: int

    @field_validator("level")
    @classmethod
    def valid_level(cls, v: int) -> int:
        if not (1 <= v <= 9):
            raise ValueError("Spell slot level must be 1-9")
        return v
