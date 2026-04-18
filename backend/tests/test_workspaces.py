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

    journal_res = await client.post(
        f"/workspaces/{workspace_id}/journals", json={"name": "Workspace Bin Journal"}
    )
    journal_id = journal_res.json()["id"]
    entry_res = await client.post(
        f"/journals/{journal_id}/entries",
        json={
            "tags": ["workspace_delete_type"],
            "body": {"ops": [{"insert": "Bin me with the workspace\n"}]},
            "name": "Workspace Bin Entry",
        },
    )
    entry_id = entry_res.json()["id"]

    # Then, delete the workspace
    response = await client.delete(f"/workspaces/{workspace_id}")
    assert response.status_code == 204

    workspaces_res = await client.get("/workspaces")
    assert all(item["id"] != workspace_id for item in workspaces_res.json())

    bin_res = await client.get("/entries/bin")
    assert bin_res.status_code == 200
    binned_entry = next(item for item in bin_res.json() if item["id"] == entry_id)
    assert binned_entry["deleted_from_workspace_id"] == workspace_id
    assert binned_entry["deleted_from_journal_id"] == journal_id


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
