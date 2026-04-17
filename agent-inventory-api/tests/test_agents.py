from httpx import AsyncClient


async def test_create_agent(client: AsyncClient) -> None:
    response = await client.post(
        "/api/v1/agents",
        json={"name": "test-agent", "description": "A test agent"},
    )
    assert response.status_code == 201
    body = response.json()
    assert body["name"] == "test-agent"
    assert body["description"] == "A test agent"
    assert body["status"] == "active"
    assert "id" in body
    assert "created_at" in body
    assert "updated_at" in body


async def test_list_agents(client: AsyncClient) -> None:
    await client.post("/api/v1/agents", json={"name": "agent-list-1"})
    await client.post("/api/v1/agents", json={"name": "agent-list-2"})

    response = await client.get("/api/v1/agents")
    assert response.status_code == 200
    body = response.json()
    assert isinstance(body, list)
    names = [a["name"] for a in body]
    assert "agent-list-1" in names
    assert "agent-list-2" in names


async def test_get_agent(client: AsyncClient) -> None:
    create_resp = await client.post("/api/v1/agents", json={"name": "get-me"})
    agent_id = create_resp.json()["id"]

    response = await client.get(f"/api/v1/agents/{agent_id}")
    assert response.status_code == 200
    assert response.json()["id"] == agent_id
    assert response.json()["name"] == "get-me"


async def test_get_agent_not_found(client: AsyncClient) -> None:
    response = await client.get("/api/v1/agents/nonexistent-id")
    assert response.status_code == 404
    assert response.json()["detail"] == "Agent not found"
