import pytest
import pytest_asyncio

from backend.database.querying import (
    create_workspace,
    delete_journal_by_id,
    delete_workspace_by_id,
)
from backend.database.structural import WorkspaceModel
from backend.models.journal import JournalCreate, JournalMove, JournalUpdate
from backend.models.workspace import WorkspaceCreate


@pytest_asyncio.fixture()
async def clear_journals():
    journal_ids = []
    yield journal_ids
    for journal_id in journal_ids:
        delete_journal_by_id(journal_id)


# test journal creation
@pytest.mark.asyncio
async def test_create_journal(client, make_workspace, clear_journals):
    workspace_id = make_workspace
    payload = JournalCreate(
        name="Test Journal", description="journal descr"
    ).model_dump()
    response = await client.post(f"/workspaces/{workspace_id}/journals", json=payload)
    assert response.status_code == 201
    clear_journals.append(response.json()["id"])
    data = response.json()
    assert data["name"] == payload["name"]
    assert data["description"] == payload["description"]


# test journal listing by creation 3 journals and check existence of all 3
@pytest.mark.asyncio
async def test_list_journals(client, make_workspace, clear_journals):
    workspace_id = make_workspace
    journal_names = ["Journal 1", "Journal 2", "Journal 3"]
    for name in journal_names:
        payload = JournalCreate(name=name, description="journal descr").model_dump()
        response = await client.post(
            f"/workspaces/{workspace_id}/journals", json=payload
        )
        assert response.status_code == 201
        clear_journals.append(response.json()["id"])

    list_response = await client.get(f"/workspaces/{workspace_id}/journals")
    assert list_response.status_code == 200
    data = list_response.json()
    returned_names = [j["name"] for j in data]
    for name in journal_names:
        assert name in returned_names


# test journal update
@pytest.mark.asyncio
async def test_update_journal(
    client, enable_privileged_mode, make_workspace, clear_journals
):
    workspace_id = make_workspace
    journal_payload = JournalCreate(
        name="Test Journal", description="journal descr"
    ).model_dump()
    journal_res = await client.post(
        f"/workspaces/{workspace_id}/journals", json=journal_payload
    )
    assert journal_res.status_code == 201
    journal_id = journal_res.json()["id"]
    clear_journals.append(journal_id)

    update_payload = JournalUpdate(
        name="Updated Test Journal", description="updated journal descr"
    ).model_dump()
    response = await client.patch(
        f"/workspaces/{workspace_id}/journals/{journal_id}", json=update_payload
    )
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == update_payload["name"]
    assert data["description"] == update_payload["description"]


# test journal deletion
@pytest.mark.asyncio
async def test_delete_journal(
    client, enable_privileged_mode, make_workspace, clear_journals
):
    workspace_id = make_workspace
    journal_payload = JournalCreate(
        name="Test Journal", description="journal descr"
    ).model_dump()
    journal_res = await client.post(
        f"/workspaces/{workspace_id}/journals", json=journal_payload
    )
    assert journal_res.status_code == 201
    journal_id = journal_res.json()["id"]
    clear_journals.append(journal_id)

    response = await client.delete(f"/workspaces/{workspace_id}/journals/{journal_id}")
    assert response.status_code == 204

    # Verify the journal is deleted
    get_response = await client.get(f"/workspaces/{workspace_id}/journals/{journal_id}")
    assert get_response.status_code == 404

    # Since entries are no longer created in this test, we skip checking the bin.


@pytest.mark.asyncio
async def test_delete_journal_requires_privileged_mode(
    client, clear_journals, make_workspace
):
    workspace_id = make_workspace

    journal_res = await client.post(
        f"/workspaces/{workspace_id}/journals",
        json={"name": "Restricted Journal"},
    )
    assert journal_res.status_code == 201
    journal_id = journal_res.json()["id"]
    clear_journals.append(journal_id)

    delete_res = await client.delete(
        f"/workspaces/{workspace_id}/journals/{journal_id}"
    )
    assert delete_res.status_code == 403
    assert "privileged mode required" in delete_res.json()["detail"].lower()


