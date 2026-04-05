"""Tests for data_management module"""

import os
from typing import Any

import pytest
from app.constants import DUMPS_PATH
from app.routes.media import ALLOWED_MIME
from bson import ObjectId
from tests.conftest import FIXTURE_HASHKEY, TEST_DB_NAME

# Export Tests


@pytest.fixture(autouse=True, scope="module")
def setup_data_management_test_environment():
    yield
    dumps_dir = DUMPS_PATH
    user_dir = os.path.join(dumps_dir, "test-user-id")
    if os.path.exists(user_dir):
        for filename in os.listdir(user_dir):
            file_path = os.path.join(user_dir, filename)
            if os.path.isfile(file_path):
                os.remove(file_path)
        os.rmdir(user_dir)


@pytest.mark.asyncio
async def test_export_empty_user(client):
    """Test export with no data returns success with zero counts."""
    response = await client.post("/data-management/export")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert "filename" in data


@pytest.mark.asyncio
async def test_export_requires_privileged_mode(unprivileged_client):
    response = await unprivileged_client.post("/data-management/export")
    assert response.status_code == 403
    assert "privileged mode required" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_export_with_data(client):
    """Test export after creating workspace, journal, and entry."""
    # Create workspace
    ws_res = await client.post("/workspaces", json={"name": "Export Test WS"})
    assert ws_res.status_code == 201
    ws_id = ws_res.json()["id"]

    # Create journal
    jr_res = await client.post(
        f"/workspaces/{ws_id}/journals", json={"name": "Export Test Journal"}
    )
    assert jr_res.status_code == 201
    jr_id = jr_res.json()["id"]

    # Create entry
    entry_payload = {
        "type": "export_test",
        "body": {"ops": [{"insert": "Export test content\n"}]},
        "name": "Export Test Entry",
    }
    entry_res = await client.post(f"/journals/{jr_id}/entries", json=entry_payload)
    assert entry_res.status_code == 201

    # Export
    export_res = await client.post("/data-management/export")
    assert export_res.status_code == 200
    data = export_res.json()
    assert data["status"] == "success"
    assert "workspaces" in data["message"]
    assert "journals" in data["message"]
    assert "entries" in data["message"]


@pytest.mark.asyncio
async def test_export_encryption_key_validation(client):
    """Test that export works without any key input."""
    response = await client.post("/data-management/export")
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_export_does_not_delete_user_data(client):
    """Test export endpoint creates dump without removing account access."""
    response = await client.post("/data-management/export")
    assert response.status_code == 200

    # Request still succeeds with same token, confirming no account deletion happened.
    workspaces_res = await client.get("/workspaces")
    assert workspaces_res.status_code == 200


@pytest.mark.asyncio
async def test_export_trims_orphaned_media(client, db_client):
    upload_res = await client.post(
        "/media/upload",
        files={"file": ("export_orphan.png", b"X" * 256, "image/png")},
    )
    assert upload_res.status_code == 201
    orphan_path = upload_res.json()["resource_path"]

    db = db_client[TEST_DB_NAME]
    orphan_before = await db["media"].find_one({"resource_path": orphan_path})
    assert orphan_before is not None

    export_res = await client.post("/data-management/export")
    assert export_res.status_code == 200

    orphan_after = await db["media"].find_one({"resource_path": orphan_path})
    assert orphan_after is None


# Import Encrypted Tests


@pytest.mark.asyncio
async def test_import_invalid_key(client):
    """Test import with wrong hashkey fails to decrypt."""
    # First create and export some data
    ws_res = await client.post("/workspaces", json={"name": "Import Test WS"})
    assert ws_res.status_code == 201

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
async def test_import_encrypted_roundtrip(client):
    """Test full export/import cycle preserves data."""
    # Create test data with unique name to identify
    unique_name = f"Roundtrip WS {ObjectId()}"
    ws_res = await client.post("/workspaces", json={"name": unique_name})
    ws_id = ws_res.json()["id"]

    jr_res = await client.post(
        f"/workspaces/{ws_id}/journals", json={"name": "Roundtrip Journal"}
    )
    jr_id = jr_res.json()["id"]

    entry_payload = {
        "type": "roundtrip_type",
        "body": {"ops": [{"insert": "Roundtrip content\n"}]},
        "name": "Roundtrip Entry",
    }
    entry_res = await client.post(f"/journals/{jr_id}/entries", json=entry_payload)
    assert entry_res.status_code == 201

    # Export
    export_res = await client.post("/data-management/export")
    filename = export_res.json()["filename"]

    # Download
    download_res = await client.get(f"/data-management/export/download/{filename}")

    # Delete original data
    await client.delete(f"/workspaces/{ws_id}")

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
    # At least our workspace/journal/entry should be imported
    assert data["workspaces_imported"] >= 1
    assert data["journals_imported"] >= 1
    assert data["entries_imported"] >= 1


