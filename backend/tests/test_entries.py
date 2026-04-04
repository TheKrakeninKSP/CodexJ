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
        "timezone": "Asia/Kolkata",
    }
    response = await client.post(f"/journals/{journal_id}/entries", json=payload)
    assert response.status_code == 201
    data = response.json()
    assert data["type"] == payload["type"]
    assert data["body"] == payload["body"]
    assert data["name"] == payload["name"]
    assert data["timezone"] == payload["timezone"]
    assert data["is_deleted"] is False


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

    # update timezone
    tz_payload = {"timezone": "America/New_York"}
    tz_response = await client.patch(f"/entries/{entry_id}", json=tz_payload)
    assert tz_response.status_code == 200
    assert tz_response.json()["timezone"] == "America/New_York"

    # verify timezone persists on GET
    get_response = await client.get(f"/entries/{entry_id}")
    assert get_response.status_code == 200
    assert get_response.json()["timezone"] == "America/New_York"


# test entry deletion
@pytest.mark.asyncio
async def test_delete_entry(client):
    initial_count_res = await client.get("/entries/bin/count")
    assert initial_count_res.status_code == 200
    initial_count = initial_count_res.json()["count"]

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

    bin_response = await client.get("/entries/bin")
    assert bin_response.status_code == 200
    binned_entry = next(item for item in bin_response.json() if item["id"] == entry_id)
    assert binned_entry["is_deleted"] is True
    assert binned_entry["deleted_from_workspace_id"] == workspace_id
    assert binned_entry["deleted_from_journal_id"] == journal_id

    count_response = await client.get("/entries/bin/count")
    assert count_response.status_code == 200
    assert count_response.json()["count"] == initial_count + 1


@pytest.mark.asyncio
async def test_restore_entry(client):
    first_workspace_res = await client.post(
        "/workspaces", json={"name": "Restore Source WS"}
    )
    second_workspace_res = await client.post(
        "/workspaces", json={"name": "Restore Target WS"}
    )
    first_workspace_id = first_workspace_res.json()["id"]
    second_workspace_id = second_workspace_res.json()["id"]

    source_journal_res = await client.post(
        f"/workspaces/{first_workspace_id}/journals", json={"name": "Source Journal"}
    )
    target_journal_res = await client.post(
        f"/workspaces/{second_workspace_id}/journals", json={"name": "Target Journal"}
    )
    source_journal_id = source_journal_res.json()["id"]
    target_journal_id = target_journal_res.json()["id"]

    entry_res = await client.post(
        f"/journals/{source_journal_id}/entries",
        json={
            "type": "restore_type",
            "body": {"ops": [{"insert": "Restore me\n"}]},
            "name": "Restore Entry",
        },
    )
    entry_id = entry_res.json()["id"]

    delete_res = await client.delete(f"/entries/{entry_id}")
    assert delete_res.status_code == 204

    restore_res = await client.post(
        f"/entries/{entry_id}/restore",
        json={"workspace_id": second_workspace_id, "journal_id": target_journal_id},
    )
    assert restore_res.status_code == 200
    restored = restore_res.json()
    assert restored["journal_id"] == target_journal_id
    assert restored["is_deleted"] is False
    assert restored["deleted_at"] is None

    bin_res = await client.get("/entries/bin")
    assert all(item["id"] != entry_id for item in bin_res.json())

    target_entries = await client.get(f"/journals/{target_journal_id}/entries")
    assert any(item["id"] == entry_id for item in target_entries.json())


@pytest.mark.asyncio
async def test_purge_deleted_entry(client):
    initial_count_res = await client.get("/entries/bin/count")
    assert initial_count_res.status_code == 200
    initial_count = initial_count_res.json()["count"]

    ws_res = await client.post("/workspaces", json={"name": "Purge WS"})
    workspace_id = ws_res.json()["id"]
    jr_res = await client.post(
        f"/workspaces/{workspace_id}/journals", json={"name": "Purge Journal"}
    )
    journal_id = jr_res.json()["id"]

    entry_res = await client.post(
        f"/journals/{journal_id}/entries",
        json={
            "type": "purge_type",
            "body": {"ops": [{"insert": "Purge me\n"}]},
            "name": "Purge Entry",
        },
    )
    entry_id = entry_res.json()["id"]

    assert (await client.delete(f"/entries/{entry_id}")).status_code == 204

    deleted_count_res = await client.get("/entries/bin/count")
    assert deleted_count_res.status_code == 200
    assert deleted_count_res.json()["count"] == initial_count + 1

    purge_res = await client.delete(f"/entries/{entry_id}/purge")
    assert purge_res.status_code == 204

    bin_res = await client.get("/entries/bin")
    assert all(item["id"] != entry_id for item in bin_res.json())

    count_res = await client.get("/entries/bin/count")
    assert count_res.status_code == 200
    assert count_res.json()["count"] == initial_count


