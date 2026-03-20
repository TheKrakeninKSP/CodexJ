import pytest
from bson import ObjectId


# test entry creation
@pytest.mark.asyncio
async def test_create_entry(client):
    ws_payload = {"name": "Test Workspace"}
    ws_res = await client.post("/workspaces", json=ws_payload)
    assert ws_res.status_code == 201
    workspace_id = ws_res.json()["id"]

    jr_payload = {"name": "Test Journal"}
    jr_res = await client.post(f"/workspaces/{workspace_id}/journals", json=jr_payload)
    assert jr_res.status_code == 201
    journal_id = jr_res.json()["id"]

    payload = {
        "type": "test_type",
        "body": {"ops": [{"insert": "Hello, world!\n"}]},
        "name": "test entry",
    }
    response = await client.post(f"/journals/{journal_id}/entries", json=payload)
    assert response.status_code == 201
    data = response.json()
    assert data["type"] == payload["type"]
    assert data["body"] == payload["body"]
    assert data["name"] == payload["name"]


# test entry listing by creating 3 entries and checking existence of all 3
@pytest.mark.asyncio
async def test_list_entries(client):
    ws_payload = {"name": "Test Workspace"}
    ws_res = await client.post("/workspaces", json=ws_payload)
    assert ws_res.status_code == 201
    workspace_id = ws_res.json()["id"]

    jr_payload = {"name": "Test Journal"}
    jr_res = await client.post(f"/workspaces/{workspace_id}/journals", json=jr_payload)
    assert jr_res.status_code == 201
    journal_id = jr_res.json()["id"]

    entry_names = ["Entry 1", "Entry 2", "Entry 3"]
    for name in entry_names:
        payload = {
            "type": "test_type",
            "body": {"ops": [{"insert": f"{name} content\n"}]},
            "name": name,
        }
        response = await client.post(f"/journals/{journal_id}/entries", json=payload)
        assert response.status_code == 201

    list_response = await client.get(f"/journals/{journal_id}/entries")
    assert list_response.status_code == 200
    data = list_response.json()
    returned_names = [e["name"] for e in data]
    for name in entry_names:
        assert name in returned_names


# test entry retrieval
@pytest.mark.asyncio
async def test_get_entry(client):
    ws_payload = {"name": "Test Workspace"}
    ws_res = await client.post("/workspaces", json=ws_payload)
    assert ws_res.status_code == 201
    workspace_id = ws_res.json()["id"]

    jr_payload = {"name": "Test Journal"}
    jr_res = await client.post(f"/workspaces/{workspace_id}/journals", json=jr_payload)
    assert jr_res.status_code == 201
    journal_id = jr_res.json()["id"]

    payload = {
        "type": "test_type",
        "body": {"ops": [{"insert": "Hello, world!\n"}]},
        "name": "test entry",
    }
    create_response = await client.post(f"/journals/{journal_id}/entries", json=payload)
    assert create_response.status_code == 201
    entry_id = create_response.json()["id"]

    get_response = await client.get(f"/entries/{entry_id}")
    assert get_response.status_code == 200
    data = get_response.json()
    assert data["type"] == payload["type"]
    assert data["body"] == payload["body"]
    assert data["name"] == payload["name"]


# test entry retrieval with invalid id
@pytest.mark.asyncio
async def test_get_entry_invalid_id(client):
    ws_payload = {"name": "Test Workspace"}
    ws_res = await client.post("/workspaces", json=ws_payload)
    assert ws_res.status_code == 201
    workspace_id = ws_res.json()["id"]

    jr_payload = {"name": "Test Journal"}
    jr_res = await client.post(f"/workspaces/{workspace_id}/journals", json=jr_payload)
    assert jr_res.status_code == 201
    journal_id = jr_res.json()["id"]
    invalid_id = ObjectId()

    get_response = await client.get(f"/entries/{invalid_id}")
    assert get_response.status_code == 404


# test entry update
@pytest.mark.asyncio
async def test_update_entry(client):
    ws_payload = {"name": "Test Workspace"}
    ws_res = await client.post("/workspaces", json=ws_payload)
    assert ws_res.status_code == 201
    workspace_id = ws_res.json()["id"]

    jr_payload = {"name": "Test Journal"}
    jr_res = await client.post(f"/workspaces/{workspace_id}/journals", json=jr_payload)
    assert jr_res.status_code == 201
    journal_id = jr_res.json()["id"]

    payload = {
        "type": "test_type",
        "body": {"ops": [{"insert": "Hello, world!\n"}]},
        "name": "test entry",
    }
    create_response = await client.post(f"/journals/{journal_id}/entries", json=payload)
    assert create_response.status_code == 201
    entry_id = create_response.json()["id"]

    update_payload = {
        "type": "updated_type",
        "body": {"ops": [{"insert": "Updated content\n"}]},
        "name": "updated entry",
    }
    update_response = await client.patch(f"/entries/{entry_id}", json=update_payload)
    assert update_response.status_code == 200
    data = update_response.json()
    assert data["type"] == update_payload["type"]
    assert data["body"] == update_payload["body"]
    assert data["name"] == update_payload["name"]


# test entry deletion
@pytest.mark.asyncio
async def test_delete_entry(client):
    ws_payload = {"name": "Test Workspace"}
    ws_res = await client.post("/workspaces", json=ws_payload)
    assert ws_res.status_code == 201
    workspace_id = ws_res.json()["id"]

    jr_payload = {"name": "Test Journal"}
    jr_res = await client.post(f"/workspaces/{workspace_id}/journals", json=jr_payload)
    assert jr_res.status_code == 201
    journal_id = jr_res.json()["id"]

    payload = {
        "type": "test_type",
        "body": {"ops": [{"insert": "Hello, world!\n"}]},
        "name": "test entry",
    }
    create_response = await client.post(f"/journals/{journal_id}/entries", json=payload)
    assert create_response.status_code == 201
    entry_id = create_response.json()["id"]

    delete_response = await client.delete(f"/entries/{entry_id}")
    assert delete_response.status_code == 204

    get_response = await client.get(f"/entries/{entry_id}")
    assert get_response.status_code == 404
