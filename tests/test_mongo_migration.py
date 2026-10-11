"""Tests for scripts/migrate_mongo_to_sqlite.py, using an in-memory fake of MongoDB."""

import importlib.util
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest
import pytest_asyncio

from backend.database.querying import (
    get_entries_by_journal_id,
    get_journals_by_workspace_id,
    get_media_by_entry_id,
    get_user_by_username,
    get_workspaces_by_user_id,
)
from backend.database.structural import Session
from backend.utils.data_management import derive_dump_key, recursive_delete_user

_SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "migrate_mongo_to_sqlite.py"
_spec = importlib.util.spec_from_file_location("migrate_mongo_to_sqlite", _SCRIPT)
migration = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(migration)

USERNAME = "mongo-migrated-user"
OLD_UID = "69fbb5d70d228ae79c71a1b3"
BASE = "http://localhost:8128/media"
HASHKEY = "mongo-era-hashkey-0123456789abcdef"
HASHKEY_HASH = migration._pwd_context.hash(HASHKEY)


class FakeCollection:
    def __init__(self, docs):
        self._docs = docs

    def find(self):
        return iter(self._docs)


class FakeMongo:
    def __init__(self, collections):
        self._collections = collections

    def __getitem__(self, name):
        return FakeCollection(self._collections.get(name, []))


def _mongo_dump():
    image_url = f"{BASE}/{OLD_UID}/img.png"
    audio_url = f"{BASE}/{OLD_UID}/song.mp3"
    page_url = f"{BASE}/{OLD_UID}/page.html"
    orphan_url = f"{BASE}/{OLD_UID}/orphan.png"
    body = {
        "ops": [
            {"insert": "Hello\n"},
            {"insert": {"image": image_url}},
            {"insert": {"audio": {"src": audio_url, "original_filename": "song.mp3"}}},
            {"insert": {"webpage": {"src": page_url, "source_url": "https://e.com", "title": "T", "status": "completed", "error_message": None}}},
            {"insert": "\n"},
        ]
    }

    def media(url, name, kind, **metadata):
        return {
            "_id": f"m-{name}",
            "user_id": OLD_UID,
            "resource_path": url,
            "stored_filename": name,
            "original_filename": name,
            "media_type": kind,
            "file_size": 12,
            "status": "completed",
            "error_message": None,
            "custom_metadata": metadata,
            "created_at": datetime(2026, 4, 1, 12, 0, 0),
        }

    return {
        "users": [
            {
                "_id": OLD_UID,
                "username": USERNAME,
                "password_hash": "ph",
                "hashkey_hash": HASHKEY_HASH,
                "dump_key": derive_dump_key(HASHKEY, OLD_UID),
                "theme": "dark",
            }
        ],
        "workspaces": [
            {"_id": "w1", "user_id": OLD_UID, "name": "WS", "created_at": "2026-04-04T19:33:18.434525Z"},
        ],
        "journals": [
            {"_id": "j1", "workspace_id": "w1", "name": "J", "description": None, "created_at": "2026-04-05T08:39:27.337000"},
        ],
        "entry_types": [
            {"_id": "t1", "user_id": OLD_UID, "workspace_id": "w1", "name": "mig-daily", "created_at": datetime(2026, 3, 1)},
            {"_id": "t2", "user_id": OLD_UID, "workspace_id": "w1", "name": "mig-daily", "created_at": datetime(2026, 2, 1)},
        ],
        "entries": [
            {
                "_id": "e1",
                "user_id": OLD_UID,
                "journal_id": "j1",
                "tags": ["mig-daily", "mig-from-entry-only"],
                "name": "First",
                "timezone": "Asia/Kolkata",
                "body": body,
                "custom_metadata": [{"key": "identify-audio", "value": "true"}],
                "media_refs": [image_url, audio_url, page_url],
                "date_created": "2026-03-27T18:18:03.214000",
                "updated_at": datetime(2026, 4, 18, 18, 34, 39),
                "is_deleted": False,
                "deleted_at": None,
                "deleted_from_workspace_id": None,
                "deleted_from_journal_id": None,
            }
        ],
        "media": [
            media(image_url, "img.png", "image"),
            media(
                audio_url,
                "song.mp3",
                "audio",
                music_lookup_status="completed",
                music_info={"title": "Enchanted", "artist": "Taylor Swift"},
            ),
            media(page_url, "page.html", "webpage", source_url="https://e.com"),
            media(orphan_url, "orphan.png", "image"),
        ],
    }


@pytest_asyncio.fixture(autouse=True)
async def cleanup_migrated_user():
    yield
    user = get_user_by_username(USERNAME)
    if user:
        await recursive_delete_user(user.id)


@pytest.fixture
def media_dirs(tmp_path):
    source, dest = tmp_path / "old", tmp_path / "new"
    (source / OLD_UID).mkdir(parents=True)
    (source / OLD_UID / "img.png").write_bytes(b"png")
    return source, dest


