from uuid import UUID

from pydantic import BaseModel, field_validator

from app.schemas import validate_non_empty


class PlayerCreate(BaseModel):
    username: str
    password: str

    @field_validator("username")
    @classmethod
    def username_valid(cls, v: str) -> str:
        v = validate_non_empty(v, "Username")
        if len(v) < 3:
            raise ValueError("Username must be at least 3 characters")
        if len(v) > 64:
            raise ValueError("Username must be at most 64 characters")
        if not v.replace("_", "").replace("-", "").isalnum():
            raise ValueError("Username may only contain letters, numbers, - and _")
        return v

    @field_validator("password")
    @classmethod
    def password_valid(cls, v: str) -> str:
        v = validate_non_empty(v, "Password")
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters")
        if len(v) > 128:
            raise ValueError("Password must be at most 128 characters")
        return v


class PlayerAssignCharacter(BaseModel):
    character_id: UUID
