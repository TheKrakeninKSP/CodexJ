from fastapi import APIRouter, Depends, HTTPException

from backend.database.querying import (
    create_journal,
    get_journal_by_id,
    get_journals_by_workspace_id,
)
from backend.database.querying import move_journal as move_journal_record
from backend.database.querying import (
    update_journal_name_and_description,
)
from backend.database.structural import JournalModel, UserModel
from backend.models.journal import (
    JournalCreate,
    JournalMove,
    JournalOut,
    JournalRestoreOut,
    JournalUpdate,
)
from backend.type_defs import id_type
from backend.utils.auth import (
    assert_workspace_owner,
    get_current_user,
    require_privileged_mode,
)
from backend.utils.common import utcnow
from backend.utils.data_management import (
    recursive_delete_journal,
    restore_binned_journal,
)

router = APIRouter(prefix="/workspaces", tags=["journals"])


def _fmt(journal: JournalModel, workspace_name: str) -> JournalOut:
    return JournalOut(
        id=journal.id,
        workspace_id=journal.workspace_id,
        name=journal.name,
        description=journal.description,
        workspace_name=workspace_name,
        created_at=journal.created_at,
    )


def _get_live_journal(journal_id: id_type, workspace_id: id_type) -> JournalModel:
    journal = get_journal_by_id(journal_id)
    if not journal or journal.workspace_id != workspace_id or journal.deleted_at:
        raise HTTPException(status_code=404, detail="Journal not found")
    return journal


@router.get("/{workspace_id}/journals", response_model=list[JournalOut])
async def list_journals(
    workspace_id: id_type,
    user: UserModel = Depends(get_current_user),
):
    workspace = assert_workspace_owner(workspace_id, user.id)
    return [
        _fmt(journal, workspace.name)
        for journal in get_journals_by_workspace_id(workspace.id)
    ]


@router.get("/{workspace_id}/journals/{journal_id}")
async def get_journal(
    workspace_id: id_type,
    journal_id: id_type,
    user: UserModel = Depends(get_current_user),
):
    workspace = assert_workspace_owner(workspace_id, user.id)
    journal = _get_live_journal(journal_id, workspace.id)
    return _fmt(journal, workspace.name)


@router.post("/{workspace_id}/journals", response_model=JournalOut, status_code=201)
async def add_journal(
    workspace_id: id_type,
    payload: JournalCreate,
    user: UserModel = Depends(get_current_user),
):
    workspace = assert_workspace_owner(workspace_id, user.id)
    journal = JournalModel(
        workspace_id=workspace.id,
        name=payload.name,
        description=payload.description,
        created_at=utcnow(),
    )
    create_journal(journal)
    return _fmt(journal, workspace.name)


@router.patch("/{workspace_id}/journals/{journal_id}", response_model=JournalOut)
async def update_journal(
    workspace_id: id_type,
    journal_id: id_type,
    payload: JournalUpdate,
    user: UserModel = Depends(get_current_user),
    _=Depends(require_privileged_mode),
):
    workspace = assert_workspace_owner(workspace_id, user.id)
    journal = _get_live_journal(journal_id, workspace.id)
    updated = update_journal_name_and_description(
        journal.id, payload.name, payload.description
    )
    if updated is None:
        raise HTTPException(400, "Did not update journal")
    return _fmt(updated, workspace.name)


@router.delete("/{workspace_id}/journals/{journal_id}", status_code=204)
async def delete_journal(
    workspace_id: id_type,
    journal_id: id_type,
    current_user: UserModel = Depends(get_current_user),
    _=Depends(require_privileged_mode),
):
    workspace = assert_workspace_owner(workspace_id, current_user.id)
    journal = _get_live_journal(journal_id, workspace.id)
    # Moves its entries to the bin; the journal can be restored from there.
    await recursive_delete_journal(journal.id)


@router.post(
    "/{workspace_id}/journals/{journal_id}/restore", response_model=JournalRestoreOut
)
async def restore_journal(
    workspace_id: id_type,
    journal_id: id_type,
    current_user: UserModel = Depends(get_current_user),
):
    """Bring back a binned journal (and its workspace, if that was binned too)
    with the entries binned along with it. No sudo: nothing is lost."""
    workspace = assert_workspace_owner(
        workspace_id, current_user.id, allow_deleted=True
    )
    journal = get_journal_by_id(journal_id)
    if not journal or journal.workspace_id != workspace.id or not journal.deleted_at:
        raise HTTPException(404, "Binned journal not found")
    restored = restore_binned_journal(journal.id)
    refreshed = get_journal_by_id(journal.id)
    assert refreshed is not None
    return JournalRestoreOut(
        journal=_fmt(refreshed, workspace.name),
        workspace_restored=workspace.deleted_at is not None,
        entries_restored=restored,
    )


@router.patch("/{workspace_id}/journals/{journal_id}/move", response_model=JournalOut)
async def move_journal(
    workspace_id: id_type,
    journal_id: id_type,
    payload: JournalMove,
    current_user: UserModel = Depends(get_current_user),
    _=Depends(require_privileged_mode),
):
    source = assert_workspace_owner(workspace_id, current_user.id)
    destination = assert_workspace_owner(payload.workspace_id, current_user.id)
    if workspace_id == payload.workspace_id:
        raise HTTPException(400, "Source and destination workspace are the same")
    journal = _get_live_journal(journal_id, source.id)
    moved = move_journal_record(journal.id, destination.id)
    if moved is None:
        raise HTTPException(404, "Journal not found")
    return _fmt(moved, destination.name)
