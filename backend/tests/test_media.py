import os

import pytest
from app.constants import DUMPS_PATH, MEDIA_PATH
from bson import ObjectId
from tests.conftest import TEST_DB_NAME


@pytest.fixture(autouse=True, scope="module")
def setup_media_test_environment():
    yield
    # clear media data for user directory after each test
    media_dir = os.path.join(MEDIA_PATH, "test-user-id")
    if os.path.exists(media_dir):
        for filename in os.listdir(media_dir):
            file_path = os.path.join(media_dir, filename)
            if os.path.isfile(file_path):
                os.remove(file_path)
        os.rmdir(media_dir)


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
        "type": "trim_test",
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

    db = db_client[TEST_DB_NAME]
    kept_doc = await db["media"].find_one({"_id": ObjectId(kept_media_id)})
    orphan_doc = await db["media"].find_one({"_id": ObjectId(orphan_media_id)})
    assert kept_doc is not None
    assert orphan_doc is None


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
        "type": "test_type",
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
        "type": "test_type",
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
        "type": "test_type",
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
        "type": "test_type",
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
        "type": "test_type",
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
        "type": "test_type",
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
