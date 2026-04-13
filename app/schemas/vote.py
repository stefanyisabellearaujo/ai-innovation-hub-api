from pydantic import BaseModel, ConfigDict


class VoteResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    voted: bool
    votes_count: int
