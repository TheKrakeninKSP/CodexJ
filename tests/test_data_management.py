"""Tests for data_management module"""

import os
from typing import Any
from unittest.mock import patch

import pytest
import pytest_asyncio
from backend.constants import DUMPS_PATH
from backend.database.querying import (
    get_entry_by_id,
    get_journal_by_id,
    get_media_by_resource_path,
    get_user_by_username,
    get_workspace_by_id,
    get_workspaces_by_user_id,
)
from backend.models.entry import EntryCreate, EntryUpdate
from backend.routes.media import ALLOWED_MIME
from backend.utils.data_management import recursive_delete_workspace
from backend.utils.music_media import wait_for_music_lookup_tasks
from tests.conftest import FIXTURE_HASHKEY, FIXTURE_USERNAME, TEST_DB_NAME

# Export Tests


@pytest.fixture(autouse=True, scope="module")
def setup_data_management_test_environment():
    yield
    dumps_dir = DUMPS_PATH
    user_dir = os.path.join(dumps_dir, FIXTURE_USERNAME)
    if os.path.exists(user_dir):
        for filename in os.listdir(user_dir):
            file_path = os.path.join(user_dir, filename)
            if os.path.isfile(file_path):
                os.remove(file_path)
        os.rmdir(user_dir)


@pytest_asyncio.fixture(autouse=True, scope="function")
async def cleanup_workspaces():
    yield
    user = get_user_by_username(FIXTURE_USERNAME)
    if not user:
        return
    workspaces = get_workspaces_by_user_id(user.id)
    for ws in workspaces:
        await recursive_delete_workspace(ws.id)


@pytest.mark.asyncio
async def test_export_empty_user(client, enable_privileged_mode):
    """Test export with no data returns success with zero counts."""
    response = await client.post("/data-management/export")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "completed"
    assert "statistics" in data
    assert data["statistics"]["workspaces_exported"] == 0
    assert data["statistics"]["journals_exported"] == 0
    assert data["statistics"]["entries_exported"] == 0
    assert data["statistics"]["tags_exported"] == 0
    assert data["statistics"]["media_exported"] == 0
    assert "filename" in data


@pytest.mark.asyncio
async def test_export_requires_privileged_mode(client):
    response = await client.post("/data-management/export")
    assert response.status_code == 403
    assert "privileged mode required" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_export_with_data(client, make_entry, enable_privileged_mode):
    """Test export after creating workspace, journal, and entry."""
    entry_id = make_entry

    # Export
    export_res = await client.post("/data-management/export")
    assert export_res.status_code == 200
    data = export_res.json()
    assert data["status"] == "completed"
    assert "statistics" in data
    assert data["statistics"]["workspaces_exported"] == 1
    assert data["statistics"]["journals_exported"] == 1
    assert data["statistics"]["entries_exported"] == 1
    assert data["statistics"]["tags_exported"] == 1
    assert data["statistics"]["media_exported"] == 0


@pytest.mark.asyncio
async def test_export_encryption_key_validation(client, enable_privileged_mode):
    """Test that export works without any key input."""
    response = await client.post("/data-management/export")
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_export_does_not_delete_user_data(client, enable_privileged_mode):
    """Test export endpoint creates dump without removing account access."""
    response = await client.post("/data-management/export")
    assert response.status_code == 200

    # Request still succeeds with same token, confirming no account deletion happened.
    workspaces_res = await client.get("/workspaces")
    assert workspaces_res.status_code == 200


@pytest.mark.asyncio
async def test_export_trims_orphaned_media(client, make_entry, enable_privileged_mode):
    entry_id = make_entry
    upload_res = await client.post(
        "/media/upload",
        data={"entry_id": entry_id},
        files={
            "file": ("export_orphan.png", b"X" * 256, "image/png"),
        },
    )
    assert upload_res.status_code == 201
    orphan_path = upload_res.json()["resource_path"]

    orphan_before = get_media_by_resource_path(orphan_path)
    assert orphan_before is not None

    export_res = await client.post("/data-management/export")
    assert export_res.status_code == 200

    orphan_after = get_media_by_resource_path(orphan_path)
    assert orphan_after is None


