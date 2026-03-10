from uuid import UUID

from pydantic import BaseModel, field_validator

from app.schemas import validate_non_empty


class LoginRequest(BaseModel):
    username: str
    password: str

    @field_validator("username", "password")
    @classmethod
    def must_not_be_blank(cls, v: str) -> str:
        return validate_non_empty(v)


class UserSession(BaseModel):
    """What we store in the signed session cookie — minimal, no sensitive data."""
    user_id: UUID
    username: str
    # we persist a simple boolean rather than the full ``role`` string,
    # keeping the session payload compact and avoiding any need to fetch the
    # user model later. The previous property accessor was a leftover from an
    # earlier design and referenced a non‑existent ``role`` field; it has been
    # removed.
    is_dm: bool = False
    language: str = "en"
    theme: str = "light"