@pytest.mark.asyncio
async def test_export_import_preserves_binned_entries(client):
    ws_res = await client.post(
        "/workspaces", json={"name": f"Binned Export WS {ObjectId()}"}
    )
    assert ws_res.status_code == 201
    ws_id = ws_res.json()["id"]

    jr_res = await client.post(
        f"/workspaces/{ws_id}/journals", json={"name": "Binned Export Journal"}
    )
    assert jr_res.status_code == 201
    jr_id = jr_res.json()["id"]

    entry_res = await client.post(
        f"/journals/{jr_id}/entries",
        json={
            "type": "binned_export_type",
            "body": {"ops": [{"insert": "Keep me in the bin\n"}]},
            "name": "Binned Export Entry",
        },
    )
    assert entry_res.status_code == 201
    entry_id = entry_res.json()["id"]

    delete_res = await client.delete(f"/entries/{entry_id}")
    assert delete_res.status_code == 204

    export_res = await client.post("/data-management/export")
    assert export_res.status_code == 200
    filename = export_res.json()["filename"]

    download_res = await client.get(f"/data-management/export/download/{filename}")
    assert download_res.status_code == 200

    import_res = await client.post(
        "/data-management/import/encrypted",
        data={
            "hashkey": FIXTURE_HASHKEY,
            "conflict_resolution": "create_new",
        },
        files={"file": ("dump.bin", download_res.content, "application/octet-stream")},
    )
    assert import_res.status_code == 200
    assert import_res.json()["entries_imported"] >= 1

    bin_res = await client.get("/entries/bin")
    assert bin_res.status_code == 200
    matching_entries = [
        item for item in bin_res.json() if item["name"] == "Binned Export Entry"
    ]
    assert matching_entries
    assert any(item["is_deleted"] is True for item in matching_entries)


@pytest.mark.asyncio
async def test_import_encrypted_all_allowed_mime_updates_media_refs(client):
    """Ensure all allowed MIME uploads survive import and media refs point to new URLs."""
    unique_id = str(ObjectId())
    ws_name = f"MIME Roundtrip WS {unique_id}"
    journal_name = f"MIME Roundtrip Journal {unique_id}"
    entry_name = f"MIME Roundtrip Entry {unique_id}"

    ws_res = await client.post("/workspaces", json={"name": ws_name})
    assert ws_res.status_code == 201
    ws_id = ws_res.json()["id"]

    jr_res = await client.post(
        f"/workspaces/{ws_id}/journals", json={"name": journal_name}
    )
    assert jr_res.status_code == 201
    jr_id = jr_res.json()["id"]

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
    }

    old_media_urls = []
    entry_ops: list[dict[str, Any]] = [{"insert": "MIME roundtrip body\n"}]

    for i, mime in enumerate(sorted(ALLOWED_MIME)):
        filename = f"mime_{i}{ext_by_mime[mime]}"
        file_content = f"payload-{mime}".encode("utf-8")
        upload_res = await client.post(
            "/media/upload",
            files={"file": (filename, file_content, mime)},
        )
        assert upload_res.status_code == 201
        media_url = upload_res.json()["resource_path"]
        old_media_urls.append(media_url)

        if mime.startswith("image"):
            embed_key = "image"
        elif mime.startswith("video"):
            embed_key = "video"
        else:
            embed_key = "audio"

        entry_ops.append({"insert": {embed_key: media_url}})
        entry_ops.append({"insert": "\n"})

    entry_payload = {
        "type": "mime_roundtrip",
        "body": {"ops": entry_ops},
        "name": entry_name,
    }
    entry_res = await client.post(f"/journals/{jr_id}/entries", json=entry_payload)
    assert entry_res.status_code == 201

    export_res = await client.post("/data-management/export")
    assert export_res.status_code == 200
    filename = export_res.json()["filename"]

    download_res = await client.get(f"/data-management/export/download/{filename}")
    assert download_res.status_code == 200

    # Remove the original workspace tree so we can verify only imported refs.
    await client.delete(f"/workspaces/{ws_id}")

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

    body_ops = imported_entry["body"]["ops"]
    body_urls = []
    for op in body_ops:
        insert = op.get("insert")
        if isinstance(insert, dict):
            for key in ("image", "video", "audio"):
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
async def test_import_conflict_skip(client):
    """Test that skip conflict resolution works."""
    # Create workspace
    ws_res = await client.post("/workspaces", json={"name": "Conflict Test WS"})
    assert ws_res.status_code == 201

    # Export
    export_res = await client.post("/data-management/export")
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
    assert data["skipped"] >= 1  # At least the workspace was skipped