# Import Encrypted Tests
@pytest.mark.asyncio
async def test_import_invalid_key(client, make_workspace, enable_privileged_mode):
    """Test import with wrong hashkey fails to decrypt."""
    # First create and export some data
    workspace_id = make_workspace
    export_res = await client.post("/data-management/export")
    assert export_res.status_code == 200
    filename = export_res.json()["filename"]

    # Download the file
    download_res = await client.get(f"/data-management/export/download/{filename}")
    assert download_res.status_code == 200

    # Try to import with wrong hashkey
    import_res = await client.post(
        "/data-management/import/encrypted",
        data={
            "hashkey": "wrong_hashkey_that_will_not_work_at_all",
            "conflict_resolution": "skip",
        },
        files={"file": ("dump.bin", download_res.content, "application/octet-stream")},
    )
    assert import_res.status_code == 400
    assert "decrypt" in import_res.json()["detail"].lower()


@pytest.mark.asyncio
async def test_import_encrypted_roundtrip(
    client, enable_privileged_mode, make_workspace, make_journal, make_entry
):
    """Test full export/import cycle preserves data."""
    # Create test data with unique name to identify
    workspace_id = make_workspace
    journal_id = make_journal
    entry_id = make_entry

    export_res = await client.post("/data-management/export")
    filename = export_res.json()["filename"]
    download_res = await client.get(f"/data-management/export/download/{filename}")

    await client.delete(f"/workspaces/{workspace_id}")

    # Import
    import_res = await client.post(
        "/data-management/import/encrypted",
        data={
            "hashkey": FIXTURE_HASHKEY,
            "conflict_resolution": "create_new",
        },
        files={"file": ("dump.bin", download_res.content, "application/octet-stream")},
    )
    assert import_res.status_code == 200
    data = import_res.json()

    assert data["workspaces_imported"] == 1
    assert data["journals_imported"] == 1
    assert data["entries_imported"] == 1


@pytest.mark.asyncio
async def test_import_encrypted_preserves_entry_custom_metadata(
    client, enable_privileged_mode, make_workspace, make_journal, make_entry
):
    workspace_id = make_workspace
    entry_id = make_entry
    metadata = [{"key": "mood", "value": "calm"}, {"key": "place", "value": "home"}]

    update_res = await client.patch(
        f"/entries/{entry_id}", json={"custom_metadata": metadata}
    )
    assert update_res.status_code == 200

    export_res = await client.post("/data-management/export")
    assert export_res.status_code == 200
    filename = export_res.json()["filename"]
    download_res = await client.get(f"/data-management/export/download/{filename}")
    assert download_res.status_code == 200

    delete_res = await client.delete(f"/workspaces/{workspace_id}")
    assert delete_res.status_code == 204

    import_res = await client.post(
        "/data-management/import/encrypted",
        data={
            "hashkey": FIXTURE_HASHKEY,
            "conflict_resolution": "create_new",
        },
        files={"file": ("dump.bin", download_res.content, "application/octet-stream")},
    )
    assert import_res.status_code == 200
    assert import_res.json()["entries_imported"] == 1

    search_res = await client.post("/entries/search", json={"name": "Test Entry"})
    assert search_res.status_code == 200
    results = search_res.json()
    assert len(results) == 1
    assert results[0]["custom_metadata"] == metadata


