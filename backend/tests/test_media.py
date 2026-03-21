import pytest


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