def _run(media_dirs, dump=None, hashkeys=None, **kwargs):
    source, dest = media_dirs
    with Session() as session:
        report = migration.migrate(
            FakeMongo(dump or _mongo_dump()),
            session,
            media_source=source,
            media_dest=dest,
            hashkeys={USERNAME: HASHKEY} if hashkeys is None else hashkeys,
            **kwargs,
        )
        if kwargs.get("dry_run"):
            session.rollback()
        else:
            session.commit()
    return report


def _dump_with_entry_links():
    """The base dump plus a second entry; the first links to it, to a missing entry and to the web."""
    dump = _mongo_dump()
    dump["entries"][0]["body"]["ops"] += [
        {"insert": "second", "attributes": {"link": "/entries/e2"}},
        {"insert": "gone", "attributes": {"link": "/entries/not-migrated"}},
        {"insert": "web", "attributes": {"link": "https://example.com/entries/e2"}},
    ]
    dump["entries"].append(
        {
            **{k: v for k, v in dump["entries"][0].items() if k != "body"},
            "_id": "e2",
            "name": "Second",
            "date_created": "2026-03-28T06:13:04.539000",
            "body": {"ops": [{"insert": "two\n"}]},
            "media_refs": [],
        }
    )
    return dump


def _migrated_entries():
    user = get_user_by_username(USERNAME)
    [workspace] = get_workspaces_by_user_id(user.id)
    [journal] = get_journals_by_workspace_id(workspace.id)
    return {e.name: e for e in get_entries_by_journal_id(journal.id)}


def _links(entry):
    return [
        op["attributes"]["link"]
        for op in json.loads(entry.body)["ops"]
        if "attributes" in op
    ]


def test_entry_links_are_remapped_to_new_ids(media_dirs):
    _run(media_dirs, dump=_dump_with_entry_links())

    entries = _migrated_entries()
    assert _links(entries["First"]) == [
        f"/entries/{entries['Second'].id}",
        "/entries/not-migrated",
        "https://example.com/entries/e2",
    ]



def test_migrates_hierarchy_with_new_uuid_ids(media_dirs):
    report = _run(media_dirs)

    user = get_user_by_username(USERNAME)
    assert user is not None and len(user.id) == 36 and user.id != OLD_UID
    assert (user.password_hash, user.hashkey_hash, user.theme) == (
        "ph",
        HASHKEY_HASH,
        "dark",
    )
    # The old key was salted with the Mongo id; the new one uses the username.
    assert user.dump_key == derive_dump_key(HASHKEY, USERNAME)
    assert user.dump_key != derive_dump_key(HASHKEY, OLD_UID)
    [workspace] = get_workspaces_by_user_id(user.id)
    assert workspace.name == "WS" and len(workspace.id) == 36
    # SQLite hands back naive datetimes; they hold the UTC values.
    assert workspace.created_at == datetime(2026, 4, 4, 19, 33, 18, 434525)
    [journal] = get_journals_by_workspace_id(workspace.id)
    assert journal.name == "J" and journal.description is None
    [entry] = get_entries_by_journal_id(journal.id)
    assert entry.name == "First" and entry.timezone == "Asia/Kolkata"
    assert (report.users, report.workspaces, report.journals, report.entries) == (1, 1, 1, 1)


def test_entry_bodies_use_new_user_id_and_media_ids(media_dirs):
    _run(media_dirs)

    user = get_user_by_username(USERNAME)
    [workspace] = get_workspaces_by_user_id(user.id)
    [journal] = get_journals_by_workspace_id(workspace.id)
    [entry] = get_entries_by_journal_id(journal.id)
    body = json.loads(entry.body)
    media_by_name = {m.stored_filename: m for m in get_media_by_entry_id(entry.id)}

    image = body["ops"][1]["insert"]["image"]
    audio = body["ops"][2]["insert"]["audio"]
    page = body["ops"][3]["insert"]["webpage"]
    assert image == f"{migration.MEDIA_URL_PREFIX}/{user.id}/img.png"
    assert audio["src"] == f"{migration.MEDIA_URL_PREFIX}/{user.id}/song.mp3"
    assert audio["media_id"] == media_by_name["song.mp3"].id
    assert page["media_id"] == media_by_name["page.html"].id
    assert OLD_UID not in entry.body
    assert json.loads(entry.media_refs) == [image, audio["src"], page["src"]]
    assert json.loads(entry.custom_metadata) == [{"key": "identify-audio", "value": "true"}]
    assert entry.date_created == datetime(2026, 3, 27, 18, 18, 3, 214000)
    assert entry.updated_at == datetime(2026, 4, 18, 18, 34, 39)