# Import Plaintext Tests


@pytest.mark.asyncio
async def test_import_plaintext_basic(client):
    """Test basic plaintext import without media."""
    # Create workspace and journal
    ws_res = await client.post("/workspaces", json={"name": "Plaintext Test WS"})
    ws_id = ws_res.json()["id"]

    jr_res = await client.post(
        f"/workspaces/{ws_id}/journals", json={"name": "Plaintext Journal"}
    )
    jr_id = jr_res.json()["id"]

    # Create plaintext entry file
    plaintext_content = """2024-06-15
Plaintext Journal
daily_note
My Daily Entry
<<<>>>[mood |-| happy]
<<<>>>[weather |-| sunny]
This is the body of my entry.
It has multiple lines.
"""

    import_res = await client.post(
        "/data-management/import/plaintext",
        data={
            "journal_id": jr_id,
            "conflict_resolution": "create_new",
        },
        files={
            "entry_file": ("entry.txt", plaintext_content.encode(), "text/plain"),
        },
    )

    assert import_res.status_code == 200
    data = import_res.json()
    assert data["status"] == "success"
    assert data["entry_id"] is not None

    # Verify the entry was created by listing entries in the journal
    entries_res = await client.get(f"/journals/{jr_id}/entries")
    assert entries_res.status_code == 200
    entries = entries_res.json()
    assert len(entries) == 1
    assert entries[0]["name"] == "My Daily Entry"
    assert entries[0]["type"] == "daily_note"
    assert len(entries[0]["custom_metadata"]) == 2


@pytest.mark.asyncio
async def test_import_plaintext_with_media(client):
    """Test plaintext import with media references."""
    # Create workspace and journal
    ws_res = await client.post("/workspaces", json={"name": "Plaintext Media WS"})
    ws_id = ws_res.json()["id"]

    jr_res = await client.post(
        f"/workspaces/{ws_id}/journals", json={"name": "Plaintext Media Journal"}
    )
    jr_id = jr_res.json()["id"]

    # Create plaintext with media reference
    plaintext_content = """2024-06-15
Plaintext Journal
photo_entry
Entry With Photo
This entry has an image:
<<>>test_image.png
And some more text.
"""

    # Create fake image
    image_content = b"PNG" + b"\x00" * 100

    import_res = await client.post(
        "/data-management/import/plaintext",
        data={
            "journal_id": jr_id,
            "conflict_resolution": "create_new",
        },
        files=[
            ("entry_file", ("entry.txt", plaintext_content.encode(), "text/plain")),
            ("media_files", ("test_image.png", image_content, "image/png")),
        ],
    )

    assert import_res.status_code == 200
    data = import_res.json()
    assert data["status"] == "success"
    assert data["media_imported"] == 1


@pytest.mark.asyncio
async def test_import_plaintext_missing_media(client):
    """Test plaintext import with missing media file reports error."""
    ws_res = await client.post("/workspaces", json={"name": "Missing Media WS"})
    ws_id = ws_res.json()["id"]

    jr_res = await client.post(
        f"/workspaces/{ws_id}/journals", json={"name": "Missing Media Journal"}
    )
    jr_id = jr_res.json()["id"]

    plaintext_content = """2024-06-15
Journal
entry_type
Entry Name
<<>>missing_file.png
Text content.
"""

    import_res = await client.post(
        "/data-management/import/plaintext",
        data={
            "journal_id": jr_id,
            "conflict_resolution": "create_new",
        },
        files={
            "entry_file": ("entry.txt", plaintext_content.encode(), "text/plain"),
        },
    )

    assert import_res.status_code == 200
    data = import_res.json()
    assert "missing_file.png" in str(data["errors"])


@pytest.mark.asyncio
async def test_import_plaintext_invalid_journal(client):
    """Test plaintext import with invalid journal ID."""
    plaintext_content = """2024-06-15
Journal
type
Name
Body text.
"""

    import_res = await client.post(
        "/data-management/import/plaintext",
        data={
            "journal_id": str(ObjectId()),  # Non-existent journal
            "conflict_resolution": "create_new",
        },
        files={
            "entry_file": ("entry.txt", plaintext_content.encode(), "text/plain"),
        },
    )

    assert import_res.status_code == 404


