import os

import pytest_asyncio
from app.database import MONGODB_URI, get_db
from app.main import app
from app.routes import media as media_routes
from app.utils.auth import get_current_user, hash_secret
from app.utils.data_management import derive_dump_key
from httpx import ASGITransport, AsyncClient
from motor.motor_asyncio import AsyncIOMotorClient

TEST_DB_NAME = os.getenv("TEST_DB_NAME", "codexj-test")

# Known test credentials so roundtrip export/import tests can derive the correct dump key.
FIXTURE_USER_ID = "test-user-id"
FIXTURE_HASHKEY = "fixture_hashkey_123"
FIXTURE_DUMP_KEY = derive_dump_key(FIXTURE_HASHKEY, FIXTURE_USER_ID)


@pytest_asyncio.fixture
async def db_client():
    client = AsyncIOMotorClient(MONGODB_URI)
    await client.admin.command("ping")

    yield client

    client.close()


@pytest_asyncio.fixture
async def client():
    test_client = AsyncIOMotorClient(MONGODB_URI, serverSelectionTimeoutMS=5000)
    app.dependency_overrides[get_current_user] = lambda: {
        "id": "test-user-id",
        "username": "test-user",
        "is_privileged": True,
        "password_hash": hash_secret("fixture_password_123"),
        "dump_key": FIXTURE_DUMP_KEY,
    }
    app.dependency_overrides[get_db] = lambda: test_client[TEST_DB_NAME]

    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://localhost") as c:
        yield c

    await media_routes.wait_for_webpage_archive_tasks()
    await media_routes.wait_for_music_lookup_tasks()
    test_client.close()
    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def unprivileged_client():
    test_client = AsyncIOMotorClient(MONGODB_URI, serverSelectionTimeoutMS=5000)
    app.dependency_overrides[get_current_user] = lambda: {
        "id": "test-user-id",
        "username": "test-user",
        "is_privileged": False,
        "password_hash": hash_secret("fixture_password_123"),
        "dump_key": FIXTURE_DUMP_KEY,
    }
    app.dependency_overrides[get_db] = lambda: test_client[TEST_DB_NAME]

    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://localhost") as c:
        yield c

    await media_routes.wait_for_webpage_archive_tasks()
    await media_routes.wait_for_music_lookup_tasks()
    test_client.close()
    app.dependency_overrides.clear()


@pytest_asyncio.fixture(scope="session", autouse=True)
async def manage_test_db():
    # setup

    # yield control back to tests
    yield

    # teardown: drop the test database after all tests have run
    client = AsyncIOMotorClient(MONGODB_URI)
    await client.drop_database(TEST_DB_NAME)
    client.close()


####
####
####
####
####
####
