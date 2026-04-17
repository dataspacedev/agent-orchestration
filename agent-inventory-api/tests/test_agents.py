from httpx import AsyncClient


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

AGENT_SPEC = {"image": "my-agent:1.0.0"}

AGENT_V1 = {"name": "test-agent", "version": "1.0.0", "description": "A test agent", "spec": AGENT_SPEC}
AGENT_V2 = {"name": "test-agent", "version": "2.0.0", "spec": AGENT_SPEC}

FULL_SPEC = {
    "image": "my-agent:2.0.0",
    "port": 9090,
    "secret_name": "my-secret",
    "config": {"LOG_LEVEL": "info", "TIMEOUT": "30"},
    "resources": {
        "requests": {"cpu": "100m", "memory": "128Mi"},
        "limits": {"cpu": "500m", "memory": "512Mi"},
    },
    "scaling": {
        "min_replicas": 2,
        "max_replicas": 10,
        "target_cpu_utilization_percentage": 70,
    },
}


# ---------------------------------------------------------------------------
# POST /agents
# ---------------------------------------------------------------------------


async def test_create_agent(client: AsyncClient) -> None:
    response = await client.post("/api/v1/agents", json=AGENT_V1)
    assert response.status_code == 201
    body = response.json()
    assert body["name"] == "test-agent"
    assert body["version"] == "1.0.0"
    assert body["description"] == "A test agent"
    assert body["status"] == "active"
    assert body["deployment_state"] == "running"
    assert body["spec"]["image"] == "my-agent:1.0.0"
    assert "id" in body
    assert "created_at" in body
    assert "updated_at" in body


async def test_create_agent_with_full_spec(client: AsyncClient) -> None:
    payload = {"name": "full-spec-agent", "version": "1.0.0", "spec": FULL_SPEC}
    response = await client.post("/api/v1/agents", json=payload)
    assert response.status_code == 201
    spec = response.json()["spec"]
    assert spec["image"] == "my-agent:2.0.0"
    assert spec["port"] == 9090
    assert spec["secret_name"] == "my-secret"
    assert spec["config"] == {"LOG_LEVEL": "info", "TIMEOUT": "30"}
    assert spec["resources"]["requests"] == {"cpu": "100m", "memory": "128Mi"}
    assert spec["scaling"]["min_replicas"] == 2
    assert spec["scaling"]["target_cpu_utilization_percentage"] == 70


async def test_create_agent_missing_spec_returns_422(client: AsyncClient) -> None:
    response = await client.post("/api/v1/agents", json={"name": "no-spec", "version": "1.0.0"})
    assert response.status_code == 422


async def test_create_agent_invalid_port_returns_422(client: AsyncClient) -> None:
    response = await client.post(
        "/api/v1/agents",
        json={"name": "bad-port", "version": "1.0.0", "spec": {"image": "x:1", "port": 99999}},
    )
    assert response.status_code == 422


async def test_create_agent_invalid_cpu_utilization_returns_422(client: AsyncClient) -> None:
    response = await client.post(
        "/api/v1/agents",
        json={
            "name": "bad-cpu",
            "version": "1.0.0",
            "spec": {"image": "x:1", "scaling": {"target_cpu_utilization_percentage": 101}},
        },
    )
    assert response.status_code == 422


async def test_create_agent_custom_deployment_state(client: AsyncClient) -> None:
    response = await client.post(
        "/api/v1/agents",
        json={"name": "stopped-agent", "version": "1.0.0", "deployment_state": "stopped", "spec": AGENT_SPEC},
    )
    assert response.status_code == 201
    assert response.json()["deployment_state"] == "stopped"


async def test_create_agent_invalid_deployment_state(client: AsyncClient) -> None:
    response = await client.post(
        "/api/v1/agents",
        json={"name": "bad-agent", "version": "1.0.0", "deployment_state": "invalid", "spec": AGENT_SPEC},
    )
    assert response.status_code == 422


async def test_create_agent_duplicate_name_version_returns_409(client: AsyncClient) -> None:
    await client.post("/api/v1/agents", json=AGENT_V1)
    response = await client.post("/api/v1/agents", json=AGENT_V1)
    assert response.status_code == 409
    assert "already exists" in response.json()["detail"]


async def test_create_agent_same_name_different_version_ok(client: AsyncClient) -> None:
    r1 = await client.post("/api/v1/agents", json=AGENT_V1)
    r2 = await client.post("/api/v1/agents", json=AGENT_V2)
    assert r1.status_code == 201
    assert r2.status_code == 201
    assert r1.json()["id"] != r2.json()["id"]


# ---------------------------------------------------------------------------
# GET /agents
# ---------------------------------------------------------------------------


async def test_list_agents(client: AsyncClient) -> None:
    await client.post("/api/v1/agents", json={"name": "agent-list-1", "version": "1.0.0", "spec": AGENT_SPEC})
    await client.post("/api/v1/agents", json={"name": "agent-list-2", "version": "1.0.0", "spec": AGENT_SPEC})

    response = await client.get("/api/v1/agents")
    assert response.status_code == 200
    body = response.json()
    assert isinstance(body, list)
    names = [a["name"] for a in body]
    assert "agent-list-1" in names
    assert "agent-list-2" in names


