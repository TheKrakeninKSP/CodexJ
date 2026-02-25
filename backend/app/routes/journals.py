from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException
from datetime import datetime, timezone

from app.database import get_db
from app.models.journal import JournalCreate, JournalUpdate, JournalOut
from app.utils.auth import get_current_user

router = APIRouter(prefix="/workspaces", tags=["journals"])


def _now():
    return datetime.now(timezone.utc)


def _fmt(doc) -> JournalOut:
    return JournalOut(
        id=str(doc["_id"]),
        workspace_id=doc["workspace_id"],
        name=doc["name"],
        description=doc.get("description"),
        created_at=doc.get("created_at", _now()),
    )


async def _assert_workspace_owner(workspace_id: str, user_id: str, db):
    ws = await db["workspaces"].find_one(
        {"_id": ObjectId(workspace_id), "user_id": user_id}
    )
    if not ws:
        raise HTTPException(404, "Workspace not found")
    return ws


@router.get("/{workspace_id}/journals", response_model=list[JournalOut])
async def list_journals(
    workspace_id: str,
    current_user: dict = Depends(get_current_user),
    db=Depends(get_db),
):
    await _assert_workspace_owner(workspace_id, current_user["id"], db)
    cursor = db["journals"].find({"workspace_id": workspace_id})
    return [_fmt(doc) async for doc in cursor]


@router.post("/{workspace_id}/journals", response_model=JournalOut, status_code=201)
async def create_journal(
    workspace_id: str,
    payload: JournalCreate,
    current_user: dict = Depends(get_current_user),
    db=Depends(get_db),
):
    await _assert_workspace_owner(workspace_id, current_user["id"], db)
    doc = {
        "workspace_id": workspace_id,
        "name": payload.name,
        "description": payload.description,
        "created_at": _now(),
    }
    result = await db["journals"].insert_one(doc)
    doc["_id"] = result.inserted_id
    return _fmt(doc)


@router.patch("/{workspace_id}/journals/{journal_id}", response_model=JournalOut)
async def update_journal(
    workspace_id: str,
    journal_id: str,
    payload: JournalUpdate,
    current_user: dict = Depends(get_current_user),
    db=Depends(get_db),
):
    await _assert_workspace_owner(workspace_id, current_user["id"], db)
    journal = await db["journals"].find_one(
        {"_id": ObjectId(journal_id), "workspace_id": workspace_id}
    )
    if not journal:
        raise HTTPException(404, "Journal not found")
    updates = {k: v for k, v in payload.model_dump().items() if v is not None}
    if updates:
        await db["journals"].update_one({"_id": ObjectId(journal_id)}, {"$set": updates})
    journal.update(updates)
    return _fmt(journal)


@router.delete("/{workspace_id}/journals/{journal_id}", status_code=204)
async def delete_journal(
    workspace_id: str,
    journal_id: str,
    current_user: dict = Depends(get_current_user),
    db=Depends(get_db),
):
    await _assert_workspace_owner(workspace_id, current_user["id"], db)
    result = await db["journals"].delete_one(
        {"_id": ObjectId(journal_id), "workspace_id": workspace_id}
    )
    if result.deleted_count == 0:
        raise HTTPException(404, "Journal not found")
    await db["entries"].delete_many({"journal_id": journal_id})
