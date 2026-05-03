import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.agent import Agent
from app.db.session import get_db
from app.models.agent import AgentCreate, AgentResponse, AgentUpdate, DeploymentState, OutboxEventType
from app.outbox.events import make_outbox_event

router = APIRouter()


def _raise_not_found() -> None:
    raise HTTPException(status_code=404, detail="Agent not found")


def _raise_conflict() -> None:
    raise HTTPException(
        status_code=409,
        detail="An agent with this name and version already exists",
    )


@router.post("/agents", response_model=AgentResponse, status_code=201, tags=["agents"])
async def create_agent(payload: AgentCreate, db: AsyncSession = Depends(get_db)) -> Agent:
    agent = Agent(id=str(uuid.uuid4()), **payload.model_dump())
    db.add(agent)
    db.add(make_outbox_event(agent, OutboxEventType.created))
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        _raise_conflict()
    await db.refresh(agent)
    return agent


@router.get("/agents", response_model=list[AgentResponse], tags=["agents"])
async def list_agents(db: AsyncSession = Depends(get_db)) -> list[Agent]:
    result = await db.execute(select(Agent))
    return list(result.scalars().all())


@router.get("/agents/{agent_id}", response_model=AgentResponse, tags=["agents"])
async def get_agent(agent_id: str, db: AsyncSession = Depends(get_db)) -> Agent:
    result = await db.execute(select(Agent).where(Agent.id == agent_id))
    agent = result.scalar_one_or_none()
    if agent is None:
        _raise_not_found()
    return agent  # type: ignore[return-value]


@router.patch("/agents/{agent_id}", response_model=AgentResponse, tags=["agents"])
async def patch_agent(
    agent_id: str, payload: AgentUpdate, db: AsyncSession = Depends(get_db)
) -> Agent:
    result = await db.execute(select(Agent).where(Agent.id == agent_id))
    agent = result.scalar_one_or_none()
    if agent is None:
        _raise_not_found()

    updates = payload.model_dump(exclude_unset=True)
    for field, value in updates.items():
        setattr(agent, field, value)

    db.add(make_outbox_event(agent, OutboxEventType.updated))
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        _raise_conflict()
    await db.refresh(agent)
    return agent  # type: ignore[return-value]


@router.post("/agents/{agent_id}/deploy", response_model=AgentResponse, tags=["agents"])
async def deploy_agent(agent_id: str, db: AsyncSession = Depends(get_db)) -> Agent:
    result = await db.execute(select(Agent).where(Agent.id == agent_id))
    agent = result.scalar_one_or_none()
    if agent is None:
        _raise_not_found()
    if agent.deployment_state == DeploymentState.running:
        raise HTTPException(status_code=409, detail="Agent is already running")
    agent.deployment_state = DeploymentState.running
    db.add(make_outbox_event(agent, OutboxEventType.updated))
    await db.commit()
    await db.refresh(agent)
    return agent  # type: ignore[return-value]


@router.post("/agents/{agent_id}/stop", response_model=AgentResponse, tags=["agents"])
async def stop_agent(agent_id: str, db: AsyncSession = Depends(get_db)) -> Agent:
    result = await db.execute(select(Agent).where(Agent.id == agent_id))
    agent = result.scalar_one_or_none()
    if agent is None:
        _raise_not_found()
    if agent.deployment_state != DeploymentState.running:
        raise HTTPException(status_code=409, detail="Agent is not running")
    agent.deployment_state = DeploymentState.stopped
    db.add(make_outbox_event(agent, OutboxEventType.stopped))
    await db.commit()
    await db.refresh(agent)
    return agent  # type: ignore[return-value]


@router.delete("/agents/{agent_id}", status_code=204, tags=["agents"])
async def delete_agent(agent_id: str, db: AsyncSession = Depends(get_db)) -> None:
    result = await db.execute(select(Agent).where(Agent.id == agent_id))
    agent = result.scalar_one_or_none()
    if agent is None:
        _raise_not_found()
    db.add(make_outbox_event(agent, OutboxEventType.deleted))
    await db.delete(agent)
    await db.commit()
