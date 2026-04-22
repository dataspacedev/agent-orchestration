import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.agent import Agent
from app.db.models.outbox import AgentOutbox
from app.db.session import get_db
from app.k8s.client import make_crd_name
from app.models.agent import AgentCreate, AgentResponse, AgentUpdate

router = APIRouter()


def _raise_not_found() -> None:
    raise HTTPException(status_code=404, detail="Agent not found")


def _raise_conflict() -> None:
    raise HTTPException(
        status_code=409,
        detail="An agent with this name and version already exists",
    )


def _outbox_event(agent: Agent, event_type: str) -> AgentOutbox:
    crd_name = make_crd_name(agent.name, agent.version)
    payload: dict[str, Any] = {"crd_name": crd_name, "name": agent.name, "version": agent.version}
    if event_type != "DELETED":
        payload["spec"] = agent.spec or {}
    return AgentOutbox(
        id=str(uuid.uuid4()),
        agent_id=agent.id,
        event_type=event_type,
        payload=payload,
    )


@router.post("/agents", response_model=AgentResponse, status_code=201, tags=["agents"])
async def create_agent(payload: AgentCreate, db: AsyncSession = Depends(get_db)) -> Agent:
    agent = Agent(id=str(uuid.uuid4()), **payload.model_dump())
    db.add(agent)
    db.add(_outbox_event(agent, "CREATED"))
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

    db.add(_outbox_event(agent, "UPDATED"))
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        _raise_conflict()
    await db.refresh(agent)
    return agent  # type: ignore[return-value]


@router.delete("/agents/{agent_id}", status_code=204, tags=["agents"])
async def delete_agent(agent_id: str, db: AsyncSession = Depends(get_db)) -> None:
    result = await db.execute(select(Agent).where(Agent.id == agent_id))
    agent = result.scalar_one_or_none()
    if agent is None:
        _raise_not_found()
    db.add(_outbox_event(agent, "DELETED"))
    await db.delete(agent)
    await db.commit()