@pytest.mark.asyncio
async def test_search_entries_excludes_deleted_entries(client):
    ws_res = await client.post("/workspaces", json={"name": "Deleted Search WS"})
    workspace_id = ws_res.json()["id"]
    jr_res = await client.post(
        f"/workspaces/{workspace_id}/journals", json={"name": "Deleted Search Journal"}
    )
    journal_id = jr_res.json()["id"]

    entry_res = await client.post(
        f"/journals/{journal_id}/entries",
        json={
            "type": "search_type",
            "body": {"ops": [{"insert": "Look for vanished text\n"}]},
            "name": "Vanished Entry",
        },
    )
    entry_id = entry_res.json()["id"]
    assert (await client.delete(f"/entries/{entry_id}")).status_code == 204

    search_res = await client.get("/entries/search", params={"q": "vanished"})
    assert search_res.status_code == 200
    assert all(item["id"] != entry_id for item in search_res.json())


@pytest.mark.asyncio
async def test_delete_entry_requires_privileged_mode(unprivileged_client):
    ws_res = await unprivileged_client.post(
        "/workspaces", json={"name": "Unprivileged WS"}
    )
    assert ws_res.status_code == 201
    workspace_id = ws_res.json()["id"]

    jr_res = await unprivileged_client.post(
        f"/workspaces/{workspace_id}/journals",
        json={"name": "Unprivileged Journal"},
    )
    assert jr_res.status_code == 201
    journal_id = jr_res.json()["id"]

    entry_res = await unprivileged_client.post(
        f"/journals/{journal_id}/entries",
        json={
            "type": "test_type",
            "body": {"ops": [{"insert": "Restricted delete\n"}]},
            "name": "restricted entry",
        },
    )
    assert entry_res.status_code == 201

    delete_res = await unprivileged_client.delete(f"/entries/{entry_res.json()['id']}")
    assert delete_res.status_code == 403
    assert "privileged mode required" in delete_res.json()["detail"].lower()


@pytest.mark.asyncio
async def test_search_entries_matches_name_metadata_and_body(client):
    ws_res = await client.post("/workspaces", json={"name": "Search WS"})
    assert ws_res.status_code == 201
    workspace_id = ws_res.json()["id"]

    jr_res = await client.post(
        f"/workspaces/{workspace_id}/journals",
        json={"name": "Search Journal"},
    )
    assert jr_res.status_code == 201
    journal_id = jr_res.json()["id"]

    entries = [
        {
            "type": "daily",
            "name": "Morning Run",
            "body": {"ops": [{"insert": "Went for a long run today\n"}]},
            "custom_metadata": [{"key": "mood", "value": "energized"}],
        },
        {
            "type": "idea",
            "name": "App Sketch",
            "body": {"ops": [{"insert": "Drafted API search improvements\n"}]},
            "custom_metadata": [{"key": "topic", "value": "backend"}],
        },
    ]

    for payload in entries:
        create_res = await client.post(f"/journals/{journal_id}/entries", json=payload)
        assert create_res.status_code == 201

    # Name search
    by_name = await client.get("/entries/search", params={"q": "Morning"})
    assert by_name.status_code == 200
    assert any(item["name"] == "Morning Run" for item in by_name.json())

    # Metadata key search
    by_metadata_key = await client.get("/entries/search", params={"q": "topic"})
    assert by_metadata_key.status_code == 200
    assert any(item["name"] == "App Sketch" for item in by_metadata_key.json())

    # Body content search
    by_body = await client.get("/entries/search", params={"q": "improvements"})
    assert by_body.status_code == 200
    assert any(item["name"] == "App Sketch" for item in by_body.json())


