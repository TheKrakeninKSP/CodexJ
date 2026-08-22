from fastapi import APIRouter, Depends, HTTPException

from backend.database.database import get_db
from backend.database.querying import (
    create_workspace,
    delete_workspace_by_id,
    get_workspace_by_id,
    get_workspaces_by_user_id,
    update_workspace_name,
)
from backend.database.structural import UserModel, WorkspaceModel
from backend.models.workspace import WorkspaceCreate, WorkspaceOut, WorkspaceUpdate
from backend.types import id_type
from backend.utils.auth import get_current_user, require_privileged_mode
from backend.utils.common import utcnow
from backend.utils.entry_bin import soft_delete_entries_for_workspace

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

    await soft_delete_entries_for_workspace(
        workspace,
        journal_docs,
        user_id=current_user["id"],
        db=db,
    )
    await db["journals"].delete_many({"workspace_id": workspace_id})
    await db["entry_types"].delete_many(
        {"user_id": current_user["id"], "workspace_id": workspace_id}
    )
    await db["workspaces"].delete_one({"_id": workspace["_id"]})
