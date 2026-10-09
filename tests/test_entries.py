import pytest

from backend.models.entry import (
    EntryCreate,
    EntryMove,
    EntryMoveRequest,
    EntryRestoreRequest,
    EntryUpdateRequest,
)


# test entry creation
@pytest.mark.asyncio
async def test_create_entry(client, make_workspace, make_journal):
    workspace_id = make_workspace
    journal_id = make_journal

    payload = EntryCreate(
        tags=["test_type"],
        body={"ops": [{"insert": "Hello, world!\n"}]},
        name="test entry",
        timezone="Asia/Kolkata",
    )
    response = await client.post(
        f"/journals/{journal_id}/entries", json=payload.model_dump()
    )
    assert response.status_code == 201
    data = response.json()
    assert data["tags"] == payload.tags
    assert data["body"] == payload.body
    assert data["name"] == payload.name
    assert data["timezone"] == payload.timezone
    assert data["is_deleted"] is False


# test entry listing by creating 3 entries and checking existence of all 3
@pytest.mark.asyncio
async def test_list_entries(client, make_workspace, make_journal):
    workspace_id = make_workspace
    journal_id = make_journal

    entry_names = ["Entry 1", "Entry 2", "Entry 3"]
    for name in entry_names:
        payload = EntryCreate(
            tags=["test_type"],
            body={"ops": [{"insert": f"{name} content\n"}]},
            name=name,
            timezone="Asia/Kolkata",
        )
        response = await client.post(
            f"/journals/{journal_id}/entries", json=payload.model_dump()
        )
        assert response.status_code == 201

    list_response = await client.get(f"/journals/{journal_id}/entries")
    assert list_response.status_code == 200
    data = list_response.json()
    returned_names = [e["name"] for e in data]
    for name in entry_names:
        assert name in returned_names


# test entry retrieval
@pytest.mark.asyncio
async def test_get_entry(client, make_workspace, make_journal):
    workspace_id = make_workspace
    journal_id = make_journal

    payload = EntryCreate(
        tags=["test_type"],
        body={"ops": [{"insert": "Hello, world!\n"}]},
        name="test entry",
        timezone="Asia/Kolkata",
    )
    create_response = await client.post(
        f"/journals/{journal_id}/entries", json=payload.model_dump()
    )
    assert create_response.status_code == 201
    entry_id = create_response.json()["id"]

    get_response = await client.get(f"/entries/{entry_id}")
    assert get_response.status_code == 200
    data = get_response.json()
    assert data["tags"] == payload.tags
    assert data["body"] == payload.body
    assert data["name"] == payload.name
    assert data["timezone"] == payload.timezone


# test entry retrieval with invalid id
@pytest.mark.asyncio
async def test_get_entry_invalid_id(
    client, make_workspace, make_journal, make_invalid_id
):
    workspace_id = make_workspace
    journal_id = make_journal
    invalid_id = make_invalid_id

    get_response = await client.get(f"/entries/{invalid_id}")
    assert get_response.status_code == 404


# test entry update
@pytest.mark.asyncio
async def test_update_entry(client, make_workspace, make_journal):
    workspace_id = make_workspace
    journal_id = make_journal

    payload = EntryCreate(
        tags=["test_type"],
        body={"ops": [{"insert": "Hello, world!\n"}]},
        name="test entry",
        timezone="Asia/Kolkata",
    )
    create_response = await client.post(
        f"/journals/{journal_id}/entries", json=payload.model_dump()
    )
    assert create_response.status_code == 201
    entry_id = create_response.json()["id"]

    update_payload = EntryUpdateRequest(
        tags=["updated_type"],
        body={"ops": [{"insert": "Updated content\n"}]},
        name="updated entry",
    )
    update_response = await client.patch(
        f"/entries/{entry_id}",
        content=update_payload.model_dump_json(),
        headers={"Content-Type": "application/json"},
    )
    assert update_response.status_code == 200
    data = update_response.json()
    assert data["tags"] == update_payload.tags
    assert data["body"] == update_payload.body
    assert data["name"] == update_payload.name
    assert data["date_created"] == create_response.json()["date_created"]

    # update timezone
    tz_payload = EntryUpdateRequest(
        timezone="America/New_York",
    )
    tz_response = await client.patch(
        f"/entries/{entry_id}",
        content=tz_payload.model_dump_json(),
        headers={"Content-Type": "application/json"},
    )
    assert tz_response.status_code == 200
    assert tz_response.json()["timezone"] == "America/New_York"

    # verify timezone persists on GET
    get_response = await client.get(f"/entries/{entry_id}")
    assert get_response.status_code == 200
    assert get_response.json()["timezone"] == "America/New_York"


