import asyncio
import os
import shutil
from unittest.mock import patch

import pytest
from app.constants import DUMPS_PATH, MEDIA_PATH
from app.routes import media as media_routes
from bson import ObjectId
from tests.conftest import TEST_DB_NAME


@pytest.fixture(autouse=True, scope="module")
def setup_media_test_environment():
    yield
    # clear the entire test user media directory after all tests in this module
    media_dir = os.path.join(MEDIA_PATH, "test-user-id")
    if os.path.exists(media_dir):
        shutil.rmtree(media_dir)


async def get_media_id_by_path(db_client, resource_path: str) -> str:
    db = db_client[TEST_DB_NAME]
    doc = await db["media"].find_one({"resource_path": resource_path})
    assert doc is not None
    return str(doc["_id"])


# test media upload and retrieval
@pytest.mark.asyncio
async def test_upload_media(client):
    # 1MB binary
    media_content = b"X" * (1024 * 1024)

    files = {
        "file": ("test.png", media_content, "image/png"),
    }

    response = await client.post("/media/upload", files=files)

    assert response.status_code == 201
    res = response.json()
    assert res["media_type"] == "image"
    assert res["original_filename"] == "test.png"
    assert res["file_size"] == len(media_content)
    assert "resource_path" in res
    assert "created_at" in res
    assert "custom_metadata" in res
    assert res["status"] == "completed"


# test upload creates a media record in the database
@pytest.mark.asyncio
async def test_upload_creates_db_record(client, db_client):
    media_content = b"A" * 512
    files = {
        "file": ("test_x.png", media_content, "image/png"),
    }
    response = await client.post("/media/upload", files=files)
    assert response.status_code == 201
    res = response.json()
    media_id = await get_media_id_by_path(db_client, res["resource_path"])

    db = db_client[TEST_DB_NAME]
    doc = await db["media"].find_one({"_id": ObjectId(media_id)})
    assert doc is not None
    assert doc["original_filename"] == "test_x.png"
    assert doc["stored_filename"].endswith(".png")
    assert doc["media_type"] == "image"
    assert doc["file_size"] == 512
    assert doc["user_id"] == "test-user-id"  # from test auth fixture
    assert res["original_filename"] == "test_x.png"
    assert res["media_type"] == "image"
    assert res["file_size"] == 512
    assert "resource_path" in res
    assert "created_at" in res


