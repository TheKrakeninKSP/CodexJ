from fastapi import APIRouter, Depends, HTTPException

from backend.database.querying import (
    create_workspace,
    delete_entry_by_id,
    delete_journal_by_id,
    delete_media_by_id,
    delete_workspace_by_id,
    get_entries_by_journal_id,
    get_journals_by_workspace_id,
    get_media_by_entry_id,
    get_workspace_by_id,
    get_workspaces_by_user_id,
    update_workspace_name,
)
from backend.database.structural import UserModel, WorkspaceModel
from backend.models.workspace import WorkspaceCreate, WorkspaceOut, WorkspaceUpdate
from backend.type_defs import id_type
from backend.utils.auth import get_current_user, require_privileged_mode
from backend.utils.common import utcnow

router = APIRouter(prefix="/workspaces", tags=["workspaces"])


@router.get("", response_model=list[WorkspaceOut])
async def list_workspaces(user: UserModel = Depends(get_current_user)):
    workspaces = get_workspaces_by_user_id(user.id)
    workspaces_out = []
    for workspace in workspaces:
        workspace_out = WorkspaceOut(
            id=workspace.id, name=workspace.name, created_at=workspace.created_at
        )
        workspaces_out.append(workspace_out)
    return workspaces_out


@router.post("", response_model=WorkspaceOut, status_code=201)
async def add_workspace(
    payload: WorkspaceCreate, user: UserModel = Depends(get_current_user)
):
    workspace = WorkspaceModel(user_id=user.id, name=payload.name, created_at=utcnow())
    workspace_id = create_workspace(workspace)
    workspace_out = WorkspaceOut(
        id=workspace_id, name=workspace.name, created_at=workspace.created_at
    )
    return workspace_out


@router.patch("/{workspace_id}", response_model=WorkspaceOut)
async def update_workspace(
    workspace_id: id_type,
    payload: WorkspaceUpdate,
    user: UserModel = Depends(get_current_user),
    _=Depends(require_privileged_mode),
):
    workspace = get_workspace_by_id(workspace_id)
    if not workspace:
        raise HTTPException(404, "Workspace not found")
    if workspace.user_id != user.id:
        raise HTTPException(403, "Forbidden access")

    updated = False
    updated_workspace = WorkspaceOut(
        id=workspace.id, name=workspace.name, created_at=workspace.created_at
    )
    if payload.name:
        if update_workspace_name(workspace_id, payload.name):
            updated = True
            updated_workspace.name = payload.name

    if updated:
        return update_workspace
    else:
        raise HTTPException(400, "Did not update workspace")


@router.delete("/{workspace_id}", status_code=204)
async def delete_workspace(
    workspace_id: id_type,
    user: UserModel = Depends(get_current_user),
    _=Depends(require_privileged_mode),
):
    workspace = get_workspace_by_id(workspace_id)
    if not workspace:
        raise HTTPException(404, "Workspace not found")
    if workspace.user_id != user.id:
        raise HTTPException(403, "Forbidden access")

    journals_of_workspace = []
    entries_of_workspace = []
    media_of_workspace = []
    journals_in_workspace = get_journals_by_workspace_id(workspace.id)
    journals_of_workspace.extend(journals_in_workspace)
    for journal in journals_in_workspace:
        entries_in_journal = get_entries_by_journal_id(journal.id)
        entries_of_workspace.extend(entries_in_journal)
        for entry in entries_in_journal:
            media_in_entry = get_media_by_entry_id(entry.id)
            media_of_workspace.extend(media_in_entry)

    for media in media_of_workspace:
        delete_media_by_id(media.id)
    for entry in entries_of_workspace:
        delete_entry_by_id(entry.id)
    for journal in journals_of_workspace:
        delete_journal_by_id(journal.id)
    delete_workspace_by_id(workspace.id)
