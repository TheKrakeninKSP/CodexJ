"""Binning journals/workspaces: entries go to the bin, the container is kept
hidden as their home, and can be restored (see migration 0007)."""

import os

import pytest

from backend.database.querying import (
    create_entry,
    create_journal,
    create_user,
    create_workspace,
    get_journal_by_id,
    get_workspace_by_id,
)
from backend.database.structural import (
    EntryModel,
    JournalModel,
    UserModel,
    WorkspaceModel,
)
from backend.type_defs import new_id
from backend.utils.addressing import get_user_media_path
from backend.utils.auth import hash_secret, set_privileged_mode
from backend.utils.common import utcnow
from backend.utils.data_management import (
    recursive_delete_journal,
    recursive_delete_user,
)

from .conftest import FIXTURE_HASHKEY, _ensure_fixture_user


async def _make_journal(client, workspace_id, name="Daily"):
    res = await client.post(f"/workspaces/{workspace_id}/journals", json={"name": name})
    assert res.status_code == 201
    return res.json()["id"]


async def _make_entry(client, journal_id, name="Entry", body=None):
    res = await client.post(
        f"/journals/{journal_id}/entries",
        json={"name": name, "body": body or {}, "tags": []},
    )
    assert res.status_code == 201
    return res.json()["id"]


async def _bin(client) -> dict[str, dict]:
    res = await client.get("/entries/bin")
    assert res.status_code == 200
    return {e["id"]: e for e in res.json()}


async def _live_journal_ids(client, workspace_id) -> set[str]:
    res = await client.get(f"/workspaces/{workspace_id}/journals")
    return {j["id"] for j in res.json()} if res.status_code == 200 else set()


# ── Binning ──────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_journal_delete_bins_entries_and_hides_journal(
    client, make_workspace, enable_privileged_mode
):
    journal_id = await _make_journal(client, make_workspace)
    live = await _make_entry(client, journal_id, "live")
    earlier = await _make_entry(client, journal_id, "binned earlier")
    assert (await client.delete(f"/entries/{earlier}")).status_code == 204

    res = await client.delete(f"/workspaces/{make_workspace}/journals/{journal_id}")
    assert res.status_code == 204

    assert journal_id not in await _live_journal_ids(client, make_workspace)
    journal = get_journal_by_id(journal_id)
    assert journal is not None and journal.deleted_at is not None

    binned = await _bin(client)
    assert binned[live]["binned_with_container"] is True
    assert binned[earlier]["binned_with_container"] is False
    for entry_id in (live, earlier):
        assert binned[entry_id]["original_journal_deleted"] is True
        assert binned[entry_id]["original_journal_name"] == "Daily"
    count = (await client.get("/entries/bin/count")).json()["count"]
    assert count >= 2


@pytest.mark.asyncio
async def test_journal_delete_still_requires_sudo(client, make_workspace):
    journal_id = await _make_journal(client, make_workspace)
    res = await client.delete(f"/workspaces/{make_workspace}/journals/{journal_id}")
    assert res.status_code == 403


@pytest.mark.asyncio
async def test_empty_journal_and_workspace_are_removed_outright(
    client, enable_privileged_mode
):
    ws = (await client.post("/workspaces", json={"name": "Empty WS"})).json()["id"]
    journal_id = await _make_journal(client, ws, "Empty")

    await client.delete(f"/workspaces/{ws}/journals/{journal_id}")
    assert get_journal_by_id(journal_id) is None

    await client.delete(f"/workspaces/{ws}")
    assert get_workspace_by_id(ws) is None


@pytest.mark.asyncio
async def test_workspace_delete_bins_all_its_journals(client, enable_privileged_mode):
    ws = (await client.post("/workspaces", json={"name": "Doomed WS"})).json()["id"]
    try:
        entries = [
            await _make_entry(client, await _make_journal(client, ws, name), name)
            for name in ("A", "B")
        ]
        assert (await client.delete(f"/workspaces/{ws}")).status_code == 204

        workspace = get_workspace_by_id(ws)
        assert workspace is not None and workspace.deleted_at is not None
        listed = {w["id"] for w in (await client.get("/workspaces")).json()}
        assert ws not in listed
        binned = await _bin(client)
        for entry_id in entries:
            assert binned[entry_id]["binned_with_container"] is True
            assert binned[entry_id]["original_journal_deleted"] is True
    finally:
        from backend.utils.data_management import recursive_delete_workspace

        await recursive_delete_workspace(ws, hard=True)


