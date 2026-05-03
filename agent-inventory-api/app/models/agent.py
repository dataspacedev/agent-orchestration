from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class DeploymentState(str, Enum):
    running = "running"
    stopped = "stopped"
    deleted = "deleted"


class OutboxEventType(str, Enum):
    created = "CREATED"
    updated = "UPDATED"
    deleted = "DELETED"
    stopped = "STOPPED"


class OutboxStatus(str, Enum):
    pending = "pending"
    processing = "processing"
    completed = "completed"
    failed = "failed"


class ResourceRequirements(BaseModel):
    requests: dict[str, str] | None = None
    limits: dict[str, str] | None = None


class ScalingConfig(BaseModel):
    min_replicas: int | None = Field(default=None, ge=1)
    max_replicas: int | None = Field(default=None, ge=1)
    target_cpu_utilization_percentage: int | None = Field(default=None, ge=1, le=100)


class AgentSpec(BaseModel):
    image: str
    port: int | None = Field(default=None, ge=1, le=65535)
    secret_name: str | None = None
    config: dict[str, str] | None = None
    resources: ResourceRequirements | None = None
    scaling: ScalingConfig | None = None


class AgentBase(BaseModel):
    name: str
    version: str
    description: str | None = None
    status: str = "active"
    deployment_state: DeploymentState = DeploymentState.running


class AgentCreate(AgentBase):
    spec: AgentSpec


class AgentUpdate(BaseModel):
    name: str | None = None
    version: str | None = None
    description: str | None = None
    status: str | None = None
    deployment_state: DeploymentState | None = None
    spec: AgentSpec | None = None


class AgentResponse(AgentBase):
    id: str
    spec: AgentSpec | None = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
