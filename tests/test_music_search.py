"""Tests for tagging music without an audio file: MusicBrainz search + yt-dlp download."""

import os
import tempfile
from unittest.mock import patch

import pytest

from backend.constants import MEDIA_PATH
from backend.database.querying import get_media_by_id
from backend.utils import music_lookup, youtube_audio
from backend.utils.music_media import wait_for_music_lookup_tasks

MB_SEARCH_RESPONSE = {
    "recording-list": [
        {
            "id": "rec-1",
            "title": "Song",
            "artist-credit-phrase": "Artist",
            "release-list": [
                {
                    "id": "rel-single",
                    "title": "Song (Single)",
                    "date": "2001-02-03",
                    "status": "Official",
                    "release-group": {"primary-type": "Single"},
                },
                {
                    "id": "rel-album",
                    "title": "The Album",
                    "date": "2002",
                    "status": "Official",
                    "release-group": {"primary-type": "Album"},
                },
            ],
        },
        # Duplicate recording of the same song - should be collapsed.
        {"id": "rec-2", "title": "song", "artist-credit-phrase": "artist"},
        {
            "id": "rec-3",
            "title": "Other",
            "artist-credit": [
                {"artist": {"name": "A"}, "joinphrase": " & "},
                {"artist": {"name": "B"}},
            ],
        },
    ]
}


def test_search_recordings_uses_fields_when_artist_given():
    with patch.object(
        music_lookup.musicbrainzngs, "search_recordings", return_value={}
    ) as mock:
        music_lookup.search_recordings("Song", "Artist", limit=5)
    mock.assert_called_once_with(recording="Song", artist="Artist", limit=20)


def test_search_recordings_respects_limit():
    with patch.object(
        music_lookup.musicbrainzngs, "search_recordings", return_value=MB_SEARCH_RESPONSE
    ):
        assert len(music_lookup.search_recordings("song", limit=1)) == 1


def test_search_recordings_parses_dedupes_and_prefers_album():
    with patch.object(
        music_lookup.musicbrainzngs, "search_recordings", return_value=MB_SEARCH_RESPONSE
    ):
        results = music_lookup.search_recordings("song")

    assert [r["mbid"] for r in results] == ["rec-1", "rec-3"]
    assert results[0] == {
        "title": "Song",
        "artist": "Artist",
        "album": "The Album",
        "year": "2002",
        "mbid": "rec-1",
        "release_mbid": "rel-album",
    }
    assert results[1]["artist"] == "A & B"
    assert results[1]["release_mbid"] is None


@pytest.mark.asyncio
async def test_search_endpoint(client):
    with patch.object(
        music_lookup.musicbrainzngs, "search_recordings", return_value=MB_SEARCH_RESPONSE
    ):
        resp = await client.get("/music/search", params={"q": "song"})
    assert resp.status_code == 200
    assert resp.json()[0]["album"] == "The Album"


@pytest.mark.asyncio
async def test_search_endpoint_reports_upstream_failure(client):
    with patch.object(
        music_lookup.musicbrainzngs, "search_recordings", side_effect=RuntimeError
    ):
        resp = await client.get("/music/search", params={"q": "song"})
    assert resp.status_code == 502


def _fake_download(query: str) -> dict:
    """Stand-in for yt-dlp: write a small file into a fresh temp dir, like the real one."""
    out_dir = tempfile.mkdtemp(prefix="codexj-test-ytdlp-")
    path = os.path.join(out_dir, "vid123.opus")
    with open(path, "wb") as f:
        f.write(b"OggS fake opus")
    _fake_download.last_query = query
    return {
        "path": path,
        "ext": "opus",
        "video_id": "vid123",
        "title": "Artist - Song (Official Audio)",
        "channel": "Artist",
        "duration": 200,
    }


@pytest.fixture
def ffmpeg_present():
    with patch.object(youtube_audio, "find_ffmpeg", return_value="/fake/ffmpeg"):
        yield