# ── Binned containers are off limits for everyday actions ────────────────────


@pytest.mark.asyncio
async def test_binned_journal_rejects_live_actions(
    client, make_workspace, enable_privileged_mode
):
    journal_id = await _make_journal(client, make_workspace)
    await _make_entry(client, journal_id)
    other = (await client.post("/workspaces", json={"name": "Other"})).json()["id"]
    try:
        await client.delete(f"/workspaces/{make_workspace}/journals/{journal_id}")
        base = f"/workspaces/{make_workspace}/journals/{journal_id}"

        assert (await client.get(base)).status_code == 404
        assert (await client.patch(base, json={"name": "x"})).status_code == 404
        assert (
            await client.patch(f"{base}/move", json={"workspace_id": other})
        ).status_code == 404
        assert (await client.get(f"/journals/{journal_id}/entries")).status_code == 404
        assert (
            await client.post(
                f"/journals/{journal_id}/entries", json={"tags": [], "body": {}}
            )
        ).status_code == 404
    finally:
        from backend.utils.data_management import recursive_delete_workspace

        await recursive_delete_workspace(other, hard=True)


# ── Restoring single entries ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_restore_to_binned_journal_refused_elsewhere_allowed(
    client, make_workspace, enable_privileged_mode
):
    journal_id = await _make_journal(client, make_workspace, "Gone")
    target = await _make_journal(client, make_workspace, "Target")
    entry_id = await _make_entry(client, journal_id)
    await client.delete(f"/workspaces/{make_workspace}/journals/{journal_id}")

    refused = await client.post(
        f"/entries/{entry_id}/restore",
        json={"workspace_id": make_workspace, "journal_id": journal_id},
    )
    assert refused.status_code == 404

    ok = await client.post(
        f"/entries/{entry_id}/restore",
        json={"workspace_id": make_workspace, "journal_id": target},
    )
    assert ok.status_code == 200
    assert ok.json()["journal_id"] == target
    # The binned journal held nothing else, so it's cleaned up.
    assert get_journal_by_id(journal_id) is None


@pytest.mark.asyncio
async def test_restore_cannot_take_another_users_binned_entry(
    client, alternate_user_client, make_workspace, enable_privileged_mode
):
    journal_id = await _make_journal(client, make_workspace)
    entry_id = await _make_entry(client, journal_id)
    await client.delete(f"/entries/{entry_id}")

    alt_ws = (await alternate_user_client.post("/workspaces", json={"name": "Alt"})).json()["id"]
    try:
        alt_journal = await _make_journal(alternate_user_client, alt_ws)
        res = await alternate_user_client.post(
            f"/entries/{entry_id}/restore",
            json={"workspace_id": alt_ws, "journal_id": alt_journal},
        )
        assert res.status_code == 403
    finally:
        from backend.utils.data_management import recursive_delete_workspace

        await recursive_delete_workspace(alt_ws, hard=True)


@pytest.mark.asyncio
async def test_moved_journal_still_restores_to_original(
    client, make_workspace, enable_privileged_mode
):
    journal_id = await _make_journal(client, make_workspace)
    entry_id = await _make_entry(client, journal_id)
    await client.delete(f"/entries/{entry_id}")
    other = (await client.post("/workspaces", json={"name": "Moved To"})).json()["id"]
    try:
        moved = await client.patch(
            f"/workspaces/{make_workspace}/journals/{journal_id}/move",
            json={"workspace_id": other},
        )
        assert moved.status_code == 200

        binned = (await _bin(client))[entry_id]
        assert binned["original_journal_deleted"] is False
        assert binned["original_workspace_id"] == other  # current, not stale

        res = await client.post(
            f"/entries/{entry_id}/restore",
            json={"workspace_id": binned["deleted_from_workspace_id"], "journal_id": journal_id},
        )
        assert res.status_code == 200
    finally:
        from backend.utils.data_management import recursive_delete_workspace

        await recursive_delete_workspace(other, hard=True)


# ── Purge and media ──────────────────────────────────────────────────────────