@pytest.mark.asyncio
async def test_import_encrypted_remaps_media_urls_in_entry_body(
    client, enable_privileged_mode, make_workspace, make_journal, make_entry
):
    workspace_id = make_workspace
    entry_id = make_entry

    upload_res = await client.post(
        "/media/upload",
        data={"entry_id": entry_id},
        files={"file": ("pic.png", b"\x89PNG" + b"X" * 64, "image/png")},
    )
    assert upload_res.status_code == 201
    old_url = upload_res.json()["resource_path"]

    update_res = await client.patch(
        f"/entries/{entry_id}",
        json={"body": {"ops": [{"insert": {"image": old_url}}, {"insert": "\n"}]}},
    )
    assert update_res.status_code == 200
    original_updated_at = update_res.json()["updated_at"]

    export_res = await client.post("/data-management/export")
    assert export_res.status_code == 200
    filename = export_res.json()["filename"]
    download_res = await client.get(f"/data-management/export/download/{filename}")
    assert download_res.status_code == 200

    delete_res = await client.delete(f"/workspaces/{workspace_id}")
    assert delete_res.status_code == 204

    import_res = await client.post(
        "/data-management/import/encrypted",
        data={
            "hashkey": FIXTURE_HASHKEY,
            "conflict_resolution": "create_new",
        },
        files={"file": ("dump.bin", download_res.content, "application/octet-stream")},
    )
    assert import_res.status_code == 200
    assert import_res.json()["entries_imported"] == 1
    assert import_res.json()["errors"] == []

    search_res = await client.post("/entries/search", json={"name": "Test Entry"})
    assert search_res.status_code == 200
    results = search_res.json()
    assert len(results) == 1
    imported = results[0]

    new_url = imported["body"]["ops"][0]["insert"]["image"]
    assert new_url != old_url
    assert imported["media_refs"] == [new_url]
    assert get_media_by_resource_path(new_url) is not None
    # the remap rewrite must not bump the imported timestamp
    assert imported["updated_at"] == original_updated_at


@pytest.mark.asyncio
async def test_export_import_preserves_binned_entries(
    client, make_entry, enable_privileged_mode
):
    entry_id = make_entry

    delete_res = await client.delete(f"/entries/{entry_id}")
    assert delete_res.status_code == 204

    export_res = await client.post("/data-management/export")
    assert export_res.status_code == 200
    filename = export_res.json()["filename"]

    download_res = await client.get(f"/data-management/export/download/{filename}")
    assert download_res.status_code == 200
    purge_res = await client.delete(f"/entries/{entry_id}/purge")
    assert purge_res.status_code == 204

    import_res = await client.post(
        "/data-management/import/encrypted",
        data={
            "hashkey": FIXTURE_HASHKEY,
            "conflict_resolution": "create_new",
        },
        files={"file": ("dump.bin", download_res.content, "application/octet-stream")},
    )
    assert import_res.status_code == 200
    assert import_res.json()["entries_imported"] == 1

    bin_res = await client.get("/entries/bin")
    assert bin_res.status_code == 200
    assert len(bin_res.json()) == 1
    assert bin_res.json()[0]["is_deleted"] is True


