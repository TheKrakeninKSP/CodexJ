from datetime import datetime, timezone

import pytest
from httpx import ASGITransport, AsyncClient

from backend.database.querying import (
    create_tag,
    create_user,
    delete_tags_by_user_id,
    get_tag_by_name,
    get_tags_by_user,
)
from backend.database.structural import TagModel, UserModel
from backend.main import app_factory
from backend.models.data_management import DumpTag, UserDataDump
from backend.models.tag import TagCreate
from backend.type_defs import new_id
from backend.utils.auth import hash_secret
from backend.utils.common import utcnow
from backend.utils.data_management import (
    import_dump_data,
    read_encrypted_dump,
    recursive_delete_user,
)

from .conftest import (
    FIXTURE_DUMP_KEY,
    FIXTURE_USERNAME,
    _ensure_alternate_fixture_user,
    _ensure_fixture_user,
)


def _names(user_id) -> set[str]:
    return {t.name for t in get_tags_by_user(user_id)}


@pytest.fixture(scope="function", autouse=True)
def cleanup_tags():
    yield
    delete_tags_by_user_id(_ensure_fixture_user().id)
    delete_tags_by_user_id(_ensure_alternate_fixture_user().id)


@pytest.mark.asyncio
async def test_create_tag(client):
    payload = TagCreate(name="Test Tag")
    response = await client.post("/tags", json=payload.model_dump())
    assert response.status_code == 201
    data = response.json()
    assert data["name"] == payload.name
    assert "Test Tag" in _names(_ensure_fixture_user().id)


@pytest.mark.asyncio
async def test_list_tags(client):
    tag_names = ["Type 1", "Type 2", "Type 3"]
    for name in tag_names:
        payload = TagCreate(name=name).model_dump()
        response = await client.post("/tags", json=payload)
        assert response.status_code == 201

    list_response = await client.get("/tags")
    assert list_response.status_code == 200
    returned_names = [et["name"] for et in list_response.json()]
    for name in tag_names:
        assert name in returned_names


@pytest.mark.asyncio
async def test_tags_are_scoped_per_user(client, alternate_user_client):
    assert (await client.post("/tags", json={"name": "Only Mine"})).status_code == 201
    assert (await client.post("/tags", json={"name": "Shared"})).status_code == 201
    # The same name is free for another user.
    assert (
        await alternate_user_client.post("/tags", json={"name": "Shared"})
    ).status_code == 201

    other_names = [t["name"] for t in (await alternate_user_client.get("/tags")).json()]
    assert other_names == ["Shared"]
    my_names = {t["name"] for t in (await client.get("/tags")).json()}
    assert {"Only Mine", "Shared"} <= my_names


@pytest.mark.asyncio
async def test_duplicate_tag_rejected_within_user(client):
    assert (await client.post("/tags", json={"name": "Dup"})).status_code == 201
    response = await client.post("/tags", json={"name": "Dup"})
    assert response.status_code == 400
    assert response.json()["detail"] == "Tag already exists"


@pytest.mark.asyncio
async def test_tags_require_auth():
    app = app_factory()  # no get_current_user override
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://localhost"
    ) as anon:
        assert (await anon.get("/tags")).status_code in (401, 403)
        assert (await anon.post("/tags", json={"name": "x"})).status_code in (401, 403)


@pytest.mark.asyncio
async def test_entry_create_and_update_register_user_tags(client, make_journal):
    me = _ensure_fixture_user()
    other = _ensure_alternate_fixture_user()
    res = await client.post(
        f"/journals/{make_journal}/entries",
        json={"name": "Tagged", "body": {}, "tags": ["alpha", "beta"]},
    )
    assert res.status_code == 201
    assert {"alpha", "beta"} <= _names(me.id)

    patch = await client.patch(
        f"/entries/{res.json()['id']}", json={"tags": ["beta", "gamma"]}
    )
    assert patch.status_code == 200
    assert {"alpha", "beta", "gamma"} <= _names(me.id)
    assert not {"alpha", "beta", "gamma"} & _names(other.id)


async def _export_dump(client) -> UserDataDump:
    res = await client.post("/data-management/export")
    assert res.status_code == 200
    download = await client.get(
        f"/data-management/export/download/{res.json()['filename']}"
    )
    assert download.status_code == 200
    data = read_encrypted_dump(download.content, FIXTURE_DUMP_KEY)
    assert data is not None
    return UserDataDump.model_validate(data)


@pytest.mark.asyncio
async def test_export_includes_only_own_tags(
    client, alternate_user_client, make_entry, enable_privileged_mode
):
    await client.post("/tags", json={"name": "unused-but-mine"})
    await alternate_user_client.post("/tags", json={"name": "not-mine"})

    dump = await _export_dump(client)
    names = {t.name for t in dump.tags}
    assert "unused-but-mine" in names
    assert "test" in names  # make_entry's tag
    assert "not-mine" not in names


@pytest.mark.asyncio
async def test_import_scopes_tags_and_leaves_other_users_alone(
    client, make_entry, enable_privileged_mode
):
    me = _ensure_fixture_user()
    other = _ensure_alternate_fixture_user()
    later = datetime(2026, 6, 1, tzinfo=timezone.utc)
    earlier = datetime(2026, 1, 1, tzinfo=timezone.utc)
    create_tag(TagModel(user_id=other.id, name="shared", created_at=later))
    create_tag(TagModel(user_id=me.id, name="mine-older", created_at=later))

    dump = await _export_dump(client)
    # Replace the dump's tag list. Leaving out make_entry's "test" tag
    # simulates an older dump whose tag list missed an entry's tag.
    dump.tags = [
        DumpTag(id=new_id(), name="shared", created_at=earlier),
        DumpTag(id=new_id(), name="mine-older", created_at=earlier),
    ]
    delete_tags_by_user_id(me.id)
    create_tag(TagModel(user_id=me.id, name="mine-older", created_at=later))

    result = await import_dump_data(dump, FIXTURE_USERNAME, conflict_resolution="skip")
    assert result.status == "completed"

    # Another user's same-named tag is untouched.
    other_tag = get_tag_by_name(other.id, "shared")
    assert other_tag is not None
    assert other_tag.created_at.replace(tzinfo=timezone.utc) == later
    # The importing user gets their own copy with the dump's timestamp...
    my_shared = get_tag_by_name(me.id, "shared")
    assert my_shared is not None and my_shared.id != other_tag.id
    assert my_shared.created_at.replace(tzinfo=timezone.utc) == earlier
    # ...an existing tag moves to the earlier timestamp in place...
    my_older = get_tag_by_name(me.id, "mine-older")
    assert my_older is not None
    assert my_older.created_at.replace(tzinfo=timezone.utc) == earlier
    # ...and entry tags missing from the dump's tag list are still registered.
    assert "test" in _names(me.id)


@pytest.mark.asyncio
async def test_account_deletion_removes_tags():
    user_id = create_user(
        UserModel(
            id=new_id(),
            username="tag-delete-user",
            password_hash=hash_secret("pw"),
            hashkey_hash=hash_secret("hk"),
            dump_key="unused",
            theme="light",
            created_at=utcnow(),
        )
    )
    create_tag(TagModel(user_id=user_id, name="doomed", created_at=utcnow()))
    assert await recursive_delete_user(user_id)
    assert get_tags_by_user(user_id) == []