@pytest.mark.asyncio
async def test_download_returns_pending_then_completes(client, make_entry, ffmpeg_present):
    with (
        patch.object(youtube_audio, "download_top_audio", side_effect=_fake_download),
        patch.object(music_lookup, "fetch_cover_art_base64", return_value="Q09WRVI=") as cover,
        patch("backend.utils.music_media.start_music_lookup") as lookup,
    ):
        resp = await client.post(
            "/music/download",
            json={
                "entry_id": make_entry, "title": "Song", "artist": "Artist",
                "album": "The Album", "year": "2002", "mbid": "rec-1", "release_mbid": "rel-1",
            },
        )
        # Returned straight away, before the download ran
        assert resp.status_code == 202, resp.text
        data = resp.json()
        assert data["status"] == "pending"
        assert data["media_type"] == "audio"
        assert data["original_filename"] == "Artist - Song.opus"
        assert data["resource_path"].endswith(".opus")
        # Metadata is known immediately; cover arrives with the download
        assert data["custom_metadata"]["music_info"]["title"] == "Song"
        assert "cover_art_base64" not in data["custom_metadata"]["music_info"]

        await wait_for_music_lookup_tasks()

    assert _fake_download.last_query == "Artist Song"
    done = await client.get(f"/media/{data['id']}")
    final = done.json()
    assert final["status"] == "completed"
    # URL is unchanged, so what the editor inserted up front stays valid
    assert final["resource_path"] == data["resource_path"]
    assert final["file_size"] > 0
    meta = final["custom_metadata"]
    assert meta["music_lookup_status"] == "completed"
    assert meta["music_info"] == {
        "title": "Song", "artist": "Artist", "album": "The Album", "year": "2002",
        "mbid": "rec-1", "cover_art_base64": "Q09WRVI=",
    }
    assert meta["youtube"]["video_id"] == "vid123"
    cover.assert_called_once_with("rel-1")
    lookup.assert_not_called()

    media = get_media_by_id(data["id"])
    user_dir = data["resource_path"].split("/")[2]
    assert os.path.isfile(os.path.join(MEDIA_PATH, user_dir, media.stored_filename))


@pytest.mark.asyncio
async def test_download_without_metadata_fingerprints(client, make_entry, ffmpeg_present):
    with (
        patch.object(youtube_audio, "download_top_audio", side_effect=_fake_download),
        patch.object(music_lookup, "fetch_cover_art_base64") as cover,
        patch("backend.utils.music_media.start_music_lookup") as lookup,
    ):
        resp = await client.post(
            "/music/download", json={"entry_id": make_entry, "title": "Some Song"}
        )
        assert resp.status_code == 202, resp.text
        assert "music_info" not in resp.json()["custom_metadata"]
        await wait_for_music_lookup_tasks()

    assert _fake_download.last_query == "Some Song"
    lookup.assert_called_once()
    cover.assert_not_called()


@pytest.mark.asyncio
async def test_download_failure_marks_media_failed(client, make_entry, ffmpeg_present):
    with patch.object(
        youtube_audio, "download_top_audio",
        side_effect=youtube_audio.YoutubeAudioError("No YouTube results for that song"),
    ):
        resp = await client.post(
            "/music/download", json={"entry_id": make_entry, "title": "x"}
        )
        assert resp.status_code == 202
        await wait_for_music_lookup_tasks()

    final = (await client.get(f"/media/{resp.json()['id']}")).json()
    assert final["status"] == "failed"
    assert final["error_message"] == "No YouTube results for that song"


@pytest.mark.asyncio
async def test_download_requires_ffmpeg(client, make_entry):
    with (
        patch.object(youtube_audio, "find_ffmpeg", return_value=None),
        patch.object(youtube_audio, "download_top_audio") as dl,
    ):
        resp = await client.post(
            "/music/download", json={"entry_id": make_entry, "title": "x"}
        )
    assert resp.status_code == 503
    dl.assert_not_called()


@pytest.mark.asyncio
async def test_download_rejects_other_users_entry(alternate_user_client, make_entry):
    with patch.object(youtube_audio, "download_top_audio") as dl:
        resp = await alternate_user_client.post(
            "/music/download", json={"entry_id": make_entry, "title": "x"}
        )
    assert resp.status_code in (403, 404)
    dl.assert_not_called()


@pytest.mark.asyncio
async def test_download_unknown_entry(client):
    resp = await client.post(
        "/music/download",
        json={"entry_id": "00000000-0000-0000-0000-000000000000", "title": "x"},
    )
    assert resp.status_code == 404