async def _entry_with_media(client, journal_id) -> tuple[str, str]:
    entry_id = await _make_entry(client, journal_id, "with media")
    upload = await client.post(
        "/media/upload",
        data={"entry_id": entry_id},
        files={"file": ("pic.png", b"png-bytes", "image/png")},
    )
    assert upload.status_code == 201
    url = upload.json()["resource_path"]
    patch = await client.patch(
        f"/entries/{entry_id}", json={"body": f'<p><img src="{url}"></p>'}
    )
    assert patch.status_code == 200
    return entry_id, url.rsplit("/", 1)[-1]


@pytest.mark.asyncio
async def test_trim_media_keeps_media_of_entries_in_binned_journal(
    client, make_workspace, enable_privileged_mode
):
    journal_id = await _make_journal(client, make_workspace)
    entry_id, filename = await _entry_with_media(client, journal_id)
    media_file = get_user_media_path(_ensure_fixture_user().id) / filename
    assert media_file.exists()

    await client.delete(f"/workspaces/{make_workspace}/journals/{journal_id}")
    assert (await client.post("/media/trim")).status_code == 200
    assert media_file.exists()

    # Purging the orphan removes its media and the now-empty binned journal.
    assert (await client.delete(f"/entries/{entry_id}/purge")).status_code == 204
    assert not media_file.exists()
    assert get_journal_by_id(journal_id) is None


# ── Restore journal ──────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_restore_journal_brings_back_entries_binned_with_it(
    client, make_workspace, enable_privileged_mode
):
    journal_id = await _make_journal(client, make_workspace)
    with_journal = await _make_entry(client, journal_id, "with journal")
    earlier = await _make_entry(client, journal_id, "binned earlier")
    await client.delete(f"/entries/{earlier}")
    await client.delete(f"/workspaces/{make_workspace}/journals/{journal_id}")

    set_privileged_mode(False)  # restoring doesn't need sudo
    res = await client.post(
        f"/workspaces/{make_workspace}/journals/{journal_id}/restore"
    )
    assert res.status_code == 200
    body = res.json()
    assert body["entries_restored"] == 1
    assert body["workspace_restored"] is False
    assert body["journal"]["id"] == journal_id

    assert journal_id in await _live_journal_ids(client, make_workspace)
    assert (await client.get(f"/entries/{with_journal}")).status_code == 200
    binned = await _bin(client)
    assert with_journal not in binned
    # The individually binned entry stays binned, but can now go back home.
    assert binned[earlier]["original_journal_deleted"] is False


@pytest.mark.asyncio
async def test_restore_journal_also_restores_binned_workspace(
    client, enable_privileged_mode
):
    ws = (await client.post("/workspaces", json={"name": "Comeback WS"})).json()["id"]
    try:
        j1 = await _make_journal(client, ws, "J1")
        j2 = await _make_journal(client, ws, "J2")
        await _make_entry(client, j1)
        await _make_entry(client, j2)
        await client.delete(f"/workspaces/{ws}")

        res = await client.post(f"/workspaces/{ws}/journals/{j1}/restore")
        assert res.status_code == 200
        assert res.json()["workspace_restored"] is True

        assert ws in {w["id"] for w in (await client.get("/workspaces")).json()}
        # Only the restored journal comes back; its sibling stays binned.
        assert await _live_journal_ids(client, ws) == {j1}
        j2_row = get_journal_by_id(j2)
        assert j2_row is not None and j2_row.deleted_at is not None
    finally:
        from backend.utils.data_management import recursive_delete_workspace

        await recursive_delete_workspace(ws, hard=True)


@pytest.mark.asyncio
async def test_restore_journal_rejects_live_and_foreign_journals(
    client, alternate_user_client, make_workspace, enable_privileged_mode
):
    journal_id = await _make_journal(client, make_workspace)
    await _make_entry(client, journal_id)
    url = f"/workspaces/{make_workspace}/journals/{journal_id}/restore"
    assert (await client.post(url)).status_code == 404  # not binned

    await client.delete(f"/workspaces/{make_workspace}/journals/{journal_id}")
    assert (await alternate_user_client.post(url)).status_code == 403


# ── Export / import ──────────────────────────────────────────────────────────