@pytest.mark.asyncio
async def test_import_encrypted_all_allowed_mime_updates_media_refs(
    client, make_journal, make_entry, enable_privileged_mode
):
    """Ensure all allowed MIME uploads survive import and media refs point to new URLs."""
    entry_id = make_entry
    entry = get_entry_by_id(entry_id)
    if not entry:
        pytest.fail("Entry not found after creation")
    entry_name = entry.name

    ext_by_mime = {
        "image/jpeg": ".jpg",
        "image/png": ".png",
        "image/gif": ".gif",
        "image/webp": ".webp",
        "video/mp4": ".mp4",
        "video/webm": ".webm",
        "video/ogg": ".ogg",
        "audio/mpeg": ".mp3",
        "audio/aac": ".aac",
        "audio/flac": ".flac",
        "audio/wav": ".wav",
        "audio/mp4": ".m4a",
        "audio/x-m4a": ".m4a",
        "audio/alac": ".alac",
        "audio/opus": ".opus",
        "audio/ogg": ".ogg",
        "application/pdf": ".pdf",
    }

    old_media_urls = []
    entry_ops: list[dict[str, Any]] = [{"insert": "MIME roundtrip body\n"}]

    for i, mime in enumerate(sorted(ALLOWED_MIME)):
        filename = f"mime_{i}{ext_by_mime[mime]}"
        file_content = f"payload-{mime}".encode("utf-8")
        upload_res = await client.post(
            "/media/upload",
            data={"entry_id": entry_id},
            files={"file": (filename, file_content, mime)},
        )
        assert upload_res.status_code == 201
        media_url = upload_res.json()["resource_path"]
        old_media_urls.append(media_url)

        if mime.startswith("image"):
            embed_key = "image"
        elif mime.startswith("video"):
            embed_key = "video"
        elif mime == "application/pdf":
            embed_key = "pdf"
        else:
            embed_key = "audio"

        entry_ops.append({"insert": {embed_key: media_url}})
        entry_ops.append({"insert": "\n"})

    entry_payload = EntryUpdate(
        tags=["mime_roundtrip"],
        body={"ops": entry_ops},
        name=entry_name,
    )
    entry_res = await client.patch(
        f"/entries/{entry_id}",
        content=entry_payload.model_dump_json(),
        headers={"Content-Type": "application/json"},
    )
    assert entry_res.status_code == 200

    export_res = await client.post("/data-management/export")
    assert export_res.status_code == 200
    filename = export_res.json()["filename"]

    download_res = await client.get(f"/data-management/export/download/{filename}")
    assert download_res.status_code == 200

    # Remove the original workspace tree so we can verify only imported refs.
    entry = get_entry_by_id(entry_res.json()["id"])
    if not entry:
        pytest.fail("Entry not found after creation")
    entry_name = entry.name
    journal = get_journal_by_id(entry.journal_id)
    if not journal:
        pytest.fail("Journal not found after entry creation")
    journal_name = journal.name
    workspace_id = journal.workspace_id
    workspace = get_workspace_by_id(workspace_id)
    if not workspace:
        pytest.fail("Workspace not found after journal creation")
    ws_name = workspace.name
    await recursive_delete_workspace(workspace_id)

    import_res = await client.post(
        "/data-management/import/encrypted",
        data={
            "hashkey": FIXTURE_HASHKEY,
            "conflict_resolution": "create_new",
        },
        files={"file": ("dump.bin", download_res.content, "application/octet-stream")},
    )
    assert import_res.status_code == 200

    workspaces_res = await client.get("/workspaces")
    assert workspaces_res.status_code == 200
    imported_ws = next(
        (ws for ws in workspaces_res.json() if ws["name"] == ws_name),
        None,
    )
    assert imported_ws is not None

    journals_res = await client.get(f"/workspaces/{imported_ws['id']}/journals")
    assert journals_res.status_code == 200
    imported_journal = next(
        (jr for jr in journals_res.json() if jr["name"] == journal_name),
        None,
    )
    assert imported_journal is not None

    entries_res = await client.get(f"/journals/{imported_journal['id']}/entries")
    assert entries_res.status_code == 200
    imported_entry = next(
        (en for en in entries_res.json() if en["name"] == entry_name),
        None,
    )
    assert imported_entry is not None
    entry_res = await client.get(f"/entries/{imported_entry['id']}")
    assert entry_res.status_code == 200
    imported_entry = entry_res.json()

    body_ops = imported_entry["body"]["ops"]
    body_urls = []
    for op in body_ops:
        insert = op.get("insert")
        if isinstance(insert, dict):
            for key in ("image", "video", "audio", "pdf"):
                if key in insert:
                    body_urls.append(insert[key])

    assert len(body_urls) == len(ALLOWED_MIME)
    assert len(imported_entry["media_refs"]) == len(ALLOWED_MIME)

    old_url_set = set(old_media_urls)
    for url in body_urls:
        assert url not in old_url_set
    for ref in imported_entry["media_refs"]:
        assert ref not in old_url_set

    assert set(imported_entry["media_refs"]) == set(body_urls)


