import pytest
from bson import ObjectId
from tests.conftest import TEST_DB_NAME


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
    assert res["status"] == "success"
    assert res["resource_type"] == "image"
    assert "resource_path" in res
    assert "media_id" in res


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
    assert "media_id" in res
    media_id = res["media_id"]

    db = db_client[TEST_DB_NAME]
    doc = await db["media"].find_one({"_id": ObjectId(media_id)})
    assert doc is not None
    assert doc["original_filename"] == "test_x.png"
    assert doc["stored_filename"].endswith(".png")
    assert doc["media_type"] == "image"
    assert doc["file_size"] == 512
    assert doc["user_id"] == "test-user-id"  # from test auth fixture
    assert "resource_path" in res
    assert "created_at" in doc


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
    assert data1["media_id"] != data2["media_id"]


# test deleting media
@pytest.mark.asyncio
async def test_delete_media(client, db_client):
    media_content = b"X" * 128
    files = {
        "file": ("delete_test.png", media_content, "image/png"),
    }
    upload_res = await client.post("/media/upload", files=files)
    assert upload_res.status_code == 201
    media_id = upload_res.json()["media_id"]

    delete_res = await client.delete(f"/media/{media_id}")
    assert delete_res.status_code == 204

    db = db_client[TEST_DB_NAME]
    doc = await db["media"].find_one({"_id": ObjectId(media_id)})
    assert doc is None


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
