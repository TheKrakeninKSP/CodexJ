import pytest


@pytest.mark.asyncio
async def test_help_route_serves_markdown(client):
    response = await client.get("/help")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/markdown")
    assert "# CodexJ Help" in response.text
    assert "Create Workspace" in response.text
