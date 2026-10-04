import os

import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from backend.models.workspace import WorkspaceCreate

os.environ.setdefault("JWT_SECRET", "test-secret-key")
os.environ.setdefault("JWT_ALGORITHM", "HS256")
os.environ.setdefault("JWT_EXPIRE_DAYS", "7")
TEST_DB_NAME = os.getenv("TEST_DB_NAME", "codexj-test")
import backend.constants

backend.constants.SQLITE_DB_URL = f"sqlite:///{TEST_DB_NAME}.db"

from backend.database.querying import delete_workspace_by_id, get_user_by_username
from backend.database.structural import (
    Session,
    UserModel,
    init_db,
)
from backend.main import app
from backend.routes import media as media_routes
from backend.utils.auth import get_current_user, hash_secret, set_privileged_mode
from backend.utils.common import utcnow
from backend.utils.data_management import derive_dump_key

# Known test credentials so roundtrip export/import tests can derive the correct dump key.
FIXTURE_USER_ID = "test-user-id"
FIXTURE_HASHKEY = "fixture_hashkey_123"
FIXTURE_USERNAME = "test-user"
FIXTURE_DUMP_KEY = derive_dump_key(FIXTURE_HASHKEY, FIXTURE_USERNAME)
set_privileged_mode(False)


def _ensure_fixture_user() -> UserModel:
    user = get_user_by_username(FIXTURE_USERNAME)
    if user is not None:
        return user

    with Session() as session:
        user = UserModel(
            username=FIXTURE_USERNAME,
            password_hash=hash_secret("fixture_password_123"),
            hashkey_hash=hash_secret(FIXTURE_HASHKEY),
            dump_key=FIXTURE_DUMP_KEY,
            theme="light",
            created_at=utcnow(),
        )
        session.add(user)
        session.commit()
        session.refresh(user)
        return user


def _ensure_alternate_fixture_user() -> UserModel:
    user = get_user_by_username("alternate-" + FIXTURE_USERNAME)
    if user is not None:
        return user

    with Session() as session:
        user = UserModel(
            username="alternate-" + FIXTURE_USERNAME,
            password_hash=hash_secret("fixture_password_123"),
            hashkey_hash=hash_secret(FIXTURE_HASHKEY),
            dump_key=FIXTURE_DUMP_KEY,
            theme="light",
            created_at=utcnow(),
        )
        session.add(user)
        session.commit()
        session.refresh(user)
        return user


@pytest_asyncio.fixture
async def client():
    app.dependency_overrides[get_current_user] = _ensure_fixture_user

    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://localhost") as c:
        yield c

    await media_routes.wait_for_webpage_archive_tasks()
    await media_routes.wait_for_music_lookup_tasks()
    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def alternate_user_client():
    app.dependency_overrides[get_current_user] = _ensure_alternate_fixture_user

    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://localhost") as c:
        yield c

    await media_routes.wait_for_webpage_archive_tasks()
    await media_routes.wait_for_music_lookup_tasks()
    app.dependency_overrides.clear()


@pytest_asyncio.fixture()
async def make_workspace(client):
    ws_payload = WorkspaceCreate(name="Test Workspace").model_dump()
    ws_res = await client.post("/workspaces", json=ws_payload)
    assert ws_res.status_code == 201
    workspace_id = ws_res.json()["id"]
    yield workspace_id
    delete_workspace_by_id(workspace_id)


@pytest_asyncio.fixture()
async def make_alternate_workspace(client):
    ws_payload = WorkspaceCreate(name="Alternate Workspace").model_dump()
    ws_res = await client.post("/workspaces", json=ws_payload)
    assert ws_res.status_code == 201
    workspace_id = ws_res.json()["id"]
    yield workspace_id
    delete_workspace_by_id(workspace_id)


@pytest_asyncio.fixture
async def enable_privileged_mode():
    set_privileged_mode(True)
    yield
    set_privileged_mode(False)


@pytest_asyncio.fixture(scope="session", autouse=True)
async def manage_test_db():
    # SQLite-based tests use the shared local database file.
    init_db()
    yield


####
####
####
####
####
####