async def _export(client) -> bytes:
    res = await client.post("/data-management/export")
    assert res.status_code == 200
    dl = await client.get(f"/data-management/export/download/{res.json()['filename']}")
    assert dl.status_code == 200
    return dl.content


async def _import(client, content: bytes, conflict: str):
    res = await client.post(
        "/data-management/import/encrypted",
        data={"hashkey": FIXTURE_HASHKEY, "conflict_resolution": conflict},
        files={"file": ("dump.bin", content, "application/octet-stream")},
    )
    assert res.status_code == 200, res.text
    return res.json()


async def _wipe_fixture_user_workspaces():
    from backend.database.querying import get_workspaces_by_user_id
    from backend.utils.data_management import recursive_delete_workspace

    user = _ensure_fixture_user()
    for ws in get_workspaces_by_user_id(user.id, include_deleted=True):
        await recursive_delete_workspace(ws.id, hard=True)


@pytest.mark.asyncio
async def test_export_import_keeps_binned_journal_and_its_entries(
    client, enable_privileged_mode
):
    await _wipe_fixture_user_workspaces()
    try:
        ws = (await client.post("/workspaces", json={"name": "Roundtrip WS"})).json()["id"]
        journal_id = await _make_journal(client, ws, "Binned One")
        await _make_entry(client, journal_id, "orphan")
        await client.delete(f"/workspaces/{ws}/journals/{journal_id}")

        content = await _export(client)
        await _wipe_fixture_user_workspaces()
        result = await _import(client, content, "create_new")
        assert result["entries_imported"] == 1

        binned = [e for e in (await _bin(client)).values() if e["name"] == "orphan"]
        assert len(binned) == 1
        orphan = binned[0]
        assert orphan["original_journal_deleted"] is True
        assert orphan["binned_with_container"] is True
        assert orphan["original_journal_name"] == "Binned One"

        restore = await client.post(
            f"/workspaces/{orphan['original_workspace_id']}/journals/"
            f"{orphan['journal_id']}/restore"
        )
        assert restore.status_code == 200
        assert restore.json()["entries_restored"] == 1
    finally:
        await _wipe_fixture_user_workspaces()


@pytest.mark.asyncio
async def test_import_skip_never_merges_live_journal_into_binned_one(
    client, enable_privileged_mode
):
    await _wipe_fixture_user_workspaces()
    try:
        ws = (await client.post("/workspaces", json={"name": "Merge WS"})).json()["id"]
        journal_id = await _make_journal(client, ws, "Daily")
        entry_id = await _make_entry(client, journal_id, "keep me live")
        content = await _export(client)  # dump has a live "Daily"

        # Now the account's "Daily" is binned (same name, same workspace).
        await client.delete(f"/workspaces/{ws}/journals/{journal_id}")
        await _import(client, content, "skip")

        live = (await client.get(f"/workspaces/{ws}/journals")).json()
        dailies = [j for j in live if j["name"] == "Daily"]
        assert len(dailies) == 1 and dailies[0]["id"] != journal_id
        entries = (await client.get(f"/journals/{dailies[0]['id']}/entries")).json()
        assert [e["name"] for e in entries] == ["keep me live"]
        # The original binned journal and its binned entry are untouched.
        assert (await _bin(client))[entry_id]["original_journal_deleted"] is True
    finally:
        await _wipe_fixture_user_workspaces()


# ── Account shred ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_account_shred_removes_binned_containers():
    user_id = create_user(
        UserModel(
            id=new_id(),
            username="shred-binned-user",
            password_hash=hash_secret("pw"),
            hashkey_hash=hash_secret("hk"),
            dump_key="unused",
            theme="light",
            created_at=utcnow(),
        )
    )
    ws_id = create_workspace(WorkspaceModel(user_id=user_id, name="W", created_at=utcnow()))
    journal_id = create_journal(
        JournalModel(workspace_id=ws_id, name="J", created_at=utcnow())
    )
    create_entry(EntryModel(journal_id=journal_id, date_created=utcnow(), updated_at=utcnow()))
    await recursive_delete_journal(journal_id)
    assert get_journal_by_id(journal_id) is not None  # binned, kept

    assert await recursive_delete_user(user_id)
    assert get_journal_by_id(journal_id) is None
    assert get_workspace_by_id(ws_id) is None
    assert not os.path.exists(get_user_media_path(user_id))
