import pytest


@pytest.mark.asyncio
async def test_create_entry_type(client):
    ws_payload = {"name": "Test Workspace"}
    ws_res = await client.post("/workspaces", json=ws_payload)
    assert ws_res.status_code == 201
    workspace_id = ws_res.json()["id"]

    payload = {"name": "Test Entry Type"}
    response = await client.post(
        f"/workspaces/{workspace_id}/entry-types", json=payload
    )
    assert response.status_code == 201
    data = response.json()
    assert data["name"] == payload["name"]
    assert data["entry_count"] == 0


@pytest.mark.asyncio
async def test_list_entry_types(client):
    ws_payload = {"name": "Test Workspace"}
    ws_res = await client.post("/workspaces", json=ws_payload)
    assert ws_res.status_code == 201
    workspace_id = ws_res.json()["id"]

    entry_type_names = ["Type 1", "Type 2", "Type 3"]
    for name in entry_type_names:
        payload = {"name": name}
        response = await client.post(
            f"/workspaces/{workspace_id}/entry-types", json=payload
        )
        assert response.status_code == 201

    list_response = await client.get(f"/workspaces/{workspace_id}/entry-types")
    assert list_response.status_code == 200
    data = list_response.json()
    returned_names = [et["name"] for et in data]
    for name in entry_type_names:
        assert name in returned_names
    assert all(entry_type["entry_count"] == 0 for entry_type in data)


@pytest.mark.asyncio
async def test_delete_entry_type(client):
    ws_payload = {"name": "Test Workspace"}
    ws_res = await client.post("/workspaces", json=ws_payload)
    assert ws_res.status_code == 201
    workspace_id = ws_res.json()["id"]

    payload = {"name": "Test Entry Type"}
    response = await client.post(
        f"/workspaces/{workspace_id}/entry-types", json=payload
    )
    assert response.status_code == 201
    entry_type_id = response.json()["id"]

    delete_response = await client.delete(
        f"/workspaces/{workspace_id}/entry-types/{entry_type_id}"
    )
    assert delete_response.status_code == 204

    list_response = await client.get(f"/workspaces/{workspace_id}/entry-types")
    assert list_response.status_code == 200
    data = list_response.json()
    for et in data:
        assert et["id"] != entry_type_id


@pytest.mark.asyncio
async def test_entry_types_are_workspace_scoped(client):
    first_workspace_res = await client.post("/workspaces", json={"name": "Workspace A"})
    second_workspace_res = await client.post(
        "/workspaces", json={"name": "Workspace B"}
    )
    first_workspace_id = first_workspace_res.json()["id"]
    second_workspace_id = second_workspace_res.json()["id"]

    payload = {"name": "Shared Name"}
    first_create = await client.post(
        f"/workspaces/{first_workspace_id}/entry-types", json=payload
    )
    second_create = await client.post(
        f"/workspaces/{second_workspace_id}/entry-types", json=payload
    )

    assert first_create.status_code == 201
    assert second_create.status_code == 201
    assert first_create.json()["id"] != second_create.json()["id"]

    first_list = await client.get(f"/workspaces/{first_workspace_id}/entry-types")
    second_list = await client.get(f"/workspaces/{second_workspace_id}/entry-types")

    assert [entry_type["name"] for entry_type in first_list.json()] == ["Shared Name"]
    assert [entry_type["name"] for entry_type in second_list.json()] == ["Shared Name"]