@pytest.mark.asyncio
async def test_import_conflict_skip(client, make_workspace, enable_privileged_mode):
    """Test that skip conflict resolution works."""
    # Create workspace
    workspace_id = make_workspace

    # Export
    export_res = await client.post("/data-management/export")
    assert export_res.status_code == 200
    filename = export_res.json()["filename"]
    download_res = await client.get(f"/data-management/export/download/{filename}")

    # Import again (workspace already exists)
    import_res = await client.post(
        "/data-management/import/encrypted",
        data={
            "hashkey": FIXTURE_HASHKEY,
            "conflict_resolution": "skip",
        },
        files={"file": ("dump.bin", download_res.content, "application/octet-stream")},
    )
    assert import_res.status_code == 200
    data = import_res.json()
    assert data["skipped"] == 1


@pytest.mark.asyncio
async def test_export_import_remaps_webpage_embed_urls(
    client, enable_privileged_mode, make_workspace, make_journal, make_entry
):
    """Webpage embeds (src field) must be remapped to the new resource URL on import."""
    ws_id = make_workspace
    ws_name = "Test Workspace"
    entry_id = make_entry

    html = (
        b'<!DOCTYPE html><html lang="en"><!--\n'
        b" Page saved with SingleFile\n"
        b" url: https://example.com/article\n"
        b" saved date: Mon Jan 01 2024 12:00:00 GMT+0000\n"
        b"--><head><title>Test Article</title></head><body>Hello</body></html>"
    )
    upload_res = await client.post(
        "/media/upload-webpage-archive",
        data={"entry_id": entry_id},
        files={"file": ("article.html", html, "text/html")},
    )
    assert upload_res.status_code == 201
    old_url = upload_res.json()["resource_path"]

    webpage_embed = {
        "src": old_url,
        "source_url": "https://example.com/article",
        "title": "Test Article",
    }
    entry_res = await client.patch(
        f"/entries/{entry_id}",
        json={
            "body": {
                "ops": [
                    {"insert": {"webpage": webpage_embed}},
                    {"insert": "\n"},
                ]
            },
        },
    )
    assert entry_res.status_code == 200
    assert old_url in entry_res.json()["media_refs"]

    export_res = await client.post("/data-management/export")
    assert export_res.status_code == 200
    filename = export_res.json()["filename"]

    download_res = await client.get(f"/data-management/export/download/{filename}")
    assert download_res.status_code == 200

    await client.delete(f"/workspaces/{ws_id}")

    import_res = await client.post(
        "/data-management/import/encrypted",
        data={"hashkey": FIXTURE_HASHKEY, "conflict_resolution": "create_new"},
        files={"file": ("dump.bin", download_res.content, "application/octet-stream")},
    )
    assert import_res.status_code == 200

    workspaces_res = await client.get("/workspaces")
    imported_ws = next(
        (ws for ws in workspaces_res.json() if ws["name"] == ws_name), None
    )
    assert imported_ws is not None

    journals_res = await client.get(f"/workspaces/{imported_ws['id']}/journals")
    imported_jr = next(
        (jr for jr in journals_res.json() if jr["name"] == "Test Journal"), None
    )
    assert imported_jr is not None

    entries_res = await client.get(f"/journals/{imported_jr['id']}/entries")
    imported_entry = next(
        (e for e in entries_res.json() if e["name"] == "Test Entry"), None
    )
    assert imported_entry is not None
    imported_entry = (await client.get(f"/entries/{imported_entry['id']}")).json()

    # The embedded src must point to the new URL, not the original
    ops = imported_entry["body"]["ops"]
    webpage_ops = [
        op
        for op in ops
        if isinstance(op.get("insert"), dict) and "webpage" in op["insert"]
    ]
    assert len(webpage_ops) == 1
    new_src = webpage_ops[0]["insert"]["webpage"]["src"]
    assert new_src != old_url
    assert new_src.startswith("/media/")

    # media_refs must also point to the new URL
    assert new_src in imported_entry["media_refs"]
    assert old_url not in imported_entry["media_refs"]

    # The imported file must retain the .html extension so browsers render it correctly
    assert new_src.endswith(
        ".html"
    ), f"Imported webpage resource lost .html extension: {new_src}"

    # Verify the imported media DB record has all required fields
    imported_media = get_media_by_resource_path(new_src)
    assert imported_media is not None
    media_status_res = await client.get(f"/media/{imported_media.id}")
    assert media_status_res.status_code == 200
    media_doc = media_status_res.json()
    assert media_doc["media_type"] == "webpage"
    assert media_doc["status"] == "completed"
    assert media_doc["resource_path"] == new_src
    assert media_doc["resource_path"].endswith(".html")
    assert "source_url" in media_doc["custom_metadata"]
    assert media_doc["custom_metadata"]["source_url"] == "https://example.com/article"