# test entry deletion
@pytest.mark.asyncio
async def test_delete_entry(
    client, make_workspace, make_journal, enable_privileged_mode
):
    initial_count_res = await client.get("/entries/bin/count")
    assert initial_count_res.status_code == 200
    initial_count = initial_count_res.json()["count"]

    workspace_id = make_workspace
    journal_id = make_journal

    payload = EntryCreate(
        tags=["test_type"],
        body={"ops": [{"insert": "Hello, world!\n"}]},
        name="test entry",
    ).model_dump()

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
async def test_restore_entry(
    client, make_workspace, make_journal, enable_privileged_mode
):
    workspace_id = make_workspace
    journal_id = make_journal

    entry_res = await client.post(
        f"/journals/{journal_id}/entries",
        json=EntryCreate(
            tags=["restore_type"],
            body={"ops": [{"insert": "Restore me\n"}]},
            name="Restore Entry",
        ).model_dump(),
    )
    entry_id = entry_res.json()["id"]

    delete_res = await client.delete(f"/entries/{entry_id}")
    assert delete_res.status_code == 204

    restore_res = await client.post(
        f"/entries/{entry_id}/restore",
        json=EntryRestoreRequest(
            workspace_id=workspace_id, journal_id=journal_id
        ).model_dump(),
    )
    assert restore_res.status_code == 200
    restored = restore_res.json()
    assert restored["journal_id"] == journal_id
    assert restored["is_deleted"] is False
    assert restored["deleted_at"] is None

    bin_res = await client.get("/entries/bin")
    assert all(item["id"] != entry_id for item in bin_res.json())

    target_entries = await client.get(f"/journals/{journal_id}/entries")
    assert any(item["id"] == entry_id for item in target_entries.json())


