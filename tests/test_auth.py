import json
from datetime import datetime

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
from backend.models.data_management import DumpUser, UserDataDump
from backend.settings import ColorTheme
from backend.utils.auth import hash_secret
from backend.utils.common import utcnow
from backend.utils.data_management import derive_dump_key


@pytest_asyncio.fixture(scope="module")
async def clean_up_users():
    yield
    for username in [
        "test_user",
        "alternate-user",
        "test-user",
        "dump_user_roundtrip",
        "dump_user_missing_creds",
        "privileged_mode_user",
        "disable_privileged_user",
    ]:
        _delete_user_if_exists(username)


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
    assert user.theme == ColorTheme.light
    workspace_names = [ws.name for ws in get_workspaces_by_user_id(user.id)]
    assert "Workspace A" in workspace_names


@pytest.mark.asyncio
async def test_register_user_with_existing_username(client, clean_up_users):
    payload = {"username": "test_user", "password": "password123"}
    _delete_user_if_exists(payload["username"])
    # First, register the user
    await client.post("auth/register", json=payload)

    # Attempt to register the user again with the same username
    response = await client.post("auth/register", json=payload)
    assert response.status_code == 409
    data = response.json()
    assert data["detail"] == "Username already taken"


@pytest.mark.asyncio
async def test_login_user(client, clean_up_users):
    payload = {"username": "test_user", "password": "password123"}
    _delete_user_if_exists(payload["username"])
    # First, register the user
    await client.post("auth/register", json=payload)

    # Now, attempt to log in
    response = await client.post("auth/login", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["token_type"] == "bearer"
    assert "access_token" in data


@pytest.mark.asyncio
async def test_login_user_with_invalid_credentials(client, clean_up_users):
    payload = {"username": "test_user", "password": "wrong_password"}
    _delete_user_if_exists(payload["username"])
    # First, register the user with the correct password
    await client.post(
        "auth/register", json={"username": "test_user", "password": "password123"}
    )

    # Now, attempt to log in with the wrong password
    response = await client.post("auth/login", json=payload)
    assert response.status_code == 401
    data = response.json()
    assert data["detail"] == "Invalid username or password"


@pytest.mark.asyncio
async def test_login_user_with_nonexistent_username(client, clean_up_users):
    payload = {"username": "nonexistent_user", "password": "password123"}
    _delete_user_if_exists(payload["username"])

    response = await client.post("auth/login", json=payload)
    assert response.status_code == 401
    data = response.json()
    assert data["detail"] == "Invalid username or password"


@pytest.mark.asyncio
async def test_unlock_user(client, clean_up_users):
    payload = {"username": "test_user", "password": "password123"}
    _delete_user_if_exists(payload["username"])
    # First, register the user
    register_response = await client.post("auth/register", json=payload)
    hashkey = register_response.json().get("hashkey")
    payload = {"username": "test_user", "hashkey": hashkey}

    # Now, attempt to unlock the user
    response = await client.post("auth/unlock", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["token_type"] == "bearer"
    assert "access_token" in data


@pytest.mark.asyncio
async def test_unlock_user_with_invalid_credentials(client, clean_up_users):
    payload = {"username": "test_user", "password": "wrong_password"}
    _delete_user_if_exists(payload["username"])
    # First, register the user with the correct password
    await client.post(
        "auth/register", json={"username": "test_user", "password": "password123"}
    )
    payload = {"username": "test_user", "hashkey": "invalid hashkey"}

    # Now, attempt to unlock the user with the wrong haskey
    response = await client.post("auth/unlock", json=payload)
    assert response.status_code == 401
    data = response.json()
    assert data["detail"] == "Invalid username or hashkey"


@pytest.mark.asyncio
async def test_register_with_import_restores_dumped_credentials(client, clean_up_users):
    test_username = "dump_user_roundtrip"
    test_hashkey = "roundtrip_import_hashkey_abc123"
    test_user_id = 1732
    plain_password = "imported_password_123"

    user = DumpUser(
        id=test_user_id,
        username=test_username,
        password_hash=hash_secret(plain_password),
        hashkey_hash=hash_secret("legacy_hashkey"),
        dump_key=derive_dump_key(test_hashkey, test_username),
        theme=ColorTheme.light,
        created_at=datetime(2026, 2, 26, 0, 0, 0),
    )
    dump_data = UserDataDump(
        version="1.2",
        exported_at=datetime(2026, 3, 26, 0, 0, 0),
        user=user,
        workspaces=[],
        journals=[],
        entries=[],
        tags=[],
        media=[],
    )

    fernet_key = derive_dump_key(test_hashkey, test_username)
    payload_token = (
        Fernet(fernet_key.encode())
        .encrypt(dump_data.model_dump_json().encode())
        .decode()
    )
    wrapped_dump = json.dumps(
        {
            "meta": {"username": test_username, "version": "1.2"},
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
    test_hashkey = "missing_creds_hashkey_abc123"
    test_user_id = 17
    dump_data = UserDataDump(
        version="1.0",
        exported_at=datetime(2026, 3, 26, 0, 0, 0),
        user=DumpUser(
            id=test_user_id,
            username="missing_creds_user",
            password_hash=hash_secret("fixture_password_123"),
            hashkey_hash=hash_secret(test_hashkey),
            dump_key=derive_dump_key(test_hashkey, "missing_creds_user"),
            theme=ColorTheme.light,
            created_at=utcnow(),
        ),
        workspaces=[],
        journals=[],
        entries=[],
        tags=[],
        media=[],
    )
    fernet_key = derive_dump_key(test_hashkey, "missing_creds_user")
    payload_token = (
        Fernet(fernet_key.encode())
        .encrypt(dump_data.model_dump_json().encode())
        .decode()
    )
    wrapped_dump = json.dumps(
        {
            "meta": {"user_id": test_user_id, "version": "1.2"},
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
async def test_delete_user_requires_privileged_mode(client, clean_up_users):
    response = await client.delete("/auth/delete")
    assert response.status_code == 403
    assert "privileged mode required" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_delete_user_succeeds_in_privileged_mode(
    client, enable_privileged_mode, clean_up_users
):
    response = await client.delete("/auth/delete")
    assert response.status_code == 200
    assert "success" in response.json()["status"].lower()


@pytest.mark.asyncio
async def test_assert_workspace_owner(
    client, alternate_user_client, make_workspace, clean_up_users
):
    workspace_id = make_workspace
    response = await client.get("/workspaces")
    assert any(ws["id"] == workspace_id for ws in response.json())
    response = await alternate_user_client.get("/workspaces")
    assert not any(ws["id"] == workspace_id for ws in response.json())


@pytest.mark.asyncio
async def test_assert_journal_access(
    client, alternate_user_client, make_journal, clean_up_users
):
    journal_id = make_journal
    response = await client.get(f"/journals/{journal_id}/entries")
    assert response.status_code == 200
    response = await alternate_user_client.get(f"/journals/{journal_id}/entries")
    assert response.status_code == 403
