import pytest

import backend.routes.auth as auth_routes
from backend.database.structural import UserModel
from backend.utils.data_management import recursive_delete_workspace

from .conftest import _ensure_fixture_user


@pytest.fixture
def media_root(tmp_path, monkeypatch):
    """Point per-user media lookups at a temp dir so tests never touch media/."""
    monkeypatch.setattr(
        auth_routes, "get_user_media_path", lambda user_id: tmp_path / str(user_id)
    )
    return tmp_path


async def _stats(client) -> dict:
    response = await client.get("/auth/me/stats")
    assert response.status_code == 200
    return response.json()


@pytest.mark.asyncio
async def test_stats_count_live_items(client, media_root, enable_privileged_mode):
    before = await _stats(client)

    ws = await client.post("/workspaces", json={"name": "Stats WS"})
    ws_id = ws.json()["id"]
    try:
        await _check_counts(client, before, ws_id)
    finally:
        await recursive_delete_workspace(ws_id, hard=True)


async def _check_counts(client, before: dict, ws_id: str) -> None:
    j = await client.post(
        f"/workspaces/{ws_id}/journals", json={"name": "Stats J", "description": ""}
    )
    j_id = j.json()["id"]
    keep = await client.post(
        f"/journals/{j_id}/entries",
        json={"name": "Keep", "body": {"ops": [{"insert": "hi\n"}]}, "tags": ["stats-a"]},
    )
    binned = await client.post(
        f"/journals/{j_id}/entries",
        json={"name": "Bin", "body": {"ops": [{"insert": "x\n"}]}, "tags": ["stats-b"]},
    )
    assert keep.status_code == binned.status_code == 201
    assert (await client.delete(f"/entries/{binned.json()['id']}")).status_code == 204

    after = await _stats(client)
    assert after["workspace_count"] == before["workspace_count"] + 1
    assert after["journal_count"] == before["journal_count"] + 1
    # The binned entry is excluded from the count but still takes up storage.
    assert after["entry_count"] == before["entry_count"] + 1
    assert after["tag_count"] >= before["tag_count"] + 2
    assert after["text_bytes"] > before["text_bytes"]
    assert after["total_bytes"] == after["media_bytes"] + after["text_bytes"]

    # Binning the workspace drops its journal and entries from the counts.
    assert (await client.delete(f"/workspaces/{ws_id}")).status_code == 204
    binned_ws = await _stats(client)
    assert binned_ws["workspace_count"] == before["workspace_count"]
    assert binned_ws["journal_count"] == before["journal_count"]
    assert binned_ws["entry_count"] == before["entry_count"]


@pytest.mark.asyncio
async def test_stats_media_bytes_and_created_at(client, media_root):
    user: UserModel = _ensure_fixture_user()
    user_dir = media_root / user.id
    user_dir.mkdir(parents=True)
    (user_dir / "a.png").write_bytes(b"x" * 120)

    data = await _stats(client)
    assert data["media_bytes"] == 120
    assert data["created_at"].endswith(("Z", "+00:00"))