@pytest.mark.asyncio
async def test_purge_deleted_entry(
    client, make_workspace, make_journal, enable_privileged_mode
):
    initial_count_res = await client.get("/entries/bin/count")
    assert initial_count_res.status_code == 200
    initial_count = initial_count_res.json()["count"]

    workspace_id = make_workspace
    journal_id = make_journal

    entry_res = await client.post(
        f"/journals/{journal_id}/entries",
        json=EntryCreate(
            tags=["purge_type"],
            body={"ops": [{"insert": "Purge me\n"}]},
            name="Purge Entry",
        ).model_dump(),
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
            "tags": ["search_type"],
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
async def test_delete_entry_requires_privileged_mode(
    client, make_workspace, make_journal
):
    workspace_id = make_workspace
    journal_id = make_journal

    entry_res = await client.post(
        f"/journals/{journal_id}/entries",
        json=EntryCreate(
            tags=["test_type"],
            body={"ops": [{"insert": "Restricted delete\n"}]},
            name="restricted entry",
        ).model_dump(),
    )
    assert entry_res.status_code == 201
    entry_id = entry_res.json()["id"]

    delete_res = await client.delete(f"/entries/{entry_id}")
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
            "tags": ["daily"],
            "name": "Morning Run",
            "body": {"ops": [{"insert": "Went for a long run today\n"}]},
            "custom_metadata": [{"key": "mood", "value": "energized"}],
        },
        {
            "tags": ["idea"],
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
                "tags": ["daily"],
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
            "tags": ["daily"],
            "name": "Focus Session",
            "body": {"ops": [{"insert": "Alpha project deep work\n"}]},
            "date_created": "2025-01-05T10:00:00Z",
        },
    )
    await client.post(
        f"/journals/{journal_id}/entries",
        json={
            "tags": ["daily"],
            "name": "Focus Session",
            "body": {"ops": [{"insert": "Alpha notes outside date window\n"}]},
            "date_created": "2025-02-05T10:00:00Z",
        },
    )
    await client.post(
        f"/journals/{journal_id}/entries",
        json={
            "tags": ["idea"],
            "name": "Focus Session",
            "body": {"ops": [{"insert": "Alpha but wrong type\n"}]},
            "date_created": "2025-01-06T10:00:00Z",
        },
    )
    await client.post(
        f"/journals/{journal_id}/entries",
        json={
            "tags": ["daily"],
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
    assert "daily" in results[0]["tags"]


@pytest.mark.asyncio
async def test_create_entry_with_multiple_tags(client, make_workspace, make_journal):
    workspace_id = make_workspace
    journal_id = make_journal

    res = await client.post(
        f"/journals/{journal_id}/entries",
        json=EntryCreate(
            tags=["journal", "reflection", "dream"],
            name="Multi-Tag Entry",
            body={"ops": [{"insert": "Multiple tags test\n"}]},
        ).model_dump(),
    )
    assert res.status_code == 201
    data = res.json()
    assert set(data["tags"]) == {"journal", "reflection", "dream"}


@pytest.mark.asyncio
async def test_update_entry_with_custom_date(client, make_workspace, make_journal):
    workspace_id = make_workspace
    journal_id = make_journal

    create_res = await client.post(
        f"/journals/{journal_id}/entries",
        json=EntryCreate(
            tags=["note"],
            name="Date Entry",
            body={"ops": [{"insert": "Test\n"}]},
        ).model_dump(),
    )
    assert create_res.status_code == 201
    entry_id = create_res.json()["id"]

    custom_iso = "2020-06-15T14:30:00Z"
    update_res = await client.patch(
        f"/entries/{entry_id}",
        json=EntryUpdateRequest(date_created=custom_iso).model_dump(),
    )
    assert update_res.status_code == 200
    assert update_res.json()["date_created"].startswith("2020-06-15")


@pytest.mark.asyncio
async def test_move_entry_to_another_journal(
    client, make_workspace, make_journal, make_alternate_journal, enable_privileged_mode
):
    workspace_id = make_workspace
    src_journal_id = make_journal
    dst_journal_id = make_alternate_journal

    entry_res = await client.post(
        f"/journals/{src_journal_id}/entries",
        json=EntryCreate(
            tags=["note"],
            name="Move Me",
            body={"ops": [{"insert": "Moving this entry\n"}]},
        ).model_dump(),
    )
    assert entry_res.status_code == 201
    entry_id = entry_res.json()["id"]

    move_res = await client.patch(
        f"/entries/{entry_id}/move",
        json=EntryMoveRequest(journal_id=dst_journal_id).model_dump(),
    )
    assert move_res.status_code == 200
    assert move_res.json()["journal_id"] == dst_journal_id

    # Should appear in destination journal
    dst_entries = await client.get(f"/journals/{dst_journal_id}/entries")
    assert any(e["id"] == entry_id for e in dst_entries.json())

    # Should not appear in source journal
    src_entries = await client.get(f"/journals/{src_journal_id}/entries")
    assert all(e["id"] != entry_id for e in src_entries.json())


@pytest.mark.asyncio
async def test_move_entry_requires_privileged_mode(
    client, make_workspace, make_journal, make_alternate_journal
):
    workspace_id = make_workspace
    journal_id = make_journal
    dst_journal_id = make_alternate_journal

    entry_res = await client.post(
        f"/journals/{journal_id}/entries",
        json=EntryCreate(
            tags=["note"],
            name="Restricted Move",
            body={"ops": [{"insert": "Test\n"}]},
        ).model_dump(),
    )
    assert entry_res.status_code == 201
    entry_id = entry_res.json()["id"]

    move_res = await client.patch(
        f"/entries/{entry_id}/move",
        json=EntryMoveRequest(journal_id=dst_journal_id).model_dump(),
    )
    assert move_res.status_code == 403
