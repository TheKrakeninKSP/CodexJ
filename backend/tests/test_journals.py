import pytest


# test journal creation
@pytest.mark.asyncio
async def test_create_journal(client):
    ws_payload = {"name": "Test Workspace"}
    ws_res = await client.post("/workspaces", json=ws_payload)
    assert ws_res.status_code == 201

    workspace_id = ws_res.json()["id"]
    payload = {"name": "Test Journal"}
    response = await client.post(f"/workspaces/{workspace_id}/journals", json=payload)
    assert response.status_code == 201
    data = response.json()
    assert data["name"] == payload["name"]


# test journal listing by creation 3 journals and check existence of all 3
@pytest.mark.asyncio
async def test_list_journals(client):
    ws_payload = {"name": "Test Workspace"}
    ws_res = await client.post("/workspaces", json=ws_payload)
    assert ws_res.status_code == 201

    workspace_id = ws_res.json()["id"]
    journal_names = ["Journal 1", "Journal 2", "Journal 3"]
    for name in journal_names:
        payload = {"name": name}
        response = await client.post(
            f"/workspaces/{workspace_id}/journals", json=payload
        )
        assert response.status_code == 201

    list_response = await client.get(f"/workspaces/{workspace_id}/journals")
    assert list_response.status_code == 200
    data = list_response.json()
    returned_names = [j["name"] for j in data]
    for name in journal_names:
        assert name in returned_names


# test journal update
@pytest.mark.asyncio
async def test_update_journal(client):
    ws_payload = {"name": "Test Workspace"}
    ws_res = await client.post("/workspaces", json=ws_payload)
    assert ws_res.status_code == 201

    workspace_id = ws_res.json()["id"]
    journal_payload = {"name": "Test Journal"}
    journal_res = await client.post(
        f"/workspaces/{workspace_id}/journals", json=journal_payload
    )
    assert journal_res.status_code == 201
    journal_id = journal_res.json()["id"]

    update_payload = {"name": "Updated Test Journal"}
    response = await client.patch(
        f"/workspaces/{workspace_id}/journals/{journal_id}", json=update_payload
    )
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == update_payload["name"]


# test journal deletion
@pytest.mark.asyncio
async def test_delete_journal(client):
    ws_payload = {"name": "Test Workspace"}
    ws_res = await client.post("/workspaces", json=ws_payload)
    assert ws_res.status_code == 201

    workspace_id = ws_res.json()["id"]
    journal_payload = {"name": "Test Journal"}
    journal_res = await client.post(
        f"/workspaces/{workspace_id}/journals", json=journal_payload
    )
    assert journal_res.status_code == 201
    journal_id = journal_res.json()["id"]

    entry_res = await client.post(
        f"/journals/{journal_id}/entries",
        json={
            "type": "journal_delete_type",
            "body": {"ops": [{"insert": "Bin me with the journal\n"}]},
            "name": "Journal Bin Entry",
        },
    )
    assert entry_res.status_code == 201
    entry_id = entry_res.json()["id"]

    response = await client.delete(f"/workspaces/{workspace_id}/journals/{journal_id}")
    assert response.status_code == 204

    # Verify the journal is deleted
    get_response = await client.get(f"/workspaces/{workspace_id}/journals/{journal_id}")
    assert get_response.status_code == 404

    bin_res = await client.get("/entries/bin")
    assert bin_res.status_code == 200
    binned_entry = next(item for item in bin_res.json() if item["id"] == entry_id)
    assert binned_entry["deleted_from_workspace_id"] == workspace_id
    assert binned_entry["deleted_from_journal_id"] == journal_id


@pytest.mark.asyncio
async def test_delete_journal_requires_privileged_mode(unprivileged_client):
    ws_res = await unprivileged_client.post(
        "/workspaces", json={"name": "Restricted WS"}
    )
    assert ws_res.status_code == 201
    workspace_id = ws_res.json()["id"]

    journal_res = await unprivileged_client.post(
        f"/workspaces/{workspace_id}/journals",
        json={"name": "Restricted Journal"},
    )
    assert journal_res.status_code == 201
    journal_id = journal_res.json()["id"]

    delete_res = await unprivileged_client.delete(
        f"/workspaces/{workspace_id}/journals/{journal_id}"
    )
    assert delete_res.status_code == 403
    assert "privileged mode required" in delete_res.json()["detail"].lower()
