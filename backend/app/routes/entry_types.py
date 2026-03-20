from datetime import datetime, timezone

from app.database import get_db
from app.models.entry_type import EntryTypeCreate, EntryTypeOut
from app.utils.auth import get_current_user
from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException

router = APIRouter(prefix="/entry-types", tags=["entry_types"])


def _now():
    return datetime.now(timezone.utc)


@router.get("", response_model=list[EntryTypeOut])
async def list_entry_types(
    current_user: dict = Depends(get_current_user),
    db=Depends(get_db),
):
    cursor = db["entry_types"].find({"user_id": current_user["id"]}).sort("name", 1)
    return [EntryTypeOut(id=str(doc["_id"]), name=doc["name"]) async for doc in cursor]


@router.post("", response_model=EntryTypeOut, status_code=201)
async def create_entry_type(
    payload: EntryTypeCreate,
    current_user: dict = Depends(get_current_user),
    db=Depends(get_db),
):
    # Idempotent — return existing if the name already exists for this user
    existing = await db["entry_types"].find_one(
        {"user_id": current_user["id"], "name": payload.name}
    )
    if existing:
        return EntryTypeOut(id=str(existing["_id"]), name=existing["name"])

    doc = {"user_id": current_user["id"], "name": payload.name, "created_at": _now()}
    result = await db["entry_types"].insert_one(doc)
    return EntryTypeOut(id=str(result.inserted_id), name=payload.name)


@router.delete("/{type_id}", status_code=204)
async def delete_entry_type(
    type_id: str,
    current_user: dict = Depends(get_current_user),
    db=Depends(get_db),
):
    result = await db["entry_types"].delete_one(
        {"_id": ObjectId(type_id), "user_id": current_user["id"]}
    )
    if result.deleted_count == 0:
        raise HTTPException(404, "Entry type not found")
