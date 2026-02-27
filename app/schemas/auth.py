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
    is_dm: bool = False

    @property
    def is_dm(self) -> bool:
        return self.role == "dm"
