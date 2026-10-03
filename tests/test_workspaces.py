from datetime import datetime

import pytest
import pytest_asyncio

from backend.database.querying import delete_workspace_by_id
from backend.models.entry import EntryCreate
from backend.models.journal import JournalCreate
from backend.models.workspace import WorkspaceCreate, WorkspaceOut

WORKSPACE_NAME = "test-workspace"


@pytest_asyncio.fixture()
async def clear_workspace():
    workspace_ids = []
    yield workspace_ids
    for workspace_id in workspace_ids:
        delete_workspace_by_id(workspace_id)


# test workspace creation
@pytest.mark.asyncio
async def test_create_workspace(client, clear_workspace):
    payload = WorkspaceCreate(name=WORKSPACE_NAME).model_dump()
    response = await client.post("/workspaces", json=payload)
    assert response.status_code == 201
    data = response.json()
    WorkspaceOut.model_validate(data)
    assert data["name"] == payload["name"]
    clear_workspace.append(data["id"])


# test workspace listing
@pytest.mark.asyncio
async def test_list_workspaces(client, clear_workspace):
    # create 3 workspaces
    workspace_ids = []
    for i in range(3):
        payload = WorkspaceCreate(name=f"{WORKSPACE_NAME}_{i}").model_dump()
        response = await client.post("/workspaces", json=payload)
        assert response.status_code == 201
        data = response.json()
        workspace_ids.append(data["id"])
    clear_workspace.extend(workspace_ids)

    # list all workspaces and verify the created ones are present
    response = await client.get("/workspaces")
    assert response.status_code == 200
    data = response.json()
    for workspace_id in workspace_ids:
        assert any(item["id"] == workspace_id for item in data)
        assert any(
            item["name"] == f"{WORKSPACE_NAME}_{workspace_ids.index(workspace_id)}"
            for item in data
        )


# test workspace update
@pytest.mark.asyncio
async def test_update_workspace(client, clear_workspace):
    # First, create a workspace
    payload = WorkspaceCreate(name=WORKSPACE_NAME).model_dump()
    response = await client.post("/workspaces", json=payload)
    assert response.status_code == 201
    data = response.json()
    workspace_id = data["id"]
    clear_workspace.append(workspace_id)

    # Then, update the workspace
    update_payload = {"name": f"{WORKSPACE_NAME}_updated"}
    response = await client.patch(f"/workspaces/{workspace_id}", json=update_payload)
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == update_payload["name"]


# test workspace deletion
@pytest.mark.asyncio
async def test_delete_workspace(client, clear_workspace):
    # First, create a workspace
    payload = WorkspaceCreate(name=WORKSPACE_NAME).model_dump()
    response = await client.post("/workspaces", json=payload)
    assert response.status_code == 201
    workspace_id = response.json()["id"]
    clear_workspace.append(workspace_id)

    journal_payload = JournalCreate(
        name="Workspace Bin Journal", description=""
    ).model_dump()
    journal_res = await client.post(
        f"/workspaces/{workspace_id}/journals", json=journal_payload
    )
    assert journal_res.status_code == 201
    journal_id = journal_res.json()["id"]

    entry_payload = EntryCreate(
        name="Workspace Bin Entry",
        tags=["workspace_delete_type"],
        body={"ops": [{"insert": "Bin me with the workspace\n"}]},
        custom_metadata=[],
        date_created=datetime(2026, 1, 1, 0, 0, 0),
        timezone="UTC",
    ).model_dump(mode="json")
    entry_res = await client.post(
        f"/journals/{journal_id}/entries",
        json=entry_payload,
    )
    assert entry_res.status_code == 201
    entry_id = entry_res.json()["id"]

    # Then, delete the workspace
    response = await client.delete(f"/workspaces/{workspace_id}")
    assert response.status_code == 204

    workspaces_res = await client.get("/workspaces")
    assert all(item["id"] != workspace_id for item in workspaces_res.json())

    # Ensure the journal and entry are also deleted
    journal_res = await client.get(f"workspaces/{workspace_id}/journals/{journal_id}")
    assert journal_res.status_code == 404

    entry_res = await client.get(f"/entries/{entry_id}")
    assert entry_res.status_code == 404


@pytest.mark.asyncio
async def test_delete_workspace_requires_privileged_mode(
    unprivileged_client, clear_workspace
):
    ws_payload = WorkspaceCreate(name="Restricted WS").model_dump()
    response = await unprivileged_client.post("/workspaces", json=ws_payload)
    assert response.status_code == 201
    workspace_id = response.json()["id"]
    clear_workspace.append(workspace_id)

    delete_res = await unprivileged_client.delete(f"/workspaces/{workspace_id}")
    assert delete_res.status_code == 403
    assert "privileged mode required" in delete_res.json()["detail"].lower()
