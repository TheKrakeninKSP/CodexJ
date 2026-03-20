import pytest
import pytest_asyncio
from app.database import get_db_no_deps
from app.main import app
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
    await db["users"].delete_many({"username": "test_user"})
