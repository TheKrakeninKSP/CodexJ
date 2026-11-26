import pytest
import pytest_asyncio

import backend.routes.admin as admin_routes
from backend.admin import main as admin_cli
from backend.database.querying import (
    delete_user_by_id,
    get_user_by_username,
    set_user_admin,
)
from backend.database.structural import UserModel

from .conftest import FIXTURE_USERNAME, _ensure_fixture_user


@pytest_asyncio.fixture
async def as_admin():
    _ensure_fixture_user()
    set_user_admin(FIXTURE_USERNAME, True)
    yield
    set_user_admin(FIXTURE_USERNAME, False)


@pytest.fixture
def media_root(tmp_path, monkeypatch):
    """Point per-user media lookups at a temp dir so tests never touch media/."""
    monkeypatch.setattr(
        admin_routes, "get_user_media_path", lambda user_id: tmp_path / str(user_id)
    )
    return tmp_path


@pytest.mark.asyncio
async def test_overview_requires_admin(client):
    response = await client.get("/admin/overview")
    assert response.status_code == 403
    assert response.json()["detail"] == "Admin access required"


@pytest.mark.asyncio
async def test_overview_reports_users_and_storage(
    client, as_admin, media_root, make_entry
):
    user = _ensure_fixture_user()
    user_dir = media_root / user.id
    (user_dir / "nested").mkdir(parents=True)
    (user_dir / "a.png").write_bytes(b"x" * 100)
    (user_dir / "nested" / "b.mp3").write_bytes(b"y" * 50)

    response = await client.get("/admin/overview")
    assert response.status_code == 200
    data = response.json()

    assert data["user_count"] == len(data["users"]) >= 1
    me = next(u for u in data["users"] if u["username"] == FIXTURE_USERNAME)
    assert me["is_admin"] is True
    assert me["media_files"] == 2
    assert me["media_bytes"] == 150
    assert me["entry_count"] >= 1
    assert me["text_bytes"] > 0
    assert me["total_bytes"] == me["media_bytes"] + me["text_bytes"]
    assert data["total_bytes"] == sum(u["total_bytes"] for u in data["users"])


@pytest.mark.asyncio
async def test_overview_user_without_media_dir(client, as_admin, media_root):
    response = await client.get("/admin/overview")
    assert response.status_code == 200
    me = next(
        u for u in response.json()["users"] if u["username"] == FIXTURE_USERNAME
    )
    assert me["media_files"] == 0
    assert me["media_bytes"] == 0


@pytest.mark.asyncio
async def test_me_reports_admin_flag(client, as_admin):
    response = await client.get("/auth/me")
    assert response.status_code == 200
    assert response.json() == {"username": FIXTURE_USERNAME, "is_admin": True}


@pytest.mark.asyncio
async def test_me_non_admin(client):
    response = await client.get("/auth/me")
    assert response.json()["is_admin"] is False


@pytest.mark.asyncio
async def test_login_records_last_login(client):
    payload = {"username": "admin_login_user", "password": "password123"}
    existing = get_user_by_username(payload["username"])
    if existing:
        delete_user_by_id(existing.id)
    try:
        await client.post("auth/register", json=payload)
        after_register = get_user_by_username(payload["username"])
        assert after_register is not None
        assert after_register.last_login_at is not None

        response = await client.post("auth/login", json=payload)
        assert response.status_code == 200
        after_login = get_user_by_username(payload["username"])
        assert after_login is not None and after_login.last_login_at is not None
        assert after_login.last_login_at >= after_register.last_login_at
    finally:
        user = get_user_by_username(payload["username"])
        if user:
            from backend.utils.data_management import recursive_delete_user

            await recursive_delete_user(user.id)


@pytest.fixture
def no_cli_migrations(monkeypatch):
    # The test DB is already at head; alembic's env.py leaves an engine open
    # that would block conftest from deleting the DB file on Windows.
    monkeypatch.setattr("backend.admin.run_migrations", lambda: None)


def test_cli_promote_and_demote(capsys, no_cli_migrations):
    _ensure_fixture_user()
    try:
        assert admin_cli(["promote", FIXTURE_USERNAME]) == 0
        user = get_user_by_username(FIXTURE_USERNAME)
        assert isinstance(user, UserModel) and user.is_admin is True

        assert admin_cli(["list"]) == 0
        assert f"admin  {FIXTURE_USERNAME}" in capsys.readouterr().out

        assert admin_cli(["demote", FIXTURE_USERNAME]) == 0
        user = get_user_by_username(FIXTURE_USERNAME)
        assert user is not None and user.is_admin is False
    finally:
        set_user_admin(FIXTURE_USERNAME, False)


def test_cli_unknown_user(capsys, no_cli_migrations):
    assert admin_cli(["promote", "no-such-user-xyz"]) == 1
    assert "No such user" in capsys.readouterr().err