def test_media_records_files_and_orphans(media_dirs):
    source, dest = media_dirs
    report = _run(media_dirs)

    user = get_user_by_username(USERNAME)
    [workspace] = get_workspaces_by_user_id(user.id)
    [journal] = get_journals_by_workspace_id(workspace.id)
    [entry] = get_entries_by_journal_id(journal.id)
    media = {m.stored_filename: m for m in get_media_by_entry_id(entry.id)}

    # The orphan (no entry references it) is skipped; the rest are kept.
    assert set(media) == {"img.png", "song.mp3", "page.html"}
    assert report.media == 3
    assert json.loads(media["song.mp3"].custom_metadata)["music_info"]["title"] == "Enchanted"

    # Only the file that exists is copied, into the new user's folder.
    assert (dest / user.id / "img.png").read_bytes() == b"png"
    assert report.media_files_copied == 1
    assert report.media_files_missing == 2
    assert not (dest / user.id / "song.mp3").exists()
    assert (source / OLD_UID / "img.png").exists()


def test_tags_are_global_and_unique(media_dirs):
    from backend.database.querying import get_all_tags

    _run(media_dirs)

    tags = {t.name: t for t in get_all_tags()}
    assert {"mig-daily", "mig-from-entry-only"} <= set(tags)
    # The earliest entry_type timestamp wins for a name that appears twice.
    assert tags["mig-daily"].created_at.replace(tzinfo=None) == datetime(2026, 2, 1)


def test_skip_missing_media(media_dirs):
    report = _run(media_dirs, skip_missing_media=True)

    user = get_user_by_username(USERNAME)
    [workspace] = get_workspaces_by_user_id(user.id)
    [journal] = get_journals_by_workspace_id(workspace.id)
    [entry] = get_entries_by_journal_id(journal.id)
    assert [m.stored_filename for m in get_media_by_entry_id(entry.id)] == ["img.png"]
    assert report.media == 1


def test_dry_run_changes_nothing(media_dirs):
    _, dest = media_dirs
    report = _run(media_dirs, dry_run=True)

    assert get_user_by_username(USERNAME) is None
    assert not dest.exists()
    assert (report.entries, report.media, report.media_files_copied) == (1, 3, 1)


def test_refuses_wrong_or_missing_hashkey(media_dirs):
    for hashkeys in ({USERNAME: "wrong"}, {}):
        with pytest.raises(migration.MigrationError, match="hashkey"):
            _run(media_dirs, hashkeys=hashkeys)
    assert get_user_by_username(USERNAME) is None


def test_refuses_to_merge_into_existing_user(media_dirs):
    _run(media_dirs)
    with pytest.raises(migration.MigrationError, match="already exists"):
        _run(media_dirs)


def _fake_terminal(monkeypatch, answers, interactive=True):
    monkeypatch.setattr(migration.sys.stdin, "isatty", lambda: interactive)
    replies = iter(answers)
    monkeypatch.setattr("builtins.input", lambda _prompt="": next(replies))


def test_prompt_returns_default_when_not_interactive(monkeypatch, tmp_path):
    _fake_terminal(monkeypatch, [], interactive=False)
    assert migration._prompt_media_source(tmp_path) == tmp_path


def test_prompt_enter_accepts_default(monkeypatch, tmp_path):
    _fake_terminal(monkeypatch, [""])
    assert migration._prompt_media_source(tmp_path) == tmp_path


def test_prompt_accepts_typed_and_quoted_paths(monkeypatch, tmp_path):
    folder = tmp_path / "old media"
    folder.mkdir()
    _fake_terminal(monkeypatch, [f'"{folder}"'])
    assert migration._prompt_media_source(tmp_path) == folder


def test_prompt_rejects_relative_paths(monkeypatch, tmp_path):
    folder = tmp_path / "real"
    folder.mkdir()
    _fake_terminal(monkeypatch, ["media", "..\\old-media", str(folder)])
    assert migration._prompt_media_source(tmp_path) == folder


def test_prompt_reasks_for_missing_folder(monkeypatch, tmp_path):
    folder = tmp_path / "real"
    folder.mkdir()
    _fake_terminal(monkeypatch, [str(tmp_path / "nope"), "n", str(folder)])
    assert migration._prompt_media_source(tmp_path) == folder


def test_prompt_can_continue_with_missing_folder(monkeypatch, tmp_path):
    missing = tmp_path / "nope"
    _fake_terminal(monkeypatch, [str(missing), "y"])
    assert migration._prompt_media_source(tmp_path) == missing


def test_date_normalisation():
    naive = migration._dt(datetime(2026, 1, 2, 3, 4, 5))
    assert naive == datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc)
    assert migration._dt("2026-04-04T19:33:18.434525Z").tzinfo is not None
    assert migration._dt("2026-03-27T18:18:03.214000") == datetime(
        2026, 3, 27, 18, 18, 3, 214000, tzinfo=timezone.utc
    )