@pytest.mark.asyncio
async def test_export_import_remaps_opus_media_refs(
    client, enable_privileged_mode, make_workspace, make_journal, make_entry
):
    """Opus audio embeds must survive export/import with remapped URLs."""
    ws_id = make_workspace
    ws_name = "Test Workspace"
    entry_id = make_entry

    opus_content = b"\x00" * 512
    upload_res = await client.post(
        "/media/upload",
        data={"entry_id": entry_id},
        files={"file": ("voice.opus", opus_content, "audio/opus")},
    )
    assert upload_res.status_code == 201
    old_url = upload_res.json()["resource_path"]

    entry_res = await client.patch(
        f"/entries/{entry_id}",
        json={
            "body": {
                "ops": [
                    {"insert": {"audio": old_url}},
                    {"insert": "\n"},
                ]
            },
        },
    )
    assert entry_res.status_code == 200
    assert old_url in entry_res.json()["media_refs"]

    export_res = await client.post("/data-management/export")
    assert export_res.status_code == 200
    filename = export_res.json()["filename"]

    download_res = await client.get(f"/data-management/export/download/{filename}")
    assert download_res.status_code == 200

    await client.delete(f"/workspaces/{ws_id}")

    import_res = await client.post(
        "/data-management/import/encrypted",
        data={"hashkey": FIXTURE_HASHKEY, "conflict_resolution": "create_new"},
        files={"file": ("dump.bin", download_res.content, "application/octet-stream")},
    )
    assert import_res.status_code == 200

    workspaces_res = await client.get("/workspaces")
    imported_ws = next(
        (ws for ws in workspaces_res.json() if ws["name"] == ws_name), None
    )
    assert imported_ws is not None

    journals_res = await client.get(f"/workspaces/{imported_ws['id']}/journals")
    imported_jr = journals_res.json()[0]

    entries_res = await client.get(f"/journals/{imported_jr['id']}/entries")
    imported_entry = entries_res.json()[0]
    imported_entry = (await client.get(f"/entries/{imported_entry['id']}")).json()
    ops = imported_entry["body"]["ops"]
    audio_ops = [
        op
        for op in ops
        if isinstance(op.get("insert"), dict) and "audio" in op["insert"]
    ]
    assert len(audio_ops) == 1
    new_url = audio_ops[0]["insert"]["audio"]
    assert new_url != old_url
    assert new_url.startswith("/media/")
    assert new_url in imported_entry["media_refs"]
    assert old_url not in imported_entry["media_refs"]


