import pytest


# test entry type creation
@pytest.mark.asyncio
async def test_create_entry_type(client):
    ws_payload = {"name": "Test Workspace"}
    ws_res = await client.post("/workspaces", json=ws_payload)
    assert ws_res.status_code == 201
    workspace_id = ws_res.json()["id"]

    jr_payload = {"name": "Test Journal"}
    jr_res = await client.post(f"/workspaces/{workspace_id}/journals", json=jr_payload)
    assert jr_res.status_code == 201
    journal_id = jr_res.json()["id"]

    payload = {"name": "Test Entry Type"}
    response = await client.post(f"/entry-types", json=payload)
    assert response.status_code == 201
    data = response.json()
    assert data["name"] == payload["name"]


# test entry type listing by creating 3 entry types and checking existence of all 3
@pytest.mark.asyncio
async def test_list_entry_types(client):
    ws_payload = {"name": "Test Workspace"}
    ws_res = await client.post("/workspaces", json=ws_payload)
    assert ws_res.status_code == 201
    workspace_id = ws_res.json()["id"]

    jr_payload = {"name": "Test Journal"}
    jr_res = await client.post(f"/workspaces/{workspace_id}/journals", json=jr_payload)
    assert jr_res.status_code == 201
    journal_id = jr_res.json()["id"]

    entry_type_names = ["Type 1", "Type 2", "Type 3"]
    for name in entry_type_names:
        payload = {"name": name}
        response = await client.post(f"/entry-types", json=payload)
        assert response.status_code == 201

    list_response = await client.get(f"/entry-types")
    assert list_response.status_code == 200
    data = list_response.json()
    returned_names = [et["name"] for et in data]
    for name in entry_type_names:
        assert name in returned_names


# test entry type deletion
@pytest.mark.asyncio
async def test_delete_entry_type(client):
    ws_payload = {"name": "Test Workspace"}
    ws_res = await client.post("/workspaces", json=ws_payload)
    assert ws_res.status_code == 201
    workspace_id = ws_res.json()["id"]

    jr_payload = {"name": "Test Journal"}
    jr_res = await client.post(f"/workspaces/{workspace_id}/journals", json=jr_payload)
    assert jr_res.status_code == 201
    journal_id = jr_res.json()["id"]

    payload = {"name": "Test Entry Type"}
    response = await client.post(f"/entry-types", json=payload)
    assert response.status_code == 201
    entry_type_id = response.json()["id"]

    delete_response = await client.delete(f"/entry-types/{entry_type_id}")
    assert delete_response.status_code == 204

    # Verify the entry type is deleted
    list_response = await client.get(f"/entry-types")
    assert list_response.status_code == 200
    data = list_response.json()
    for et in data:
        assert et["id"] != entry_type_id