# ---------------------------------------------------------------------------
# GET /agents/{agent_id}
# ---------------------------------------------------------------------------


async def test_get_agent(client: AsyncClient) -> None:
    create_resp = await client.post("/api/v1/agents", json={"name": "get-me", "version": "1.0.0", "spec": AGENT_SPEC})
    agent_id = create_resp.json()["id"]

    response = await client.get(f"/api/v1/agents/{agent_id}")
    assert response.status_code == 200
    body = response.json()
    assert body["id"] == agent_id
    assert body["name"] == "get-me"
    assert body["version"] == "1.0.0"
    assert body["spec"]["image"] == "my-agent:1.0.0"


async def test_get_agent_not_found(client: AsyncClient) -> None:
    response = await client.get("/api/v1/agents/nonexistent-id")
    assert response.status_code == 404
    assert response.json()["detail"] == "Agent not found"


# ---------------------------------------------------------------------------
# PATCH /agents/{agent_id}
# ---------------------------------------------------------------------------


async def test_patch_agent_partial_update(client: AsyncClient) -> None:
    create_resp = await client.post("/api/v1/agents", json=AGENT_V1)
    agent_id = create_resp.json()["id"]
    original_name = create_resp.json()["name"]

    response = await client.patch(
        f"/api/v1/agents/{agent_id}",
        json={"deployment_state": "stopped"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["deployment_state"] == "stopped"
    # Unchanged fields are preserved
    assert body["name"] == original_name
    assert body["version"] == "1.0.0"
    assert body["spec"]["image"] == "my-agent:1.0.0"


async def test_patch_agent_spec_update(client: AsyncClient) -> None:
    create_resp = await client.post("/api/v1/agents", json=AGENT_V1)
    agent_id = create_resp.json()["id"]

    new_spec = {"image": "my-agent:2.0.0", "port": 8081}
    response = await client.patch(f"/api/v1/agents/{agent_id}", json={"spec": new_spec})
    assert response.status_code == 200
    spec = response.json()["spec"]
    assert spec["image"] == "my-agent:2.0.0"
    assert spec["port"] == 8081


async def test_patch_agent_update_version(client: AsyncClient) -> None:
    create_resp = await client.post("/api/v1/agents", json=AGENT_V1)
    agent_id = create_resp.json()["id"]

    response = await client.patch(f"/api/v1/agents/{agent_id}", json={"version": "1.1.0"})
    assert response.status_code == 200
    assert response.json()["version"] == "1.1.0"


async def test_patch_agent_update_name_and_version(client: AsyncClient) -> None:
    create_resp = await client.post("/api/v1/agents", json=AGENT_V1)
    agent_id = create_resp.json()["id"]

    response = await client.patch(
        f"/api/v1/agents/{agent_id}",
        json={"name": "renamed-agent", "version": "3.0.0"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["name"] == "renamed-agent"
    assert body["version"] == "3.0.0"


async def test_patch_agent_conflict_returns_409(client: AsyncClient) -> None:
    await client.post("/api/v1/agents", json=AGENT_V1)
    r2 = await client.post("/api/v1/agents", json=AGENT_V2)
    agent2_id = r2.json()["id"]

    # Try to patch agent2 to have the same name+version as agent1
    response = await client.patch(
        f"/api/v1/agents/{agent2_id}",
        json={"version": "1.0.0"},
    )
    assert response.status_code == 409


async def test_patch_agent_not_found(client: AsyncClient) -> None:
    response = await client.patch("/api/v1/agents/nonexistent-id", json={"status": "inactive"})
    assert response.status_code == 404


async def test_patch_agent_deployment_state_all_values(client: AsyncClient) -> None:
    for state in ("running", "stopped", "deleted"):
        create_resp = await client.post(
            "/api/v1/agents",
            json={"name": f"agent-{state}", "version": "1.0.0", "spec": AGENT_SPEC},
        )
        agent_id = create_resp.json()["id"]
        response = await client.patch(
            f"/api/v1/agents/{agent_id}", json={"deployment_state": state}
        )
        assert response.status_code == 200
        assert response.json()["deployment_state"] == state


# ---------------------------------------------------------------------------
# DELETE /agents/{agent_id}
# ---------------------------------------------------------------------------


async def test_delete_agent(client: AsyncClient) -> None:
    create_resp = await client.post("/api/v1/agents", json=AGENT_V1)
    agent_id = create_resp.json()["id"]

    delete_resp = await client.delete(f"/api/v1/agents/{agent_id}")
    assert delete_resp.status_code == 204

    get_resp = await client.get(f"/api/v1/agents/{agent_id}")
    assert get_resp.status_code == 404


async def test_delete_agent_not_found(client: AsyncClient) -> None:
    response = await client.delete("/api/v1/agents/nonexistent-id")
    assert response.status_code == 404


async def test_delete_agent_frees_name_version_slot(client: AsyncClient) -> None:
    """After deletion the same name+version can be re-created."""
    create_resp = await client.post("/api/v1/agents", json=AGENT_V1)
    agent_id = create_resp.json()["id"]

    await client.delete(f"/api/v1/agents/{agent_id}")

    recreate_resp = await client.post("/api/v1/agents", json=AGENT_V1)
    assert recreate_resp.status_code == 201
