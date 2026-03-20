import os

import pytest_asyncio
from app.database import MONGODB_URI, get_db
from app.main import app
from app.utils.auth import get_current_user
from httpx import ASGITransport, AsyncClient
from motor.motor_asyncio import AsyncIOMotorClient

TEST_DB_NAME = os.getenv("TEST_DB_NAME", "codexj-test")


@pytest_asyncio.fixture
async def db_client():
    client = AsyncIOMotorClient(MONGODB_URI)
    await client.admin.command("ping")

    yield client

    client.close()


@pytest_asyncio.fixture
async def client():
    test_client = AsyncIOMotorClient(MONGODB_URI, serverSelectionTimeoutMS=5000)
    app.dependency_overrides[get_current_user] = lambda: {"id": "test-user-id"}
    app.dependency_overrides[get_db] = lambda: test_client[TEST_DB_NAME]

    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://localhost") as c:
        yield c

    test_client.close()
    app.dependency_overrides.clear()


####
####
####
####
####
####
