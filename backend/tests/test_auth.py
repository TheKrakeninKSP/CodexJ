import json

import pytest
import pytest_asyncio
from app.database import get_db_no_deps
from app.main import app
from app.utils.auth import decode_token, hash_secret
from app.utils.data_management import encrypt_data
from tests.conftest import TEST_DB_NAME


# test registration with valid data
@pytest.mark.asyncio
async def test_register_user(client, clean_up_users):
    payload = {"username": "test_user", "password": "password123"}
    response = await client.post("auth/register", json=payload)
    assert response.status_code == 201
    data = response.json()
    assert data["username"] == payload["username"]
    assert data["token_type"] == "bearer"
    assert "access_token" in data
    assert "hashkey" in data

    # verify default workspace creation
    db = get_db_no_deps(TEST_DB_NAME)
    users = db["users"]
    user = await users.find_one({"username": payload["username"]})
    if not user:
        assert False, "User not found in database after registration"
    user_id = str(user["_id"])
    workspaces = db["workspaces"]
    ws_data = await workspaces.find({"user_id": user_id}).to_list()
    for ws in ws_data:
        if ws["user_id"] == user_id and ws["name"] == "Workspace A":
            break
    else:
        assert False, "Default workspace not found for new user"


@pytest_asyncio.fixture(scope="module")
async def clean_up_users():
    yield
    db = get_db_no_deps(TEST_DB_NAME)
    await db["users"].delete_many(
        {
            "username": {
                "$in": [
                    "test_user",
                    "dump_user_roundtrip",
                    "dump_user_missing_creds",
                    "privileged_mode_user",
                    "disable_privileged_user",
                ]
            }
        }
    )


@pytest.mark.asyncio
async def test_register_with_import_restores_dumped_credentials(client, clean_up_users):
    encryption_key = "roundtrip_import_key"
    plain_password = "imported_password_123"

    dump = {
        "version": "1.0",
        "exported_at": "2026-03-26T00:00:00Z",
        "user_id": "legacy-user-id",
        "username": "dump_user_roundtrip",
        "password_hash": hash_secret(plain_password),
        "hashkey_hash": hash_secret("legacy_hashkey"),
        "workspaces": [],
        "journals": [],
        "entries": [],
        "entry_types": [],
        "media": [],
    }
    encrypted_dump = encrypt_data(json.dumps(dump), encryption_key)

    import_res = await client.post(
        "/auth/register-with-import",
        data={"encryption_key": encryption_key},
        files={"file": ("dump.bin", encrypted_dump, "application/octet-stream")},
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
    encryption_key = "missing_creds_key"
    dump = {
        "version": "1.0",
        "exported_at": "2026-03-26T00:00:00Z",
        "user_id": "legacy-user-id",
        "workspaces": [],
        "journals": [],
        "entries": [],
        "entry_types": [],
        "media": [],
    }
    encrypted_dump = encrypt_data(json.dumps(dump), encryption_key)

    import_res = await client.post(
        "/auth/register-with-import",
        data={"encryption_key": encryption_key},
        files={"file": ("dump.bin", encrypted_dump, "application/octet-stream")},
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

    payload = decode_token(privileged_res.json()["access_token"])
    assert payload.get("is_privileged") is True


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

    payload = decode_token(disable_res.json()["access_token"])
    assert payload.get("is_privileged") is None


@pytest.mark.asyncio
async def test_delete_user_requires_privileged_mode(unprivileged_client):
    response = await unprivileged_client.delete("/auth/delete")
    assert response.status_code == 403
    assert "privileged mode required" in response.json()["detail"].lower()
