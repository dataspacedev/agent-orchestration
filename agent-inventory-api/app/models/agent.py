from datetime import datetime

from pydantic import BaseModel, ConfigDict


class AgentBase(BaseModel):
    name: str
    description: str | None = None
    status: str = "active"


class AgentCreate(AgentBase):
    pass


class AgentResponse(AgentBase):
    id: str
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
