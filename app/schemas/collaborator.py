import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class CollaboratorResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID
    idea_id: uuid.UUID
    role: str
    joined_at: datetime
    user_name: str | None = None