@pytest.mark.asyncio
async def test_delete_entry_type_blocks_when_type_is_in_use(client):
    ws_res = await client.post("/workspaces", json={"name": "In Use Workspace"})
    assert ws_res.status_code == 201
    workspace_id = ws_res.json()["id"]

    jr_res = await client.post(
        f"/workspaces/{workspace_id}/journals",
        json={"name": "In Use Journal"},
    )
    assert jr_res.status_code == 201
    journal_id = jr_res.json()["id"]

    entry_type_res = await client.post(
        f"/workspaces/{workspace_id}/entry-types",
        json={"name": "Locked Type"},
    )
    assert entry_type_res.status_code == 201
    entry_type_id = entry_type_res.json()["id"]

    entry_res = await client.post(
        f"/journals/{journal_id}/entries",
        json={
            "tags": ["Locked Type"],
            "body": {"ops": [{"insert": "Type still in use\n"}]},
            "name": "Uses Locked Type",
            "custom_metadata": [],
        },
    )
    assert entry_res.status_code == 201

    delete_response = await client.delete(
        f"/workspaces/{workspace_id}/entry-types/{entry_type_id}"
    )
    assert delete_response.status_code == 409
    assert "still referenced" in delete_response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_list_entry_types_backfills_existing_workspace_entries(client):
    ws_res = await client.post("/workspaces", json={"name": "Backfill Workspace"})
    assert ws_res.status_code == 201
    workspace_id = ws_res.json()["id"]

    jr_res = await client.post(
        f"/workspaces/{workspace_id}/journals",
        json={"name": "Backfill Journal"},
    )
    assert jr_res.status_code == 201
    journal_id = jr_res.json()["id"]

    entry_res = await client.post(
        f"/journals/{journal_id}/entries",
        json={
            "tags": ["Recovered Type"],
            "body": {"ops": [{"insert": "Legacy entry type\n"}]},
            "name": "Legacy Entry",
            "custom_metadata": [],
        },
    )
    assert entry_res.status_code == 201

    list_response = await client.get(f"/workspaces/{workspace_id}/entry-types")
    assert list_response.status_code == 200
    assert [entry_type["name"] for entry_type in list_response.json()] == [
        "Recovered Type"
    ]
    assert list_response.json()[0]["entry_count"] == 1


@pytest.mark.asyncio
async def test_list_entry_types_returns_entry_counts(client):
    ws_res = await client.post("/workspaces", json={"name": "Count Workspace"})
    assert ws_res.status_code == 201
    workspace_id = ws_res.json()["id"]

    first_journal_res = await client.post(
        f"/workspaces/{workspace_id}/journals",
        json={"name": "Count Journal One"},
    )
    second_journal_res = await client.post(
        f"/workspaces/{workspace_id}/journals",
        json={"name": "Count Journal Two"},
    )
    first_journal_id = first_journal_res.json()["id"]
    second_journal_id = second_journal_res.json()["id"]

    await client.post(
        f"/workspaces/{workspace_id}/entry-types",
        json={"name": "Frequent"},
    )
    await client.post(
        f"/workspaces/{workspace_id}/entry-types",
        json={"name": "Rare"},
    )

    for journal_id in (first_journal_id, second_journal_id):
        entry_res = await client.post(
            f"/journals/{journal_id}/entries",
            json={
                "tags": ["Frequent"],
                "body": {"ops": [{"insert": "Count me\n"}]},
                "name": f"Entry {journal_id}",
                "custom_metadata": [],
            },
        )
        assert entry_res.status_code == 201

    rare_entry_res = await client.post(
        f"/journals/{first_journal_id}/entries",
        json={
            "tags": ["Rare"],
            "body": {"ops": [{"insert": "Only once\n"}]},
            "name": "Rare Entry",
            "custom_metadata": [],
        },
    )
    assert rare_entry_res.status_code == 201

    list_response = await client.get(f"/workspaces/{workspace_id}/entry-types")
    assert list_response.status_code == 200
    counts_by_name = {
        entry_type["name"]: entry_type["entry_count"]
        for entry_type in list_response.json()
    }
    assert counts_by_name["Frequent"] == 2
    assert counts_by_name["Rare"] == 1


@pytest.mark.asyncio
async def test_multi_tag_entry_counts_toward_both_types(client):
    ws_res = await client.post("/workspaces", json={"name": "Multi-Tag Count WS"})
    workspace_id = ws_res.json()["id"]
    jr_res = await client.post(
        f"/workspaces/{workspace_id}/journals", json={"name": "Multi-Tag Count Journal"}
    )
    journal_id = jr_res.json()["id"]

    entry_res = await client.post(
        f"/journals/{journal_id}/entries",
        json={
            "tags": ["TypeA", "TypeB"],
            "name": "Multi-Tag",
            "body": {"ops": [{"insert": "Has two tags\n"}]},
        },
    )
    assert entry_res.status_code == 201

    list_response = await client.get(f"/workspaces/{workspace_id}/entry-types")
    assert list_response.status_code == 200
    counts_by_name = {et["name"]: et["entry_count"] for et in list_response.json()}
    assert counts_by_name.get("TypeA") == 1
    assert counts_by_name.get("TypeB") == 1
