import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

VALID_STATUSES = {"idea", "evaluation", "development", "completed", "archived"}


class IdeaCreate(BaseModel):
    """Payload for creating a new idea."""

    title: str = Field(..., min_length=1, max_length=200, description="Idea title")
    description: str = Field(
        ..., min_length=1, max_length=5000, description="Detailed description"
    )


class IdeaUpdate(BaseModel):
    """Payload for partially updating an idea."""

    title: str | None = Field(None, min_length=1, max_length=200, description="Idea title")
    description: str | None = Field(
        None, min_length=1, max_length=5000, description="Detailed description"
    )
    status: str | None = Field(
        None,
        description="Status: idea, evaluation, development, completed, archived",
    )

    @field_validator("status")
    @classmethod
    def validate_status(cls, v: str | None) -> str | None:
        if v is not None and v not in VALID_STATUSES:
            raise ValueError(
                f"status must be one of: {', '.join(sorted(VALID_STATUSES))}"
            )
        return v


class AuthorResponse(BaseModel):
    """Minimal author info embedded in idea responses."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    role: str


class CollaboratorInfo(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID
    role: str
    user_name: str | None = None

    @model_validator(mode="before")
    @classmethod
    def extract_user_name(cls, data: Any) -> Any:
        # When built from an ORM Collaborator object, pull user.name
        if hasattr(data, "user") and data.user is not None:
            data.__dict__["user_name"] = data.user.name
        return data


class IdeaResponse(BaseModel):
    """Full idea data returned from the API."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    description: str
    category: str | None
    status: str
    author_id: uuid.UUID
    author: AuthorResponse | None
    votes_count: int
    collaborators: list[CollaboratorInfo] = []
    created_at: datetime
    updated_at: datetime


class IdeaListResponse(BaseModel):
    """Paginated list of ideas."""

    items: list[IdeaResponse]
    total: int
    page: int
    per_page: int
    pages: int
