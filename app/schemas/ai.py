import uuid
from pydantic import BaseModel, Field


class CategorizeRequest(BaseModel):
    description: str = Field(..., min_length=1, max_length=5000, description="Text to categorize")


class CategorizeResponse(BaseModel):
    category: str = Field(..., description="Top predicted category label")
    scores: dict[str, float] = Field(default_factory=dict, description="Label-to-score mapping")


class SimilarRequest(BaseModel):
    description: str = Field(..., min_length=1, max_length=5000, description="Description to find similar ideas for")
    title: str = Field(default="", max_length=200, description="Optional title to improve matching accuracy")
    exclude_id: uuid.UUID | None = Field(None, description="Idea ID to exclude from results")


class SimilarIdeaItem(BaseModel):
    idea_id: uuid.UUID
    title: str
    category: str
    similarity_score: float


class SimilarResponse(BaseModel):
    similar_ideas: list[SimilarIdeaItem] = Field(default_factory=list)
