import pytest


# test local db connection
@pytest.mark.asyncio
async def test_local_db_connection(db_client):
    try:
        await db_client.admin.command("ping")
    except Exception as e:
        pytest.fail(f"Cannot connect to local database: {e}")


# test workspace creation
@pytest.mark.asyncio
async def test_create_workspace(client):
    payload = {"name": "Test Workspace"}
    response = await client.post("/workspaces", json=payload)
    assert response.status_code == 201
    data = response.json()
    assert data["name"] == payload["name"]


@pytest.mark.asyncio
async def test_create_entry(client, journal_id):
    payload = {
        "type": "text",
        "body": {"ops": [{"insert": "Hello, world!\n"}]},
        "name": "My First Entry",
    }
    response = await client.post(f"/journals/{journal_id}/entries", json=payload)
    assert response.status_code == 201
    data = response.json()
    assert data["type"] == payload["type"]
    assert data["body"] == payload["body"]
    assert data["name"] == payload["name"]
    assert data["name"] == payload["name"]
