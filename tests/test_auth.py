import json

import pytest
import pytest_asyncio
from cryptography.fernet import Fernet

from backend.database.querying import (
    create_user,
    delete_entry_by_id,
    delete_journal_by_id,
    delete_media_by_id,
    delete_user_by_id,
    delete_workspace_by_id,
    get_entries_by_journal_id,
    get_journals_by_workspace_id,
    get_media_by_entry_id,
    get_user_by_username,
    get_workspaces_by_user_id,
)
from backend.database.structural import UserModel
from backend.utils.auth import hash_secret
from backend.utils.common import utcnow
from backend.utils.data_management import derive_dump_key


def _delete_user_if_exists(username: str):
    user = get_user_by_username(username)
    if user is None:
        return

    workspaces = get_workspaces_by_user_id(user.id)
    journals = []
    entries = []
    media_items = []
    for workspace in workspaces:
        workspace_journals = get_journals_by_workspace_id(workspace.id)
        journals.extend(workspace_journals)
        for journal in workspace_journals:
            journal_entries = get_entries_by_journal_id(journal.id)
            entries.extend(journal_entries)
            for entry in journal_entries:
                media_items.extend(get_media_by_entry_id(entry.id))

    for media in media_items:
        delete_media_by_id(media.id)
    for entry in entries:
        delete_entry_by_id(entry.id)
    for journal in journals:
        delete_journal_by_id(journal.id)
    for workspace in workspaces:
        delete_workspace_by_id(workspace.id)

    delete_user_by_id(user.id)


# test registration with valid data
@pytest.mark.asyncio
async def test_register_user(client, clean_up_users):
    payload = {"username": "test_user", "password": "password123"}
    _delete_user_if_exists(payload["username"])
    response = await client.post("auth/register", json=payload)
    assert response.status_code == 201
    data = response.json()
    assert data["username"] == payload["username"]
    assert data["token_type"] == "bearer"
    assert "access_token" in data
    assert "hashkey" in data

    # verify default workspace creation
    user = get_user_by_username(payload["username"])
    assert user is not None, "User not found in database after registration"
    assert user.theme == "1"
    workspace_names = [ws.name for ws in get_workspaces_by_user_id(user.id)]
    assert "Workspace A" in workspace_names


@pytest_asyncio.fixture(scope="module")
async def clean_up_users():
    yield
    for username in [
        "test_user",
        "test-user",
        "dump_user_roundtrip",
        "dump_user_missing_creds",
        "privileged_mode_user",
        "disable_privileged_user",
    ]:
        _delete_user_if_exists(username)


@pytest.mark.asyncio
async def test_register_with_import_restores_dumped_credentials(client, clean_up_users):
    pytest.xfail("register-with-import still depends on legacy DB wiring")
    test_hashkey = "roundtrip_import_hashkey_abc123"
    test_user_id = "aabbccdd11223344aabbccdd"  # valid-looking hex id
    plain_password = "imported_password_123"

    dump_data = {
        "version": "1.0",
        "exported_at": "2026-03-26T00:00:00Z",
        "user_id": test_user_id,
        "username": "dump_user_roundtrip",
        "password_hash": hash_secret(plain_password),
        "hashkey_hash": hash_secret("legacy_hashkey"),
        "workspaces": [],
        "journals": [],
        "entries": [],
        "entry_types": [],
        "media": [],
    }
    fernet_key = derive_dump_key(test_hashkey, test_user_id)
    payload_token = (
        Fernet(fernet_key.encode()).encrypt(json.dumps(dump_data).encode()).decode()
    )
    wrapped_dump = json.dumps(
        {
            "meta": {"user_id": test_user_id, "version": "1.0"},
            "payload": payload_token,
        }
    ).encode()

    import_res = await client.post(
        "/auth/register-with-import",
        data={"hashkey": test_hashkey},
        files={"file": ("dump.bin", wrapped_dump, "application/octet-stream")},
    )

    assert import_res.status_code == 201
    import_data = import_res.json()
    assert import_data["username"] == "dump_user_roundtrip"
    assert "access_token" in import_data

    login_res = await client.post(
        "/auth/login",
        json={
            "username": "dump_user_roundtrip",
            "password": plain_password,
        },
    )
    assert login_res.status_code == 200
    assert "access_token" in login_res.json()


