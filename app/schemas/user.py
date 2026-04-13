import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.models.user import UserRole


class UserCreate(BaseModel):
    """Payload for creating a new user account."""

    name: str = Field(..., min_length=2, max_length=255, description="Full name of the user")
    email: EmailStr = Field(..., description="Unique email address")
    password: str = Field(..., min_length=8, description="Password (min 8 characters)")
    role: UserRole = Field(default=UserRole.USER, description="User role: user, developer, or admin")


class UserLogin(BaseModel):
    """Credentials for user login."""

    email: EmailStr = Field(..., description="Registered email address")
    password: str = Field(..., description="Account password")


class UserResponse(BaseModel):
    """User data returned from the API (no sensitive fields)."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    email: str
    avatar_url: str | None
    role: str
    created_at: datetime
    updated_at: datetime


class UserUpdate(BaseModel):
    """Fields that a user can update on their own profile."""

    name: str | None = Field(None, min_length=2, max_length=255)
    avatar_url: str | None = Field(None, max_length=500)


class RoleUpdate(BaseModel):
    """Payload for an admin to change another user's role."""

    role: UserRole = Field(..., description="New role to assign")


class TokenResponse(BaseModel):
    """Authentication token response."""

    access_token: str = Field(..., description="JWT bearer token")
    token_type: str = Field(default="bearer", description="Token type")
    user: UserResponse = Field(..., description="Authenticated user data")
