from datetime import datetime, timezone

from app.database import get_db
from app.models.workspace import WorkspaceCreate, WorkspaceOut, WorkspaceUpdate
from app.utils.auth import get_current_user, require_privileged_mode
from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException

router = APIRouter(prefix="/workspaces", tags=["workspaces"])


def _now():
    return datetime.now(timezone.utc)


def _fmt(doc) -> WorkspaceOut:
    return WorkspaceOut(
        id=str(doc["_id"]),
        name=doc["name"],
        created_at=doc.get("created_at", _now()),
    )


@router.get("", response_model=list[WorkspaceOut])
async def list_workspaces(
    current_user: dict = Depends(get_current_user),
    db=Depends(get_db),
):
    cursor = db["workspaces"].find({"user_id": current_user["id"]})
    return [_fmt(doc) async for doc in cursor]


@router.post("", response_model=WorkspaceOut, status_code=201)
async def create_workspace(
    payload: WorkspaceCreate,
    current_user: dict = Depends(get_current_user),
    db=Depends(get_db),
):
    doc = {"user_id": current_user["id"], "name": payload.name, "created_at": _now()}
    result = await db["workspaces"].insert_one(doc)
    doc["_id"] = result.inserted_id
    return _fmt(doc)


@router.patch("/{workspace_id}", response_model=WorkspaceOut)
async def update_workspace(
    workspace_id: str,
    payload: WorkspaceUpdate,
    current_user: dict = Depends(get_current_user),
    db=Depends(get_db),
):
    ws = await db["workspaces"].find_one(
        {"_id": ObjectId(workspace_id), "user_id": current_user["id"]}
    )
    if not ws:
        raise HTTPException(404, "Workspace not found")
    updates = {k: v for k, v in payload.model_dump().items() if v is not None}
    if updates:
        await db["workspaces"].update_one(
            {"_id": ObjectId(workspace_id)}, {"$set": updates}
        )
    ws.update(updates)
    return _fmt(ws)


@router.delete("/{workspace_id}", status_code=204)
async def delete_workspace(
    workspace_id: str,
    current_user: dict = Depends(require_privileged_mode),
    db=Depends(get_db),
):
    result = await db["workspaces"].delete_one(
        {"_id": ObjectId(workspace_id), "user_id": current_user["id"]}
    )
    if result.deleted_count == 0:
        raise HTTPException(404, "Workspace not found")
    # Cascade delete journals and their entries
    journal_ids = [
        str(j["_id"])
        async for j in db["journals"].find({"workspace_id": workspace_id}, {"_id": 1})
    ]
    await db["journals"].delete_many({"workspace_id": workspace_id})
    if journal_ids:
        await db["entries"].delete_many({"journal_id": {"$in": journal_ids}})
