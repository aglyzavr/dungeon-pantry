from pydantic import BaseModel, field_validator


class LoginRequest(BaseModel):
    username: str
    password: str

    @field_validator("username", "password")
    @classmethod
    def must_not_be_blank(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("This field cannot be blank")
        return v.strip()


class UserSession(BaseModel):
    """What we store in the signed session cookie — minimal, no sensitive data."""
    user_id: str
    username: str
    # we persist a simple boolean rather than the full ``role`` string,
    # keeping the session payload compact and avoiding any need to fetch the
    # user model later. The previous property accessor was a leftover from an
    # earlier design and referenced a non‑existent ``role`` field; it has been
    # removed.
    is_dm: bool = False
