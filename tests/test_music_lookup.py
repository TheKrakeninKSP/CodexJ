"""Tests for music identification (AcoustID → MusicBrainz) pipeline."""

import os
import shutil
from unittest.mock import AsyncMock, patch

import pytest

from backend.constants import MEDIA_PATH
from backend.database.querying import (
    delete_media_by_id,
    get_media_by_user_id,
    get_user_by_username,
)
from backend.utils.music_media import wait_for_music_lookup_tasks
from tests.conftest import FIXTURE_USERNAME


@pytest.fixture(autouse=True, scope="module")
def setup_music_test_environment():
    yield
    user = get_user_by_username(FIXTURE_USERNAME)
    if user is not None:
        media_dir = os.path.join(MEDIA_PATH, str(user.id))
        if os.path.exists(media_dir):
            shutil.rmtree(media_dir)


@pytest.fixture(autouse=True, scope="function")
def cleanup_media_db_records():
    yield
    user = get_user_by_username(FIXTURE_USERNAME)
    for media in get_media_by_user_id(user.id) if user is not None else []:
        delete_media_by_id(media.id)


MOCK_MUSIC_INFO = {
    "title": "Test Song",
    "artist": "Test Artist",
    "album": "Test Album",
    "year": "2024",
    "mbid": "12345678-1234-1234-1234-123456789abc",
    "cover_art_base64": "dGVzdA==",  # base64 of "test"
}


async def _upload_audio(client, entry_id, filename="song.mp3", size=1024):
    """Upload audio and let the lookup it schedules finish."""
    response = await client.post(
        "/media/upload",
        data={"entry_id": entry_id},
        files={"file": (filename, b"\x00" * size, "audio/mpeg")},
    )
    assert response.status_code == 201
    await wait_for_music_lookup_tasks()
    return response.json()


async def _identify(client, media_id, *, force=True):
    return await client.post(
        f"/media/{media_id}/identify-music",
        params={"force": "true"} if force else {},
    )


async def _get_metadata(client, media_id):
    response = await client.get(f"/media/{media_id}")
    assert response.status_code == 200
    return response.json()["custom_metadata"]


@pytest.mark.asyncio
async def test_audio_upload_triggers_music_lookup(client, make_entry):
    """Audio upload should set music_lookup_status to pending and schedule a lookup."""
    with patch(
        "backend.utils.music_media._finalize_music_lookup",
        new=AsyncMock(return_value=None),
    ) as finalize:
        media = await _upload_audio(client, make_entry)
        await wait_for_music_lookup_tasks()

    assert media["media_type"] == "audio"
    assert media["custom_metadata"]["music_lookup_status"] == "pending"
    finalize.assert_called_once()
    assert (await _get_metadata(client, media["id"]))[
        "music_lookup_status"
    ] == "pending"


@pytest.mark.asyncio
async def test_audio_upload_with_successful_identification(client, make_entry):
    """The lookup scheduled by an upload populates custom_metadata when it matches."""
    with patch(
        "backend.utils.music_lookup.identify_song", return_value=MOCK_MUSIC_INFO
    ):
        media = await _upload_audio(client, make_entry)
        await wait_for_music_lookup_tasks()

    metadata = await _get_metadata(client, media["id"])
    assert metadata["music_lookup_status"] == "completed"
    assert metadata["music_info"] == MOCK_MUSIC_INFO


@pytest.mark.asyncio
async def test_identify_music_successful_identification(client, make_entry):
    """When identify_song returns data, custom_metadata should be populated."""
    media = await _upload_audio(client, make_entry)

    with patch(
        "backend.utils.music_lookup.identify_song", return_value=MOCK_MUSIC_INFO
    ):
        response = await _identify(client, media["id"])
        assert response.status_code == 200
        assert response.json()["custom_metadata"]["music_lookup_status"] == "pending"
        await wait_for_music_lookup_tasks()

    metadata = await _get_metadata(client, media["id"])
    assert metadata["music_lookup_status"] == "completed"
    assert metadata["music_info"] == MOCK_MUSIC_INFO


@pytest.mark.asyncio
async def test_identify_music_no_match(client, make_entry):
    """When identify_song returns None, status should be not_found."""
    media = await _upload_audio(client, make_entry)

    with patch("backend.utils.music_lookup.identify_song", return_value=None):
        response = await _identify(client, media["id"])
        assert response.status_code == 200
        await wait_for_music_lookup_tasks()

    metadata = await _get_metadata(client, media["id"])
    assert metadata["music_lookup_status"] == "not_found"
    assert "music_info" not in metadata


@pytest.mark.asyncio
async def test_identify_music_identification_error(client, make_entry):
    """When identify_song raises an exception, status should be failed."""
    media = await _upload_audio(client, make_entry)

    with patch(
        "backend.utils.music_lookup.identify_song",
        side_effect=RuntimeError("fpcalc not found"),
    ):
        response = await _identify(client, media["id"])
        assert response.status_code == 200
        await wait_for_music_lookup_tasks()

    metadata = await _get_metadata(client, media["id"])
    assert metadata["music_lookup_status"] == "failed"


@pytest.mark.asyncio
async def test_identify_music_force_reidentifies_not_found(client, make_entry):
    """force=true re-runs the lookup after a previous 'not_found' result."""
    media = await _upload_audio(client, make_entry)

    with patch("backend.utils.music_lookup.identify_song", return_value=None):
        await _identify(client, media["id"])
        await wait_for_music_lookup_tasks()
    assert (await _get_metadata(client, media["id"]))[
        "music_lookup_status"
    ] == "not_found"

    with patch(
        "backend.utils.music_lookup.identify_song", return_value=MOCK_MUSIC_INFO
    ):
        response = await _identify(client, media["id"])
        assert response.status_code == 200
        await wait_for_music_lookup_tasks()

    metadata = await _get_metadata(client, media["id"])
    assert metadata["music_lookup_status"] == "completed"
    assert metadata["music_info"]["title"] == "Test Song"


@pytest.mark.asyncio
async def test_identify_music_skips_not_found_without_force(client, make_entry):
    """identify-music must not re-run the lookup when status is already 'not_found'."""
    media = await _upload_audio(client, make_entry)
    assert (await _get_metadata(client, media["id"]))[
        "music_lookup_status"
    ] == "not_found"

    finalize = AsyncMock(return_value=None)
    with patch("backend.utils.music_media._finalize_music_lookup", new=finalize):
        response = await _identify(client, media["id"], force=False)
        await wait_for_music_lookup_tasks()

    assert response.status_code == 200
    assert response.json()["custom_metadata"]["music_lookup_status"] == "not_found"
    finalize.assert_not_called()


@pytest.mark.asyncio
async def test_identify_music_not_audio(client, make_entry):
    """identify-music on non-audio media should return 422."""
    response = await client.post(
        "/media/upload",
        data={"entry_id": make_entry},
        files={"file": ("test.png", b"PNG" * 512, "image/png")},
    )
    assert response.status_code == 201

    response = await _identify(client, response.json()["id"])
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_identify_music_unknown_media(client, make_invalid_id):
    response = await _identify(client, make_invalid_id)
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_image_upload_no_music_lookup(client, make_entry):
    """Image uploads should not trigger music identification."""
    response = await client.post(
        "/media/upload",
        data={"entry_id": make_entry},
        files={"file": ("no_music.png", b"X" * 512, "image/png")},
    )
    assert response.status_code == 201
    assert "music_lookup_status" not in (response.json()["custom_metadata"] or {})
