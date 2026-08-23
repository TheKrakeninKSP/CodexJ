import os

import pytest_asyncio
from httpx import ASGITransport, AsyncClient

os.environ.setdefault("JWT_SECRET", "test-secret-key")
os.environ.setdefault("JWT_ALGORITHM", "HS256")
os.environ.setdefault("JWT_EXPIRE_DAYS", "7")

from backend.database.querying import get_user_by_username
from backend.database.structural import Session, UserModel, init_db
from backend.main import app
from backend.routes import media as media_routes
from backend.utils.auth import get_current_user, hash_secret, set_privileged_mode
from backend.utils.common import utcnow
from backend.utils.data_management import derive_dump_key

TEST_DB_NAME = os.getenv("TEST_DB_NAME", "codexj-test")

# Known test credentials so roundtrip export/import tests can derive the correct dump key.
FIXTURE_USER_ID = "test-user-id"
FIXTURE_HASHKEY = "fixture_hashkey_123"
FIXTURE_USERNAME = "test-user"
FIXTURE_DUMP_KEY = derive_dump_key(FIXTURE_HASHKEY, FIXTURE_USERNAME)


def _ensure_fixture_user() -> UserModel:
    init_db()
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


@pytest_asyncio.fixture
async def client():
    init_db()
    set_privileged_mode(True)
    app.dependency_overrides[get_current_user] = _ensure_fixture_user

    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://localhost") as c:
        yield c

    await media_routes.wait_for_webpage_archive_tasks()
    await media_routes.wait_for_music_lookup_tasks()
    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def unprivileged_client():
    init_db()
    set_privileged_mode(False)
    app.dependency_overrides[get_current_user] = _ensure_fixture_user

    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://localhost") as c:
        yield c

    await media_routes.wait_for_webpage_archive_tasks()
    await media_routes.wait_for_music_lookup_tasks()
    app.dependency_overrides.clear()


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