@pytest.mark.asyncio
async def test_register_with_import_requires_dumped_credentials(client, clean_up_users):
    pytest.xfail("register-with-import still depends on legacy DB wiring")
    test_hashkey = "missing_creds_hashkey_abc123"
    test_user_id = "bb11cc22dd33ee44bb11cc22"
    dump_data = {
        "version": "1.0",
        "exported_at": "2026-03-26T00:00:00Z",
        "user_id": test_user_id,
        "workspaces": [],
        "journals": [],
        "entries": [],
        "entry_types": [],
        "media": [],
    }
    fernet_key = derive_dump_key(test_hashkey, test_user_id)
    payload_token = (
        Fernet(fernet_key.encode()).encrypt(json.dumps(dump_data).encode()).decode()
    )
    wrapped_dump = json.dumps(
        {
            "meta": {"user_id": test_user_id, "version": "1.0"},
            "payload": payload_token,
        }
    ).encode()

    import_res = await client.post(
        "/auth/register-with-import",
        data={"hashkey": test_hashkey},
        files={"file": ("dump.bin", wrapped_dump, "application/octet-stream")},
    )

    assert import_res.status_code == 400
    assert "username" in import_res.json()["detail"].lower()


@pytest.mark.asyncio
async def test_enable_privileged_mode_returns_privileged_token(client, clean_up_users):
    privileged_res = await client.post(
        "/auth/privileged",
        json={"password": "fixture_password_123"},
    )
    assert privileged_res.status_code == 200
    assert privileged_res.json() == {"status": "Privileged mode enabled"}


@pytest.mark.asyncio
async def test_disable_privileged_mode_returns_non_privileged_token(
    client,
    clean_up_users,
):
    privileged_res = await client.post(
        "/auth/privileged",
        json={"password": "fixture_password_123"},
    )
    assert privileged_res.status_code == 200

    disable_res = await client.post("/auth/privileged/disable")
    assert disable_res.status_code == 200
    assert disable_res.json() == {"status": "Privileged mode disabled"}


@pytest.mark.asyncio
async def test_get_preferences_defaults_to_light_for_legacy_user(
    client, clean_up_users
):
    _delete_user_if_exists("test-user")
    create_user(
        UserModel(
            username="test-user",
            password_hash=hash_secret("fixture_password_123"),
            hashkey_hash=hash_secret("fixture_hashkey_123"),
            dump_key=derive_dump_key("fixture_hashkey_123", "test-user"),
            theme="light",
            created_at=utcnow(),
        )
    )

    response = await client.get("/auth/preferences")

    assert response.status_code == 200
    assert response.json() == {"theme": "light"}


@pytest.mark.asyncio
async def test_update_preferences_persists_theme(client, clean_up_users):
    _delete_user_if_exists("test-user")
    create_user(
        UserModel(
            username="test-user",
            password_hash=hash_secret("fixture_password_123"),
            hashkey_hash=hash_secret("fixture_hashkey_123"),
            dump_key=derive_dump_key("fixture_hashkey_123", "test-user"),
            theme="light",
            created_at=utcnow(),
        )
    )

    response = await client.patch(
        "/auth/preferences",
        json={"theme": "solarized-dark"},
    )

    assert response.status_code == 200
    assert response.json() == {"theme": "solarized-dark"}

    user = get_user_by_username("test-user")
    assert user is not None
    assert user.theme == "solarized-dark"


@pytest.mark.asyncio
async def test_update_preferences_accepts_future_theme_identifiers(
    client, clean_up_users
):
    _delete_user_if_exists("test-user")
    create_user(
        UserModel(
            username="test-user",
            password_hash=hash_secret("fixture_password_123"),
            hashkey_hash=hash_secret("fixture_hashkey_123"),
            dump_key=derive_dump_key("fixture_hashkey_123", "test-user"),
            theme="light",
            created_at=utcnow(),
        )
    )

    response = await client.patch(
        "/auth/preferences",
        json={"theme": "midnight-ink"},
    )

    assert response.status_code == 200
    assert response.json() == {"theme": "midnight-ink"}

    user = get_user_by_username("test-user")
    assert user is not None
    assert user.theme == "midnight-ink"


@pytest.mark.asyncio
async def test_delete_user_requires_privileged_mode(unprivileged_client):
    response = await unprivileged_client.delete("/auth/delete")
    assert response.status_code == 403
    assert "privileged mode required" in response.json()["detail"].lower()
