import pytest

from backend.database.querying import delete_tag, get_all_tags
from backend.models.tag import TagCreate


@pytest.fixture(scope="function", autouse=True)
def cleanup_tags():
    yield
    tags = get_all_tags()
    for tag in tags:
        delete_tag(tag)


@pytest.mark.asyncio
async def test_create_tag(client):
    payload = TagCreate(name="Test Tag")
    response = await client.post("/tags", json=payload.model_dump())
    assert response.status_code == 201
    data = response.json()
    assert data["name"] == payload.name


@pytest.mark.asyncio
async def test_list_tags(client):
    tag_names = ["Type 1", "Type 2", "Type 3"]
    for name in tag_names:
        payload = TagCreate(name=name).model_dump()
        response = await client.post("/tags", json=payload)
        assert response.status_code == 201

    list_response = await client.get("/tags")
    assert list_response.status_code == 200
    data = list_response.json()
    returned_names = [et["name"] for et in data]
    for name in tag_names:
        assert name in returned_names