@pytest.mark.asyncio
async def test_search_entries_supports_filter_only_and_pagination(client):
    ws_res = await client.post("/workspaces", json={"name": "Filter WS"})
    assert ws_res.status_code == 201
    workspace_id = ws_res.json()["id"]

    jr_res = await client.post(
        f"/workspaces/{workspace_id}/journals",
        json={"name": "Filter Journal"},
    )
    assert jr_res.status_code == 201
    journal_id = jr_res.json()["id"]

    for i in range(3):
        create_res = await client.post(
            f"/journals/{journal_id}/entries",
            json={
                "type": "daily",
                "name": f"Entry {i}",
                "body": {"ops": [{"insert": f"Payload {i}\n"}]},
            },
        )
        assert create_res.status_code == 201

    page_1 = await client.get(
        "/entries/search",
        params={
            "journal_id": journal_id,
            "entry_type": "daily",
            "limit": 2,
            "offset": 0,
        },
    )
    assert page_1.status_code == 200
    assert len(page_1.json()) == 2

    page_2 = await client.get(
        "/entries/search",
        params={
            "journal_id": journal_id,
            "entry_type": "daily",
            "limit": 2,
            "offset": 2,
        },
    )
    assert page_2.status_code == 200
    assert len(page_2.json()) == 1


@pytest.mark.asyncio
async def test_search_entries_rejects_invalid_date_range(client):
    res = await client.get(
        "/entries/search",
        params={
            "q": "daily",
            "from": "2025-01-10T00:00:00Z",
            "to": "2025-01-01T00:00:00Z",
        },
    )
    assert res.status_code == 400
    assert "invalid date range" in res.json()["detail"].lower()


@pytest.mark.asyncio
async def test_search_entries_denies_foreign_journal_access(client):
    ws_res = await client.post("/workspaces", json={"name": "Owned WS"})
    assert ws_res.status_code == 201
    workspace_id = ws_res.json()["id"]

    jr_res = await client.post(
        f"/workspaces/{workspace_id}/journals",
        json={"name": "Owned Journal"},
    )
    assert jr_res.status_code == 201

    journal_id = str(ObjectId())
    res = await client.get(
        "/entries/search",
        params={"q": "anything", "journal_id": journal_id},
    )
    assert res.status_code == 403
    assert "access denied" in res.json()["detail"].lower()


@pytest.mark.asyncio
async def test_search_entries_combines_query_and_filters(client):
    ws_res = await client.post("/workspaces", json={"name": "Combined Search WS"})
    assert ws_res.status_code == 201
    workspace_id = ws_res.json()["id"]

    jr_res = await client.post(
        f"/workspaces/{workspace_id}/journals",
        json={"name": "Combined Search Journal"},
    )
    assert jr_res.status_code == 201
    journal_id = jr_res.json()["id"]

    await client.post(
        f"/journals/{journal_id}/entries",
        json={
            "type": "daily",
            "name": "Focus Session",
            "body": {"ops": [{"insert": "Alpha project deep work\n"}]},
            "date_created": "2025-01-05T10:00:00Z",
        },
    )
    await client.post(
        f"/journals/{journal_id}/entries",
        json={
            "type": "daily",
            "name": "Focus Session",
            "body": {"ops": [{"insert": "Alpha notes outside date window\n"}]},
            "date_created": "2025-02-05T10:00:00Z",
        },
    )
    await client.post(
        f"/journals/{journal_id}/entries",
        json={
            "type": "idea",
            "name": "Focus Session",
            "body": {"ops": [{"insert": "Alpha but wrong type\n"}]},
            "date_created": "2025-01-06T10:00:00Z",
        },
    )
    await client.post(
        f"/journals/{journal_id}/entries",
        json={
            "type": "daily",
            "name": "Other Name",
            "body": {"ops": [{"insert": "Alpha but wrong name\n"}]},
            "date_created": "2025-01-07T10:00:00Z",
        },
    )

    res = await client.get(
        "/entries/search",
        params={
            "q": "alpha",
            "journal_id": journal_id,
            "entry_type": "daily",
            "name": "Focus",
            "from": "2025-01-01T00:00:00Z",
            "to": "2025-01-31T23:59:59Z",
        },
    )
    assert res.status_code == 200
    results = res.json()
    assert len(results) == 1
    assert results[0]["name"] == "Focus Session"
    assert results[0]["type"] == "daily"
