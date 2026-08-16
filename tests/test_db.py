import pytest


# test local db connection
@pytest.mark.asyncio
async def test_local_db_connection(db_client):
    try:
        await db_client.admin.command("ping")
    except Exception as e:
        pytest.fail(f"Cannot connect to local database: {e}")
