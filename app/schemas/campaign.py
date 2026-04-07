from uuid import UUID
from datetime import datetime

from pydantic import BaseModel, field_validator

from app.schemas import validate_non_empty


class CampaignCreate(BaseModel):
    name: str
    description: str | None = None

    @field_validator("name")
    @classmethod
    def name_must_not_be_blank(cls, v: str) -> str:
        v = validate_non_empty(v, "Campaign name")
        if len(v) > 100:
            raise ValueError("Campaign name must be at most 100 characters")
        return v

    @field_validator("description", mode="before")
    @classmethod
    def description_max_length(cls, v: str | None) -> str | None:
        if v and len(v) > 1000:
            raise ValueError("Description must be at most 1000 characters")
        return v


class CampaignUpdate(BaseModel):
    name: str
    description: str | None = None

    @field_validator("name")
    @classmethod
    def name_must_not_be_blank(cls, v: str) -> str:
        v = validate_non_empty(v, "Campaign name")
        if len(v) > 100:
            raise ValueError("Campaign name must be at most 100 characters")
        return v

    @field_validator("description", mode="before")
    @classmethod
    def description_max_length(cls, v: str | None) -> str | None:
        if v and len(v) > 1000:
            raise ValueError("Description must be at most 1000 characters")
        return v


class CampaignResponse(BaseModel):
    id: UUID
    name: str
    description: str | None
    created_at: datetime

    model_config = {"from_attributes": True}