# Utility Function Tests


def test_parse_plaintext_entry():
    """Test plaintext parsing utility."""
    from app.utils.data_management import parse_plaintext_entry

    content = """2024-01-15
My Journal
daily_log
Morning Notes
<<<>>>[mood |-| energetic]
<<<>>>[location |-| home]
Started the day early.
Had coffee.
<<>>breakfast.jpg
Felt great!
"""

    result = parse_plaintext_entry(content)
    assert result.date is not None
    assert result.date.year == 2024
    assert result.date.month == 1
    assert result.date.day == 15
    assert result.journal_name == "My Journal"
    assert result.entry_type == "daily_log"
    assert result.entry_name == "Morning Notes"
    assert len(result.custom_metadata) == 2
    assert result.custom_metadata[0]["key"] == "mood"
    assert result.custom_metadata[0]["value"] == "energetic"
    assert "breakfast.jpg" in result.media_references
    assert "Started the day early" in result.body_text


def test_parse_plaintext_entry_media_filename_with_spaces():
    """Quoted media markers should support filenames with spaces."""
    from app.utils.data_management import parse_plaintext_entry

    content = """2024-01-15
My Journal
daily_log
Morning Notes
Look at this image:
<<>>"breakfast photo 01.jpg"
"""

    result = parse_plaintext_entry(content)
    assert "breakfast photo 01.jpg" in result.media_references


def test_encryption_roundtrip():
    """Test encryption/decryption works correctly."""
    from app.utils.data_management import decrypt_data, encrypt_data

    original = '{"test": "data", "unicode": "日本語"}'
    key = "my_test_encryption_key"

    encrypted = encrypt_data(original, key)
    assert encrypted != original.encode()

    decrypted = decrypt_data(encrypted, key)
    assert decrypted == original


def test_encryption_wrong_key():
    """Test decryption with wrong key returns None."""
    from app.utils.data_management import decrypt_data, encrypt_data

    original = "secret data"
    encrypted = encrypt_data(original, "correct_key")

    result = decrypt_data(encrypted, "wrong_key")
    assert result is None


def test_convert_body_to_quill_delta():
    """Test body text to Quill Delta conversion."""
    from app.utils.data_management import convert_body_to_quill_delta

    body_text = "Hello world!\n<<>>image.png\nMore text."
    media_refs = {"image.png": "http://localhost:8128/media/user/abc123.png"}

    delta = convert_body_to_quill_delta(body_text, media_refs)

    assert "ops" in delta
    ops = delta["ops"]

    # Should have image insert
    has_image = any(
        isinstance(op.get("insert"), dict) and "image" in op["insert"] for op in ops
    )
    assert has_image


def test_convert_body_to_quill_delta_media_filename_with_spaces():
    """Quoted markers with spaces should resolve to media embeds."""
    from app.utils.data_management import convert_body_to_quill_delta

    body_text = 'Before\n<<>>"my photo.png"\nAfter'
    media_refs = {"my photo.png": "http://localhost:8128/media/user/photo.png"}

    delta = convert_body_to_quill_delta(body_text, media_refs)
    ops = delta["ops"]
    assert any(
        isinstance(op.get("insert"), dict)
        and op["insert"].get("image") == "http://localhost:8128/media/user/photo.png"
        for op in ops
    )


def test_validate_dump_structure():
    """Test dump structure validation."""
    from app.utils.data_management import validate_dump_structure

    # Valid dump
    valid_dump = {
        "version": "1.0",
        "user_id": "test-user",
        "workspaces": [],
        "journals": [],
        "entries": [],
    }
    valid, msg = validate_dump_structure(valid_dump)
    assert valid

    # Missing key
    invalid_dump = {
        "version": "1.0",
        "user_id": "test-user",
        "workspaces": [],
    }
    valid, msg = validate_dump_structure(invalid_dump)
    assert not valid
    assert "Missing" in msg

    # Invalid version
    invalid_version_dump = {
        "version": "2.0",
        "user_id": "test-user",
        "workspaces": [],
        "journals": [],
        "entries": [],
    }
    valid, msg = validate_dump_structure(invalid_version_dump)
    assert not valid
    assert "version" in msg.lower()


def test_update_media_refs_in_body_handles_object_embed_values():
    """Media URL remapping should support object embeds (e.g. audio blot payloads)."""
    from app.utils.data_management import update_media_refs_in_body

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
