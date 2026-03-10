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
        return validate_non_empty(v, "Campaign name")


class CampaignUpdate(BaseModel):
    name: str
    description: str | None = None

    @field_validator("name")
    @classmethod
    def name_must_not_be_blank(cls, v: str) -> str:
        return validate_non_empty(v, "Campaign name")


class CampaignResponse(BaseModel):
    id: UUID
    name: str
    description: str | None
    created_at: datetime

    model_config = {"from_attributes": True}