@pytest.mark.asyncio
async def test_move_journal_to_another_workspace(
    client, enable_privileged_mode, make_workspace, make_alternate_workspace
):
    ws_a_id = make_workspace
    ws_b_id = make_alternate_workspace

    jr_payload = JournalCreate(
        name="Movable Journal", description="journal descr"
    ).model_dump()

    jr_res = await client.post(
        f"/workspaces/{ws_a_id}/journals",
        json=jr_payload,
    )
    journal_id = jr_res.json()["id"]

    move_payload = JournalMove(workspace_id=ws_b_id).model_dump()
    move_res = await client.patch(
        f"/workspaces/{ws_a_id}/journals/{journal_id}/move",
        json=move_payload,
    )
    assert move_res.status_code == 200
    assert move_res.json()["workspace_id"] == ws_b_id

    # Should appear in dest workspace
    dest_journals = await client.get(f"/workspaces/{ws_b_id}/journals")
    assert any(j["id"] == journal_id for j in dest_journals.json())

    # Should not appear in source workspace
    src_journals = await client.get(f"/workspaces/{ws_a_id}/journals")
    assert all(j["id"] != journal_id for j in src_journals.json())

    # check name and description in the destination workspace
    dest_journal = next(j for j in dest_journals.json() if j["id"] == journal_id)
    assert dest_journal["name"] == "Movable Journal"
    assert dest_journal["description"] == "journal descr"


@pytest.mark.asyncio
async def test_move_journal_requires_privileged_mode(
    client, make_workspace, make_alternate_workspace
):
    ws_a_id = make_workspace
    ws_b_id = make_alternate_workspace

    jr_payload = JournalCreate(
        name="Restricted Move Journal", description="journal descr"
    ).model_dump()

    jr_res = await client.post(
        f"/workspaces/{ws_a_id}/journals",
        json=jr_payload,
    )
    journal_id = jr_res.json()["id"]

    move_res = await client.patch(
        f"/workspaces/{ws_a_id}/journals/{journal_id}/move",
        json=JournalMove(workspace_id=ws_b_id).model_dump(),
    )
    assert move_res.status_code == 403
    assert "privileged mode required" in move_res.json()["detail"].lower()


@pytest.mark.asyncio
async def test_journal_functions_as_alternate_user(
    client, alternate_user_client, make_workspace, make_alternate_workspace
):
    # create a journal as primary user
    ws_id = make_workspace
    ws_b_id = make_alternate_workspace
    jr_payload = JournalCreate(
        name="Primary User Journal", description="journal descr"
    ).model_dump()
    jr_res = await client.post(
        f"/workspaces/{ws_id}/journals",
        json=jr_payload,
    )
    journal_id = jr_res.json()["id"]

    # access the journal as alternate user
    alt_res = await alternate_user_client.get(
        f"/workspaces/{ws_id}/journals/{journal_id}"
    )
    assert alt_res.status_code == 200
    alt_journal = alt_res.json()
    assert alt_journal["name"] == "Primary User Journal"
    assert alt_journal["description"] == "journal descr"

    # update as alternate user
    update_payload = JournalUpdate(
        name="Updated Primary User Journal", description="updated journal descr"
    ).model_dump()
    update_res = await alternate_user_client.patch(
        f"/workspaces/{ws_id}/journals/{journal_id}",
        json=update_payload,
    )
    assert update_res.status_code == 403

    # delete as alternate user
    delete_res = await alternate_user_client.delete(
        f"/workspaces/{ws_id}/journals/{journal_id}"
    )
    assert delete_res.status_code == 403

    # move as alternate user
    ws_b_id = make_alternate_workspace
    move_res = await alternate_user_client.patch(
        f"/workspaces/{ws_id}/journals/{journal_id}/move",
        json=JournalMove(workspace_id=ws_b_id).model_dump(),
    )
    assert move_res.status_code == 403
    assert "privileged mode required" in move_res.json()["detail"].lower()
