import pytest


# test workspace creation
@pytest.mark.asyncio
async def test_create_workspace(client):
    payload = {"name": "Test Workspace"}
    response = await client.post("/workspaces", json=payload)
    assert response.status_code == 201
    data = response.json()
    assert data["name"] == payload["name"]


# test workspace listing
@pytest.mark.asyncio
async def test_list_workspaces(client):
    response = await client.get("/workspaces")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)


# test workspace update
@pytest.mark.asyncio
async def test_update_workspace(client):
    # First, create a workspace
    payload = {"name": "Test Workspace"}
    response = await client.post("/workspaces", json=payload)
    assert response.status_code == 201
    workspace_id = response.json()["id"]

    # Then, update the workspace
    update_payload = {"name": "Updated Test Workspace"}
    response = await client.patch(f"/workspaces/{workspace_id}", json=update_payload)
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == update_payload["name"]


# test workspace deletion
@pytest.mark.asyncio
async def test_delete_workspace(client):
    # First, create a workspace
    payload = {"name": "Test Workspace"}
    response = await client.post("/workspaces", json=payload)
    assert response.status_code == 201
    workspace_id = response.json()["id"]

    # Then, delete the workspace
    response = await client.delete(f"/workspaces/{workspace_id}")
    assert response.status_code == 204


@pytest.mark.asyncio
async def test_delete_workspace_requires_privileged_mode(unprivileged_client):
    response = await unprivileged_client.post(
        "/workspaces", json={"name": "Restricted WS"}
    )
    assert response.status_code == 201
    workspace_id = response.json()["id"]

    delete_res = await unprivileged_client.delete(f"/workspaces/{workspace_id}")
    assert delete_res.status_code == 403
    assert "privileged mode required" in delete_res.json()["detail"].lower()
