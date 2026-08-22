from fastapi import APIRouter, Depends, HTTPException

from backend.database.querying import (
    create_journal,
    delete_journal_by_id,
    get_journal_by_id,
    get_journals_by_workspace_id,
    get_workspace_by_id,
)
from backend.database.querying import move_journal as move_journal_record
from backend.database.querying import (
    update_journal_name_and_description,
)
from backend.database.structural import JournalModel, UserModel
from backend.models.journal import JournalCreate, JournalMove, JournalOut, JournalUpdate
from backend.utils.auth import get_current_user, require_privileged_mode
from backend.utils.common import utcnow

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


def _assert_workspace_owner(workspace_id: int, user_id: int):
    workspace = get_workspace_by_id(workspace_id)
    if not workspace or workspace.user_id != user_id:
        raise HTTPException(404, "Workspace not found")
    return workspace


@router.get("/{workspace_id}/journals", response_model=list[JournalOut])
async def list_journals(
    workspace_id: int,
    user: UserModel = Depends(get_current_user),
):
    workspace = _assert_workspace_owner(workspace_id, user.id)
    return [
        _fmt(journal, workspace.name)
        for journal in get_journals_by_workspace_id(workspace.id)
    ]


@router.get("/{workspace_id}/journals/{journal_id}")
async def get_journal(
    workspace_id: int, journal_id: int, user: UserModel = Depends(get_current_user)
):
    workspace = _assert_workspace_owner(workspace_id, user.id)
    journal = get_journal_by_id(journal_id)
    if not journal or journal.workspace_id != workspace.id:
        raise HTTPException(status_code=404, detail="Journal not found")
    return _fmt(journal, workspace.name)


@router.post("/{workspace_id}/journals", response_model=JournalOut, status_code=201)
async def add_journal(
    workspace_id: int,
    payload: JournalCreate,
    user: UserModel = Depends(get_current_user),
):
    workspace = _assert_workspace_owner(workspace_id, user.id)
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
    workspace_id: int,
    journal_id: int,
    payload: JournalUpdate,
    user: UserModel = Depends(get_current_user),
    _=Depends(require_privileged_mode),
):
    workspace = _assert_workspace_owner(workspace_id, user.id)
    journal = get_journal_by_id(journal_id)
    if not journal or journal.workspace_id != workspace.id:
        raise HTTPException(404, "Journal not found")
    updated = update_journal_name_and_description(
        journal.id, payload.name, payload.description
    )
    if updated is None:
        raise HTTPException(400, "Did not update journal")
    return _fmt(updated, workspace.name)


@router.delete("/{workspace_id}/journals/{journal_id}", status_code=204)
async def delete_journal(
    workspace_id: int,
    journal_id: int,
    current_user: UserModel = Depends(get_current_user),
    _=Depends(require_privileged_mode),
):
    workspace = _assert_workspace_owner(workspace_id, current_user.id)
    journal = get_journal_by_id(journal_id)
    if not journal or journal.workspace_id != workspace.id:
        raise HTTPException(404, "Journal not found")
    if not delete_journal_by_id(journal.id):
        raise HTTPException(404, "Journal not found")


@router.patch("/{workspace_id}/journals/{journal_id}/move", response_model=JournalOut)
async def move_journal(
    workspace_id: int,
    journal_id: int,
    payload: JournalMove,
    current_user: UserModel = Depends(get_current_user),
    _=Depends(require_privileged_mode),
):
    source = _assert_workspace_owner(workspace_id, current_user.id)
    destination = _assert_workspace_owner(payload.workspace_id, current_user.id)
    if workspace_id == payload.workspace_id:
        raise HTTPException(400, "Source and destination workspace are the same")
    journal = get_journal_by_id(journal_id)
    if not journal or journal.workspace_id != source.id:
        raise HTTPException(404, "Journal not found")
    moved = move_journal_record(journal.id, destination.id)
    if moved is None:
        raise HTTPException(404, "Journal not found")
    return _fmt(moved, destination.name)