@pytest.mark.asyncio
async def test_export_import_remaps_entry_links(
    client, enable_privileged_mode, make_workspace, make_journal, make_entry
):
    """Links to other entries must point at the imported copies, not the old ids."""
    ws_id = make_workspace
    source_id = make_entry
    target_res = await client.post(
        f"/journals/{make_journal}/entries",
        json={"tags": [], "name": "Link Target", "body": {"ops": [{"insert": "x\n"}]}},
    )
    assert target_res.status_code == 201
    target_id = target_res.json()["id"]

    body = {
        "ops": [
            {"insert": "see "},
            {"insert": "target", "attributes": {"link": f"/entries/{target_id}"}},
            {"insert": " and "},
            {"insert": "web", "attributes": {"link": "https://example.com/entries/1"}},
            {"insert": "\n"},
        ]
    }
    assert (
        await client.patch(f"/entries/{source_id}", json={"body": body})
    ).status_code == 200

    export_res = await client.post("/data-management/export")
    assert export_res.status_code == 200
    download_res = await client.get(
        f"/data-management/export/download/{export_res.json()['filename']}"
    )
    assert (await client.delete(f"/workspaces/{ws_id}")).status_code == 204

    import_res = await client.post(
        "/data-management/import/encrypted",
        data={"hashkey": FIXTURE_HASHKEY, "conflict_resolution": "create_new"},
        files={"file": ("dump.bin", download_res.content, "application/octet-stream")},
    )
    assert import_res.status_code == 200
    assert import_res.json()["entries_imported"] == 2

    async def find(name):
        found = (await client.post("/entries/search", json={"name": name})).json()
        assert len(found) == 1
        return (await client.get(f"/entries/{found[0]['id']}")).json()

    new_source = await find("Test Entry")
    new_target = await find("Link Target")
    links = [
        op["attributes"]["link"]
        for op in new_source["body"]["ops"]
        if "attributes" in op
    ]
    assert new_target["id"] != target_id
    assert links == [f"/entries/{new_target['id']}", "https://example.com/entries/1"]


@pytest.mark.asyncio
async def test_export_import_preserves_music_identification(
    client, enable_privileged_mode, make_workspace, make_entry
):
    """Music metadata survives import and the embed's media_id points at the new media."""
    ws_id = make_workspace
    entry_id = make_entry
    music_info = {
        "title": "Enchanted",
        "artist": "Taylor Swift",
        "album": "Speak Now",
        "year": "2010",
        "mbid": "3504d301-ea35-43da-a968-2f66922e109f",
        "cover_art_base64": "dGVzdA==",
    }

    with patch("backend.utils.music_lookup.identify_song", return_value=music_info):
        upload_res = await client.post(
            "/media/upload",
            data={"entry_id": entry_id},
            files={"file": ("song.mp3", b"\x00" * 256, "audio/mpeg")},
        )
        assert upload_res.status_code == 201
        await wait_for_music_lookup_tasks()
    old_media = upload_res.json()

    body = {
        "ops": [
            {
                "insert": {
                    "audio": {
                        "src": old_media["resource_path"],
                        "original_filename": "song.mp3",
                        "media_id": old_media["id"],
                    }
                }
            },
            {"insert": "\n"},
        ]
    }
    assert (
        await client.patch(f"/entries/{entry_id}", json={"body": body})
    ).status_code == 200

    export_res = await client.post("/data-management/export")
    assert export_res.status_code == 200
    download_res = await client.get(
        f"/data-management/export/download/{export_res.json()['filename']}"
    )
    assert download_res.status_code == 200
    assert (await client.delete(f"/workspaces/{ws_id}")).status_code == 204

    import_res = await client.post(
        "/data-management/import/encrypted",
        data={"hashkey": FIXTURE_HASHKEY, "conflict_resolution": "create_new"},
        files={"file": ("dump.bin", download_res.content, "application/octet-stream")},
    )
    assert import_res.status_code == 200
    assert import_res.json()["errors"] == []

    search_res = await client.post("/entries/search", json={"name": "Test Entry"})
    imported_id = search_res.json()[0]["id"]
    imported_entry = (await client.get(f"/entries/{imported_id}")).json()
    audio = imported_entry["body"]["ops"][0]["insert"]["audio"]

    # The embed must reference the imported media record, not the original id.
    assert audio["media_id"] != old_media["id"]
    media_res = await client.get(f"/media/{audio['media_id']}")
    assert media_res.status_code == 200
    media = media_res.json()
    assert media["resource_path"] == audio["src"]
    assert media["custom_metadata"]["music_lookup_status"] == "completed"
    assert media["custom_metadata"]["music_info"] == music_info


