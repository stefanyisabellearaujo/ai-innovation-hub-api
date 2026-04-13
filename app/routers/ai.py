from typing import Annotated
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.middleware.auth import get_current_user
from app.models.user import User
from app.schemas.ai import (
    CategorizeRequest,
    CategorizeResponse,
    SimilarIdeaItem,
    SimilarRequest,
    SimilarResponse,
)
from app.services import ai_service

router = APIRouter(prefix="/api/ai", tags=["AI"])


@router.post(
    "/categorize",
    response_model=CategorizeResponse,
    summary="Categorize text using AI",
)
async def categorize(
    body: CategorizeRequest,
    current_user: Annotated[User, Depends(get_current_user)],
) -> CategorizeResponse:
    """Classify text using HuggingFace zero-shot classification. Falls back to 'Other' on failure."""
    result = await ai_service.categorize_idea(body.description)
    return CategorizeResponse(category=result["category"], scores=result["scores"])


@router.post(
    "/similar",
    response_model=SimilarResponse,
    summary="Find similar ideas",
)
async def find_similar(
    body: SimilarRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> SimilarResponse:
    """Find ideas similar to the given description using category filter and keyword similarity."""
    similar = await ai_service.find_similar_ideas(
        description=body.description,
        title=body.title,
        db=db,
        exclude_id=body.exclude_id,
    )
    return SimilarResponse(
        similar_ideas=[SimilarIdeaItem(**item) for item in similar]
    )
