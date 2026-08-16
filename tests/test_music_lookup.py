"""Tests for music identification (AcoustID → MusicBrainz) pipeline."""

import asyncio
import os
import shutil
from unittest.mock import AsyncMock, patch

import pytest
from app.constants import MEDIA_PATH
from app.routes import media as media_routes
from tests.conftest import TEST_DB_NAME


@pytest.fixture(autouse=True, scope="module")
def setup_music_test_environment():
    yield
    media_dir = os.path.join(MEDIA_PATH, "test-user-id")
    if os.path.exists(media_dir):
        shutil.rmtree(media_dir)


MOCK_MUSIC_INFO = {
    "title": "Test Song",
    "artist": "Test Artist",
    "album": "Test Album",
    "year": "2024",
    "mbid": "12345678-1234-1234-1234-123456789abc",
    "cover_art_base64": "dGVzdA==",  # base64 of "test"
}


@pytest.mark.asyncio
async def test_audio_upload_triggers_music_lookup(client, db_client):
    """Audio upload should set music_lookup_status to pending and schedule background lookup."""
    audio_content = b"\x00" * 1024

    with patch(
        "app.routes.media._finalize_music_lookup",
        new=AsyncMock(return_value=None),
    ):
        files = {"file": ("test_song.mp3", audio_content, "audio/mpeg")}
        response = await client.post("/media/upload", files=files)

    assert response.status_code == 201
    res = response.json()
    assert res["media_type"] == "audio"
    assert res["custom_metadata"]["music_lookup_status"] == "pending"


@pytest.mark.asyncio
async def test_audio_upload_with_successful_identification(client, db_client):
    """When identify_song returns data, custom_metadata should be populated."""
    audio_content = b"\x00" * 2048

    with patch("app.utils.music_lookup.identify_song", return_value=MOCK_MUSIC_INFO):
        files = {"file": ("identified_song.mp3", audio_content, "audio/mpeg")}
        response = await client.post("/media/upload", files=files)
        assert response.status_code == 201

        # Wait for background task to complete
        await media_routes.wait_for_music_lookup_tasks()

    resource_path = response.json()["resource_path"]
    db = db_client[TEST_DB_NAME]
    doc = await db["media"].find_one({"resource_path": resource_path})
    assert doc is not None
    assert doc["custom_metadata"]["music_lookup_status"] == "completed"
    assert doc["custom_metadata"]["music_info"]["title"] == "Test Song"
    assert doc["custom_metadata"]["music_info"]["artist"] == "Test Artist"
    assert doc["custom_metadata"]["music_info"]["album"] == "Test Album"
    assert doc["custom_metadata"]["music_info"]["year"] == "2024"
    assert doc["custom_metadata"]["music_info"]["mbid"] == MOCK_MUSIC_INFO["mbid"]


@pytest.mark.asyncio
async def test_audio_upload_no_match(client, db_client):
    """When identify_song returns None, status should be not_found."""
    audio_content = b"\x00" * 2048

    with patch("app.utils.music_lookup.identify_song", return_value=None):
        files = {"file": ("voice_memo.mp3", audio_content, "audio/mpeg")}
        response = await client.post("/media/upload", files=files)
        assert response.status_code == 201

        await media_routes.wait_for_music_lookup_tasks()

    resource_path = response.json()["resource_path"]
    db = db_client[TEST_DB_NAME]
    doc = await db["media"].find_one({"resource_path": resource_path})
    assert doc is not None
    assert doc["custom_metadata"]["music_lookup_status"] == "not_found"
    assert "music_info" not in doc["custom_metadata"]


@pytest.mark.asyncio
async def test_audio_upload_identification_error(client, db_client):
    """When identify_song raises an exception, status should be failed."""
    audio_content = b"\x00" * 2048

    with patch(
        "app.utils.music_lookup.identify_song",
        side_effect=RuntimeError("fpcalc not found"),
    ):
        files = {"file": ("error_song.mp3", audio_content, "audio/mpeg")}
        response = await client.post("/media/upload", files=files)
        assert response.status_code == 201

        await media_routes.wait_for_music_lookup_tasks()

    resource_path = response.json()["resource_path"]
    db = db_client[TEST_DB_NAME]
    doc = await db["media"].find_one({"resource_path": resource_path})
    assert doc is not None
    assert doc["custom_metadata"]["music_lookup_status"] == "failed"


@pytest.mark.asyncio
async def test_identify_music_endpoint(client, db_client):
    """POST /media/identify-music should trigger music lookup for existing audio."""
    audio_content = b"\x00" * 1024

    # Upload audio without music identification
    with patch("app.utils.music_lookup.identify_song", return_value=None):
        files = {"file": ("manual_id.mp3", audio_content, "audio/mpeg")}
        response = await client.post("/media/upload", files=files)
        assert response.status_code == 201
        await media_routes.wait_for_music_lookup_tasks()

    resource_path = response.json()["resource_path"]

    # Explicitly force re-identification after a previous "not_found" result.
    # force=True is required because the endpoint skips "not_found" without it.
    with patch("app.utils.music_lookup.identify_song", return_value=MOCK_MUSIC_INFO):
        response = await client.post(
            "/media/identify-music",
            params={"resource_path": resource_path, "force": "true"},
        )
        assert response.status_code == 200
        await media_routes.wait_for_music_lookup_tasks()

    db = db_client[TEST_DB_NAME]
    doc = await db["media"].find_one({"resource_path": resource_path})
    assert doc is not None
    assert doc["custom_metadata"]["music_lookup_status"] == "completed"
    assert doc["custom_metadata"]["music_info"]["title"] == "Test Song"


@pytest.mark.asyncio
async def test_identify_music_skips_not_found_without_force(client, db_client):
    """identify-music must not re-run fpcalc when status is already 'not_found'."""
    audio_content = b"\x00" * 512

    with patch("app.utils.music_lookup.identify_song", return_value=None):
        files = {"file": ("no_match.mp3", audio_content, "audio/mpeg")}
        response = await client.post("/media/upload", files=files)
        assert response.status_code == 201
        await media_routes.wait_for_music_lookup_tasks()

    resource_path = response.json()["resource_path"]

    # Without force, a second call must return early without rescheduling.
    call_count = 0

    async def counting_finalize(**kwargs):
        nonlocal call_count
        call_count += 1

    with patch(
        "app.routes.media._finalize_music_lookup",
        new=AsyncMock(side_effect=counting_finalize),
    ):
        response = await client.post(
            "/media/identify-music",
            params={"resource_path": resource_path},
        )
        assert response.status_code == 200

    assert (
        call_count == 0
    ), "identify_song must not be called again for a not_found audio"


@pytest.mark.asyncio
async def test_identify_music_not_audio(client, db_client):
    """POST /media/identify-music on a non-audio media should return 422."""
    image_content = b"PNG" * 512
    files = {"file": ("test.png", image_content, "image/png")}
    response = await client.post("/media/upload", files=files)
    assert response.status_code == 201
    resource_path = response.json()["resource_path"]

    response = await client.post(
        "/media/identify-music",
        params={"resource_path": resource_path},
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_image_upload_no_music_lookup(client, db_client):
    """Image uploads should not trigger music identification."""
    image_content = b"X" * 512
    files = {"file": ("no_music.png", image_content, "image/png")}
    response = await client.post("/media/upload", files=files)
    assert response.status_code == 201
    res = response.json()
    # Image uploads should have empty custom_metadata (no music_lookup_status)
    assert res["custom_metadata"] == {} or "music_lookup_status" not in (
        res["custom_metadata"] or {}
    )