def test_encryption_roundtrip():
    """Test encryption/decryption works correctly."""
    from backend.utils.data_management import decrypt_data, encrypt_data

    original = '{"test": "data", "unicode": "日本語"}'
    key = "my_test_encryption_key"

    encrypted = encrypt_data(original, key)
    assert encrypted != original.encode()

    decrypted = decrypt_data(encrypted, key)
    assert decrypted == original


def test_encryption_wrong_key():
    """Test decryption with wrong key returns None."""
    from backend.utils.data_management import decrypt_data, encrypt_data

    original = "secret data"
    encrypted = encrypt_data(original, "correct_key")

    result = decrypt_data(encrypted, "wrong_key")
    assert result is None


def test_validate_dump_structure():
    """Test dump structure validation."""
    from backend.constants import APP_VERSION
    from backend.utils.data_management import validate_dump_structure

    current_major = int(APP_VERSION.split(".")[0])

    # Valid dump (same major version as the app)
    valid_dump = {
        "version": f"{current_major}.0",
        "user": {"username": "test-user"},
        "workspaces": [],
        "journals": [],
        "entries": [],
    }
    valid, msg = validate_dump_structure(valid_dump)
    assert valid

    # Missing key
    invalid_dump = {
        "version": f"{current_major}.0",
        "user": {"username": "test-user"},
        "workspaces": [],
    }
    valid, msg = validate_dump_structure(invalid_dump)
    assert not valid
    assert "Missing" in msg

    # Dumps from other major versions are rejected (e.g. 1.x used integer ids)
    for other_major in (current_major - 1, current_major + 1):
        other_version_dump = {
            "version": f"{other_major}.0",
            "user": {"username": "test-user"},
            "workspaces": [],
            "journals": [],
            "entries": [],
        }
        valid, msg = validate_dump_structure(other_version_dump)
        assert not valid
        assert "version" in msg.lower()


def test_update_media_refs_in_body_handles_object_embed_values():
    """Media URL remapping should support object embeds (e.g. audio blot payloads)."""
    from backend.utils.data_management import update_media_refs_in_body

    old_audio = "http://localhost:8128/media/old-user/audio1.m4a"
    old_image = "http://localhost:8128/media/old-user/image1.png"
    new_audio = "http://localhost:8128/media/new-user/audio2.m4a"
    new_image = "http://localhost:8128/media/new-user/image2.png"

    body = {
        "ops": [
            {
                "insert": {
                    "audio": {
                        "src": old_audio,
                        "original_filename": "voice-note.m4a",
                    }
                }
            },
            {"insert": {"image": old_image}},
            {"insert": "plain text\n"},
        ]
    }
    url_map = {
        old_audio: new_audio,
        old_image: new_image,
    }

    updated = update_media_refs_in_body(body, url_map)
    assert updated["ops"][0]["insert"]["audio"]["src"] == new_audio
    assert updated["ops"][0]["insert"]["audio"]["original_filename"] == "voice-note.m4a"
    assert updated["ops"][1]["insert"]["image"] == new_image


def test_update_media_refs_in_body_remaps_media_ids():
    from backend.utils.data_management import update_media_refs_in_body

    body = {
        "ops": [
            {"insert": {"audio": {"src": "old.m4a", "media_id": "old-1"}}},
            {"insert": {"webpage": {"src": "old.html", "media_id": "old-2"}}},
            {"insert": {"audio": {"src": "keep.m4a", "media_id": "unmapped"}}},
        ]
    }
    updated = update_media_refs_in_body(
        body,
        {"old.m4a": "new.m4a", "old.html": "new.html"},
        {"old-1": "new-1", "old-2": "new-2"},
    )
    ops = updated["ops"]
    assert ops[0]["insert"]["audio"] == {"src": "new.m4a", "media_id": "new-1"}
    assert ops[1]["insert"]["webpage"] == {"src": "new.html", "media_id": "new-2"}
    assert ops[2]["insert"]["audio"] == {"src": "keep.m4a", "media_id": "unmapped"}