@pytest.mark.asyncio
async def test_upload_webpage_archive_extracts_metadata(client, db_client):
    html = b"""<!DOCTYPE html><html lang="en"><!--
 Page saved with SingleFile
 url: https://example.com/articles/one
 saved date: Thu Apr 03 2026 10:30:00 GMT+0530 (India Standard Time)
--><head><title>Saved Example</title><link rel="canonical" href="https://example.com/articles/one"></head><body>Hello</body></html>"""

    response = await client.post(
        "/media/upload-webpage-archive",
        files={"file": ("example.html", html, "text/html")},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["media_type"] == "webpage"
    assert body["status"] == "completed"
    assert body["original_filename"] == "Saved Example"
    assert body["custom_metadata"]["source_url"] == "https://example.com/articles/one"
    assert body["custom_metadata"]["page_title"] == "Saved Example"
    assert body["custom_metadata"]["archived_at"] == "2026-04-03T05:00:00+00:00"

    media_id = await get_media_id_by_path(db_client, body["resource_path"])
    db = db_client[TEST_DB_NAME]
    doc = await db["media"].find_one({"_id": ObjectId(media_id)})
    assert doc is not None
    assert doc["stored_filename"].endswith(".html")


@pytest.mark.asyncio
async def test_upload_webpage_archive_rejects_non_html(client):
    response = await client.post(
        "/media/upload-webpage-archive",
        files={"file": ("not-html.txt", b"plain text", "text/plain")},
    )

    assert response.status_code == 415


# test that duplicate filanames produce unique stored files
@pytest.mark.asyncio
async def test_duplicate_filename_no_overwrite(client):
    media_content_1 = b"A" * 256
    media_content_2 = b"B" * 512
    files_1 = {
        "file": ("duplicate.png", media_content_1, "image/png"),
    }
    files_2 = {
        "file": ("duplicate.png", media_content_2, "image/png"),
    }
    res1 = await client.post("/media/upload", files=files_1)
    res2 = await client.post("/media/upload", files=files_2)

    assert res1.status_code == 201
    assert res2.status_code == 201

    data1 = res1.json()
    data2 = res2.json()

    assert data1["resource_path"] != data2["resource_path"]
    assert data1["original_filename"] == data2["original_filename"] == "duplicate.png"


# test deleting media
@pytest.mark.asyncio
async def test_delete_media(client, db_client):
    media_content = b"X" * 128
    files = {
        "file": ("delete_test.png", media_content, "image/png"),
    }
    upload_res = await client.post("/media/upload", files=files)
    assert upload_res.status_code == 201
    media_id = await get_media_id_by_path(db_client, upload_res.json()["resource_path"])

    delete_res = await client.delete(f"/media/{media_id}")
    assert delete_res.status_code == 204

    db = db_client[TEST_DB_NAME]
    doc = await db["media"].find_one({"_id": ObjectId(media_id)})
    assert doc is None


@pytest.mark.asyncio
async def test_trim_media_deletes_only_unreferenced(client, db_client):
    ws_res = await client.post("/workspaces", json={"name": "Trim Workspace"})
    assert ws_res.status_code == 201
    workspace_id = ws_res.json()["id"]

    jr_res = await client.post(
        f"/workspaces/{workspace_id}/journals",
        json={"name": "Trim Journal"},
    )
    assert jr_res.status_code == 201
    journal_id = jr_res.json()["id"]

    kept_entry_type_res = await client.post(
        f"/workspaces/{workspace_id}/entry-types",
        json={"name": "trim_test"},
    )
    assert kept_entry_type_res.status_code == 201

    orphan_entry_type_res = await client.post(
        f"/workspaces/{workspace_id}/entry-types",
        json={"name": "unused_trim_type"},
    )
    assert orphan_entry_type_res.status_code == 201
    orphan_entry_type_id = orphan_entry_type_res.json()["id"]

    kept_upload_res = await client.post(
        "/media/upload",
        files={"file": ("kept.png", b"K" * 128, "image/png")},
    )
    assert kept_upload_res.status_code == 201
    kept_path = kept_upload_res.json()["resource_path"]
    kept_media_id = await get_media_id_by_path(db_client, kept_path)

    orphan_upload_res = await client.post(
        "/media/upload",
        files={"file": ("orphan.png", b"O" * 128, "image/png")},
    )
    assert orphan_upload_res.status_code == 201
    orphan_path = orphan_upload_res.json()["resource_path"]
    orphan_media_id = await get_media_id_by_path(db_client, orphan_path)

    entry_payload = {
        "tags": ["trim_test"],
        "body": {
            "ops": [
                {"insert": "keep this media\n"},
                {"insert": {"image": kept_path}},
                {"insert": "\n"},
            ]
        },
        "name": "Trim Test Entry",
    }
    entry_res = await client.post(f"/journals/{journal_id}/entries", json=entry_payload)
    assert entry_res.status_code == 201

    trim_res = await client.post("/media/trim")
    assert trim_res.status_code == 200
    body = trim_res.json()
    assert body["status"] == "success"
    assert body["deleted_count"] >= 1
    assert body["deleted_entry_type_count"] >= 1

    db = db_client[TEST_DB_NAME]
    kept_doc = await db["media"].find_one({"_id": ObjectId(kept_media_id)})
    orphan_doc = await db["media"].find_one({"_id": ObjectId(orphan_media_id)})
    kept_entry_type_doc = await db["entry_types"].find_one(
        {"name": "trim_test", "workspace_id": workspace_id}
    )
    orphan_entry_type_doc = await db["entry_types"].find_one(
        {"_id": ObjectId(orphan_entry_type_id)}
    )
    assert kept_doc is not None
    assert orphan_doc is None
    assert kept_entry_type_doc is not None
    assert orphan_entry_type_doc is None


@pytest.mark.asyncio
async def test_trim_media_requires_privileged_mode(unprivileged_client):
    trim_res = await unprivileged_client.post("/media/trim")
    assert trim_res.status_code == 403
    assert "privileged mode required" in trim_res.json()["detail"].lower()


# test saving entry with media
@pytest.mark.asyncio
async def test_create_entry_with_media(client):
    ws_payload = {"name": "Test Workspace"}
    ws_res = await client.post("/workspaces", json=ws_payload)
    assert ws_res.status_code == 201
    workspace_id = ws_res.json()["id"]

    jr_payload = {"name": "Test Journal"}
    jr_res = await client.post(f"/workspaces/{workspace_id}/journals", json=jr_payload)
    assert jr_res.status_code == 201
    journal_id = jr_res.json()["id"]

    # make a binary object of 2MB size
    media_content = b"X" * (1024 * 1024 * 2)  # 2MB
    files = {
        "file": ("test_image_for_entry.png", media_content, "image/png"),
    }
    media_upload_response = await client.post("/media/upload", files=files)
    assert media_upload_response.status_code == 201

    # add binary object and create entry with it
    payload = {
        "tags": ["test_type"],
        "body": {
            "ops": [
                {"insert": "Hello, world!\n"},
                {"insert": {"image": media_upload_response.json()["resource_path"]}},
                {"insert": "\n"},
            ]
        },
        "name": "test entry with media",
    }
    response = await client.post(f"/journals/{journal_id}/entries", json=payload)
    assert response.status_code == 201
    data = response.json()
    assert "body" in data
    assert "ops" in data["body"]
    ops = data["body"]["ops"]
    assert len(ops) == 3
    assert ops[0]["insert"] == "Hello, world!\n"
    assert ops[1]["insert"] == {"image": media_upload_response.json()["resource_path"]}
    assert ops[2]["insert"] == "\n"
    assert ops[2]["insert"] == "\n"


# test that media_refs is populated when creating entry with media
@pytest.mark.asyncio
async def test_entry_media_refs_populated_on_create(client):
    ws_payload = {"name": "Test Workspace"}
    ws_res = await client.post("/workspaces", json=ws_payload)
    workspace_id = ws_res.json()["id"]

    jr_payload = {"name": "Test Journal"}
    jr_res = await client.post(f"/workspaces/{workspace_id}/journals", json=jr_payload)
    journal_id = jr_res.json()["id"]

    # Upload media
    media_content = b"X" * 1024
    files = {"file": ("test.png", media_content, "image/png")}
    media_res = await client.post("/media/upload", files=files)
    assert media_res.status_code == 201
    media_path = media_res.json()["resource_path"]

    # Create entry with media
    payload = {
        "tags": ["test_type"],
        "body": {
            "ops": [
                {"insert": "Hello!\n"},
                {"insert": {"image": media_path}},
                {"insert": "\n"},
            ]
        },
        "name": "test entry",
    }
    entry_res = await client.post(f"/journals/{journal_id}/entries", json=payload)
    assert entry_res.status_code == 201
    entry_data = entry_res.json()

    # Verify media_refs is populated
    assert "media_refs" in entry_data
    assert len(entry_data["media_refs"]) == 1
    assert entry_data["media_refs"][0] == media_path


# test that media_refs supports multiple media items
@pytest.mark.asyncio
async def test_entry_media_refs_multiple_items(client):
    ws_payload = {"name": "Test Workspace"}
    ws_res = await client.post("/workspaces", json=ws_payload)
    workspace_id = ws_res.json()["id"]

    jr_payload = {"name": "Test Journal"}
    jr_res = await client.post(f"/workspaces/{workspace_id}/journals", json=jr_payload)
    journal_id = jr_res.json()["id"]

    # Upload two media files
    files1 = {"file": ("image1.png", b"A" * 512, "image/png")}
    media1_res = await client.post("/media/upload", files=files1)
    media1_path = media1_res.json()["resource_path"]

    files2 = {"file": ("image2.png", b"B" * 512, "image/png")}
    media2_res = await client.post("/media/upload", files=files2)
    media2_path = media2_res.json()["resource_path"]

    # Create entry with both media items
    payload = {
        "tags": ["test_type"],
        "body": {
            "ops": [
                {"insert": {"image": media1_path}},
                {"insert": "\n"},
                {"insert": {"image": media2_path}},
                {"insert": "\n"},
            ]
        },
        "name": "multi-media entry",
    }
    entry_res = await client.post(f"/journals/{journal_id}/entries", json=payload)
    assert entry_res.status_code == 201
    entry_data = entry_res.json()

    # Verify both media refs are captured
    assert len(entry_data["media_refs"]) == 2
    assert media1_path in entry_data["media_refs"]
    assert media2_path in entry_data["media_refs"]


# test that media_refs is updated when entry body is updated
@pytest.mark.asyncio
async def test_entry_media_refs_updated_on_body_change(client):
    ws_payload = {"name": "Test Workspace"}
    ws_res = await client.post("/workspaces", json=ws_payload)
    workspace_id = ws_res.json()["id"]

    jr_payload = {"name": "Test Journal"}
    jr_res = await client.post(f"/workspaces/{workspace_id}/journals", json=jr_payload)
    journal_id = jr_res.json()["id"]

    # Upload media
    files = {"file": ("test.png", b"X" * 512, "image/png")}
    media_res = await client.post("/media/upload", files=files)
    media_path = media_res.json()["resource_path"]

    # Create entry without media
    payload = {
        "tags": ["test_type"],
        "body": {"ops": [{"insert": "No media yet\n"}]},
        "name": "test entry",
    }
    entry_res = await client.post(f"/journals/{journal_id}/entries", json=payload)
    entry_id = entry_res.json()["id"]
    assert len(entry_res.json()["media_refs"]) == 0

    # Update entry to include media
    update_payload = {
        "body": {
            "ops": [
                {"insert": "Now with media!\n"},
                {"insert": {"image": media_path}},
                {"insert": "\n"},
            ]
        }
    }
    update_res = await client.patch(f"/entries/{entry_id}", json=update_payload)
    assert update_res.status_code == 200
    updated_data = update_res.json()

    # Verify media_refs was updated
    assert len(updated_data["media_refs"]) == 1
    assert updated_data["media_refs"][0] == media_path


# test that deleting media fails when it's referenced by an entry
@pytest.mark.asyncio
async def test_delete_media_fails_when_referenced(client, db_client):
    ws_payload = {"name": "Test Workspace"}
    ws_res = await client.post("/workspaces", json=ws_payload)
    workspace_id = ws_res.json()["id"]

    jr_payload = {"name": "Test Journal"}
    jr_res = await client.post(f"/workspaces/{workspace_id}/journals", json=jr_payload)
    journal_id = jr_res.json()["id"]

    # Upload media
    files = {"file": ("test.png", b"X" * 512, "image/png")}
    media_res = await client.post("/media/upload", files=files)
    media_path = media_res.json()["resource_path"]
    db = db_client[TEST_DB_NAME]
    doc = await db["media"].find_one({"resource_path": media_path})
    assert doc is not None
    media_id = str(doc["_id"])

    # Create entry that references the media
    payload = {
        "tags": ["test_type"],
        "body": {"ops": [{"insert": {"image": media_path}}]},
        "name": "entry with media",
    }
    entry_res = await client.post(f"/journals/{journal_id}/entries", json=payload)
    assert entry_res.status_code == 201

    # Try to delete the media - should fail
    delete_res = await client.delete(f"/media/{media_id}")
    assert delete_res.status_code == 409
    assert "still referenced" in delete_res.json()["detail"].lower()


# test that media can be deleted when not referenced
@pytest.mark.asyncio
async def test_delete_media_succeeds_when_not_referenced(client, db_client):
    # Upload media
    files = {"file": ("test.png", b"X" * 512, "image/png")}
    media_res = await client.post("/media/upload", files=files)
    media_id = await get_media_id_by_path(db_client, media_res.json()["resource_path"])

    # Delete media - should succeed (no entries reference it)
    delete_res = await client.delete(f"/media/{media_id}")
    assert delete_res.status_code == 204


# test that media can be deleted after removing from entry
@pytest.mark.asyncio
async def test_delete_media_after_removing_from_entry(client, db_client):
    ws_payload = {"name": "Test Workspace"}
    ws_res = await client.post("/workspaces", json=ws_payload)
    workspace_id = ws_res.json()["id"]

    jr_payload = {"name": "Test Journal"}
    jr_res = await client.post(f"/workspaces/{workspace_id}/journals", json=jr_payload)
    journal_id = jr_res.json()["id"]

    # Upload media
    files = {"file": ("test.png", b"X" * 512, "image/png")}
    media_res = await client.post("/media/upload", files=files)
    media_path = media_res.json()["resource_path"]
    media_id = await get_media_id_by_path(db_client, media_path)

    # Create entry with media
    payload = {
        "tags": ["test_type"],
        "body": {"ops": [{"insert": {"image": media_path}}]},
        "name": "entry with media",
    }
    entry_res = await client.post(f"/journals/{journal_id}/entries", json=payload)
    entry_id = entry_res.json()["id"]

    # Try to delete media - should fail
    delete_res = await client.delete(f"/media/{media_id}")
    assert delete_res.status_code == 409

    # Update entry to remove media
    update_payload = {"body": {"ops": [{"insert": "No media anymore\n"}]}}
    update_res = await client.patch(f"/entries/{entry_id}", json=update_payload)
    assert update_res.status_code == 200
    assert len(update_res.json()["media_refs"]) == 0

    # Now delete media - should succeed
    delete_res2 = await client.delete(f"/media/{media_id}")
    assert delete_res2.status_code == 204
    assert delete_res2.status_code == 204


@pytest.mark.asyncio
async def test_trim_media_keeps_media_referenced_by_binned_entry(client, db_client):
    ws_res = await client.post("/workspaces", json={"name": "Binned Media WS"})
    workspace_id = ws_res.json()["id"]

    jr_res = await client.post(
        f"/workspaces/{workspace_id}/journals", json={"name": "Binned Media Journal"}
    )
    journal_id = jr_res.json()["id"]

    media_res = await client.post(
        "/media/upload",
        files={"file": ("binned.png", b"B" * 512, "image/png")},
    )
    media_path = media_res.json()["resource_path"]
    media_id = await get_media_id_by_path(db_client, media_path)

    entry_res = await client.post(
        f"/journals/{journal_id}/entries",
        json={
            "tags": ["binned_media_type"],
            "body": {"ops": [{"insert": {"image": media_path}}, {"insert": "\n"}]},
            "name": "Binned Media Entry",
        },
    )
    entry_id = entry_res.json()["id"]

    delete_res = await client.delete(f"/entries/{entry_id}")
    assert delete_res.status_code == 204

    trim_res = await client.post("/media/trim")
    assert trim_res.status_code == 200

    db = db_client[TEST_DB_NAME]
    media_doc = await db["media"].find_one({"_id": ObjectId(media_id)})
    assert media_doc is not None


# ── Webpage media tests ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_save_webpage_rejects_invalid_url(client):
    res = await client.post("/media/save-webpage", json={"url": "ftp://example.com"})
    assert res.status_code == 422


@pytest.mark.asyncio
async def test_save_webpage_rejects_private_ip(client):
    res = await client.post(
        "/media/save-webpage", json={"url": "http://127.0.0.1/secret"}
    )
    assert res.status_code == 422


@pytest.mark.asyncio
async def test_save_webpage_creates_archive(client, db_client, tmp_path):
    """Mock SingleFile CLI; verify archive file and DB record."""
    from pathlib import Path

    archive_started = asyncio.Event()
    allow_archive_completion = asyncio.Event()

    async def fake_archive(url, output_path):
        archive_started.set()
        await allow_archive_completion.wait()
        Path(output_path).write_text(
            "<html><head><title>Test Page</title></head><body>Hello</body></html>",
            encoding="utf-8",
        )
        return {
            "page_title": "Test Page",
            "archived_at": "2026-01-01T00:00:00+00:00",
        }

    with patch("app.utils.webpage_archiver.archive_webpage", new=fake_archive):
        res = await client.post(
            "/media/save-webpage", json={"url": "http://example.com/"}
        )

        assert res.status_code == 201
        data = res.json()
        assert data["media_type"] == "webpage"
        assert data["status"] == "pending"
        assert data["file_size"] == 0
        assert "custom_metadata" in data
        assert data["custom_metadata"]["source_url"] == "http://example.com/"
        assert data["custom_metadata"]["page_title"] == ""
        assert data["resource_path"].endswith(".html")
        assert "/index.html" not in data["resource_path"]
        assert "asset_count" not in (data["custom_metadata"] or {})
        assert "http_status" not in (data["custom_metadata"] or {})

        await asyncio.sleep(0)
        await asyncio.wait_for(archive_started.wait(), timeout=1)

        db = db_client[TEST_DB_NAME]
        doc = await db["media"].find_one({"resource_path": data["resource_path"]})
        assert doc is not None
        assert doc["media_type"] == "webpage"
        assert doc["status"] == "pending"

        allow_archive_completion.set()
        await media_routes.wait_for_webpage_archive_tasks()

    data = res.json()
    db = db_client[TEST_DB_NAME]

    parts = data["resource_path"].split("/")
    stored_filename = parts[-1]
    media_file = os.path.join(MEDIA_PATH, "test-user-id", stored_filename)
    assert os.path.isfile(media_file)

    completed_doc = await db["media"].find_one({"resource_path": data["resource_path"]})
    assert completed_doc is not None
    assert completed_doc["stored_filename"] == stored_filename
    assert completed_doc["status"] == "completed"
    assert completed_doc["custom_metadata"]["page_title"] == "Test Page"


@pytest.mark.asyncio
async def test_get_media_status_returns_updated_archive_state(client):
    archive_started = asyncio.Event()
    allow_archive_completion = asyncio.Event()

    async def fake_archive(url, output_path):
        archive_started.set()
        await allow_archive_completion.wait()
        Path(output_path).write_text(
            "<html><head><title>Status Page</title></head><body>Hello</body></html>",
            encoding="utf-8",
        )
        return {
            "page_title": "Status Page",
            "archived_at": "2026-01-01T00:00:00+00:00",
        }

    from pathlib import Path

    with patch("app.utils.webpage_archiver.archive_webpage", new=fake_archive):
        res = await client.post(
            "/media/save-webpage", json={"url": "http://example.com/status"}
        )

        resource_path = res.json()["resource_path"]
        pending_res = await client.get(
            "/media/status", params={"resource_path": resource_path}
        )
        assert pending_res.status_code == 200
        assert pending_res.json()["status"] == "pending"

        await asyncio.sleep(0)
        await asyncio.wait_for(archive_started.wait(), timeout=1)
        allow_archive_completion.set()
        await media_routes.wait_for_webpage_archive_tasks()

    resource_path = res.json()["resource_path"]

    completed_res = await client.get(
        "/media/status", params={"resource_path": resource_path}
    )
    assert completed_res.status_code == 200
    assert completed_res.json()["status"] == "completed"
    assert completed_res.json()["custom_metadata"]["page_title"] == "Status Page"


@pytest.mark.asyncio
async def test_save_webpage_marks_failed_archive(client, db_client):
    from pathlib import Path

    async def fake_archive(url, output_path):
        Path(output_path).write_text("partial", encoding="utf-8")
        raise RuntimeError("SingleFile exited with code 1")

    with patch("app.utils.webpage_archiver.archive_webpage", new=fake_archive):
        res = await client.post(
            "/media/save-webpage", json={"url": "http://example.com/fail"}
        )

        assert res.status_code == 201
        resource_path = res.json()["resource_path"]
        await media_routes.wait_for_webpage_archive_tasks()

    resource_path = res.json()["resource_path"]

    db = db_client[TEST_DB_NAME]
    doc = await db["media"].find_one({"resource_path": resource_path})
    assert doc is not None
    assert doc["status"] == "failed"
    assert "SingleFile exited with code 1" in doc["error_message"]

    stored_filename = resource_path.split("/")[-1]
    media_file = os.path.join(MEDIA_PATH, "test-user-id", stored_filename)
    assert not os.path.exists(media_file)
    assert doc["stored_filename"] == stored_filename


@pytest.mark.asyncio
async def test_delete_webpage_media_removes_file(client, db_client):
    """Deleting a webpage media record should remove the archived HTML file."""
    from pathlib import Path

    async def fake_archive(url, output_path):
        Path(output_path).write_text(
            "<html><head><title>Del Page</title></head><body>bye</body></html>",
            encoding="utf-8",
        )
        return {
            "page_title": "Del Page",
            "archived_at": "2026-01-01T00:00:00+00:00",
        }

    with patch("app.utils.webpage_archiver.archive_webpage", new=fake_archive):
        res = await client.post(
            "/media/save-webpage", json={"url": "http://example.com/del"}
        )
        assert res.status_code == 201
        await media_routes.wait_for_webpage_archive_tasks()

    resource_path = res.json()["resource_path"]
    db = db_client[TEST_DB_NAME]
    doc = await db["media"].find_one({"resource_path": resource_path})
    assert doc is not None
    media_id = str(doc["_id"])

    stored_filename = resource_path.split("/")[-1]
    media_file = os.path.join(MEDIA_PATH, "test-user-id", stored_filename)
    assert os.path.isfile(media_file)

    delete_res = await client.delete(f"/media/{media_id}")
    assert delete_res.status_code == 204

    assert not os.path.exists(media_file)


@pytest.mark.asyncio
async def test_webpage_media_ref_extracted_from_entry(client):
    """webpage embeds in entry body should appear in media_refs."""
    ws_res = await client.post("/workspaces", json={"name": "Webpage WS"})
    workspace_id = ws_res.json()["id"]
    jr_res = await client.post(
        f"/workspaces/{workspace_id}/journals", json={"name": "Webpage J"}
    )
    journal_id = jr_res.json()["id"]

    archive_url = "http://localhost:8128/media/test-user-id/fakeabcdef/index.html"
    entry_payload = {
        "tags": ["web"],
        "name": "webpage entry",
        "body": {
            "ops": [
                {"insert": "some text\n"},
                {
                    "insert": {
                        "webpage": {
                            "src": archive_url,
                            "source_url": "http://example.com/",
                            "title": "Test Page",
                        }
                    }
                },
                {"insert": "\n"},
            ]
        },
    }
    entry_res = await client.post(f"/journals/{journal_id}/entries", json=entry_payload)
    assert entry_res.status_code == 201
    data = entry_res.json()
    assert archive_url in data["media_refs"]


# ── Opus audio tests ──────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_upload_opus_audio_accepted(client):
    """audio/opus MIME type should be accepted and stored as media_type 'audio'."""
    audio_content = b"\x00" * 1024
    files = {"file": ("test_voice.opus", audio_content, "audio/opus")}
    response = await client.post("/media/upload", files=files)
    assert response.status_code == 201
    data = response.json()
    assert data["media_type"] == "audio"
    assert data["original_filename"] == "test_voice.opus"
    assert data["file_size"] == len(audio_content)
    assert "resource_path" in data


@pytest.mark.asyncio
async def test_upload_opus_creates_db_record(client, db_client):
    """Uploading an opus file should create a DB record with the correct fields."""
    audio_content = b"\x01" * 512
    files = {"file": ("voice_note.opus", audio_content, "audio/opus")}
    response = await client.post("/media/upload", files=files)
    assert response.status_code == 201
    res = response.json()
    media_id = await get_media_id_by_path(db_client, res["resource_path"])

    db = db_client[TEST_DB_NAME]
    doc = await db["media"].find_one({"_id": ObjectId(media_id)})
    assert doc is not None
    assert doc["media_type"] == "audio"
    assert doc["original_filename"] == "voice_note.opus"
    assert doc["stored_filename"].endswith(".opus")
    assert doc["file_size"] == 512
    assert doc["user_id"] == "test-user-id"


@pytest.mark.asyncio
async def test_upload_opus_stored_file_exists(client):
    """The actual file should be written to disk after an opus upload."""
    audio_content = b"\x02" * 256
    files = {"file": ("disk_check.opus", audio_content, "audio/opus")}
    response = await client.post("/media/upload", files=files)
    assert response.status_code == 201
    data = response.json()

    parts = data["resource_path"].split("/")
    stored_filename = parts[-1]
    media_file = os.path.join(MEDIA_PATH, "test-user-id", stored_filename)
    assert os.path.isfile(media_file)


@pytest.mark.asyncio
async def test_upload_opus_resource_path_accessible(client):
    """The resource_path returned for an opus upload should be retrievable."""
    audio_content = b"\x03" * 128
    files = {"file": ("accessible.opus", audio_content, "audio/opus")}
    upload_res = await client.post("/media/upload", files=files)
    assert upload_res.status_code == 201
    resource_path = upload_res.json()["resource_path"]
    assert resource_path.startswith("http://localhost:8128/media/")
    assert resource_path.endswith(".opus")


@pytest.mark.asyncio
async def test_upload_opus_via_ogg_mime_accepted(client):
    """Browsers report .opus files as audio/ogg — this should also be accepted."""
    audio_content = b"\x03" * 128
    files = {"file": ("browser_voice.opus", audio_content, "audio/ogg")}
    res = await client.post("/media/upload", files=files)
    assert res.status_code == 201
    data = res.json()
    assert data["media_type"] == "audio"
    assert data["original_filename"] == "browser_voice.opus"


# ── PDF media tests ───────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_upload_pdf_accepted(client):
    """application/pdf MIME type should be accepted and stored as media_type 'pdf'."""
    pdf_content = b"%PDF-1.4 fake content" + b"\x00" * 512
    files = {"file": ("document.pdf", pdf_content, "application/pdf")}
    response = await client.post("/media/upload", files=files)
    assert response.status_code == 201
    data = response.json()
    assert data["media_type"] == "pdf"
    assert data["original_filename"] == "document.pdf"
    assert data["file_size"] == len(pdf_content)
    assert "resource_path" in data
    assert data["status"] == "completed"


@pytest.mark.asyncio
async def test_upload_pdf_creates_db_record(client, db_client):
    """Uploading a PDF file should create a DB record with the correct fields."""
    pdf_content = b"%PDF-1.4 db test" + b"\x00" * 256
    files = {"file": ("report.pdf", pdf_content, "application/pdf")}
    response = await client.post("/media/upload", files=files)
    assert response.status_code == 201
    res = response.json()
    media_id = await get_media_id_by_path(db_client, res["resource_path"])

    db = db_client[TEST_DB_NAME]
    doc = await db["media"].find_one({"_id": ObjectId(media_id)})
    assert doc is not None
    assert doc["media_type"] == "pdf"
    assert doc["original_filename"] == "report.pdf"
    assert doc["stored_filename"].endswith(".pdf")
    assert doc["user_id"] == "test-user-id"


@pytest.mark.asyncio
async def test_entry_with_pdf_embed_populates_media_refs(client):
    """A pdf embed op in an entry body should appear in media_refs."""
    ws_res = await client.post("/workspaces", json={"name": "PDF WS"})
    workspace_id = ws_res.json()["id"]
    jr_res = await client.post(
        f"/workspaces/{workspace_id}/journals", json={"name": "PDF Journal"}
    )
    journal_id = jr_res.json()["id"]

    pdf_content = b"%PDF-1.4 entry test" + b"\x00" * 128
    upload_res = await client.post(
        "/media/upload",
        files={"file": ("entry_doc.pdf", pdf_content, "application/pdf")},
    )
    assert upload_res.status_code == 201
    pdf_url = upload_res.json()["resource_path"]

    entry_payload = {
        "tags": ["pdf_test"],
        "name": "PDF entry",
        "body": {
            "ops": [
                {"insert": "See attached document:\n"},
                {"insert": {"pdf": pdf_url}},
                {"insert": "\n"},
            ]
        },
    }
    entry_res = await client.post(f"/journals/{journal_id}/entries", json=entry_payload)
    assert entry_res.status_code == 201
    data = entry_res.json()
    assert pdf_url in data["media_refs"]
