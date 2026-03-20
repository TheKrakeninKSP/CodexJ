from datetime import datetime, timezone
from typing import Optional
from unicodedata import name

from app.database import get_db
from app.models.entry import EntryCreate, EntryModel, EntryUpdate
from app.utils.auth import get_current_user
from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, Query

router = APIRouter(tags=["entries"])


def _now():
    return datetime.now(timezone.utc)


async def _assert_journal_access(journal_id: str, user_id: str, db):
    """Verify the journal belongs to a workspace owned by the user."""
    journal = await db["journals"].find_one({"_id": ObjectId(journal_id)})
    if not journal:
        raise HTTPException(404, "Journal not found")
    ws = await db["workspaces"].find_one(
        {"_id": ObjectId(journal["workspace_id"]), "user_id": user_id}
    )
    if not ws:
        raise HTTPException(403, "Access denied")
    return journal


@router.get("/journals/{journal_id}/entries", response_model=list[EntryModel])
async def list_entries(
    journal_id: str,
    current_user: dict = Depends(get_current_user),
    db=Depends(get_db),
):
    await _assert_journal_access(journal_id, current_user["id"], db)
    cursor = db["entries"].find({"journal_id": journal_id}).sort("date_created", -1)
    return [EntryModel(**doc) async for doc in cursor]


@router.post(
    "/journals/{journal_id}/entries", response_model=EntryModel, status_code=201
)
async def create_entry(
    journal_id: str,
    payload: EntryCreate,
    current_user: dict = Depends(get_current_user),
    db=Depends(get_db),
):
    await _assert_journal_access(journal_id, current_user["id"], db)
    now = _now()
    entry_name = payload.name
    if not entry_name:
        entry_name = str(payload.date_created) or now.isoformat()
    entry = EntryModel(
        id="",
        journal_id=journal_id,
        type=payload.type,
        name=entry_name,
        body=payload.body,
        custom_metadata=payload.custom_metadata or [],
        media_refs=[],
        date_created=payload.date_created or now,
        updated_at=now,
    )
    result = await db["entries"].insert_one(dict(entry))
    entry.id = str(result.inserted_id)
    return entry


@router.get("/entries/{entry_id}", response_model=EntryModel)
async def get_entry(
    entry_id: str,
    current_user: dict = Depends(get_current_user),
    db=Depends(get_db),
):
    entry = await db["entries"].find_one({"_id": ObjectId(entry_id)})
    if not entry:
        raise HTTPException(404, "Entry not found")
    await _assert_journal_access(entry["journal_id"], current_user["id"], db)
    return entry


@router.patch("/entries/{entry_id}", response_model=EntryModel)
async def update_entry(
    entry_id: str,
    payload: EntryUpdate,
    current_user: dict = Depends(get_current_user),
    db=Depends(get_db),
):
    entry = await db["entries"].find_one({"_id": ObjectId(entry_id)})
    if not entry:
        raise HTTPException(404, "Entry not found")
    await _assert_journal_access(entry["journal_id"], current_user["id"], db)
    updates: dict = {"updated_at": _now()}
    if payload.type is not None:
        updates["type"] = payload.type
    if payload.name is not None:
        updates["name"] = payload.name
    if payload.body is not None:
        updates["body"] = payload.body
    if payload.custom_metadata is not None:
        updates["custom_metadata"] = [m.model_dump() for m in payload.custom_metadata]
    await db["entries"].update_one({"_id": ObjectId(entry_id)}, {"$set": updates})
    entry.update(updates)
    return entry


@router.delete("/entries/{entry_id}", status_code=204)
async def delete_entry(
    entry_id: str,
    current_user: dict = Depends(get_current_user),
    db=Depends(get_db),
):
    entry = await db["entries"].find_one({"_id": ObjectId(entry_id)})
    if not entry:
        raise HTTPException(404, "Entry not found")
    await _assert_journal_access(entry["journal_id"], current_user["id"], db)
    await db["entries"].delete_one({"_id": ObjectId(entry_id)})


@router.get("/entries/search", response_model=list[EntryModel])
async def search_entries(
    q: str = Query(..., min_length=1),
    journal_id: Optional[str] = Query(None),
    entry_type: Optional[str] = Query(None),
    name: Optional[str] = Query(None),
    from_date: Optional[datetime] = Query(None, alias="from"),
    to_date: Optional[datetime] = Query(None, alias="to"),
    current_user: dict = Depends(get_current_user),
    db=Depends(get_db),
):
    # Collect journal IDs the user owns
    user_ws_ids = [
        str(ws["_id"])
        async for ws in db["workspaces"].find(
            {"user_id": current_user["id"]}, {"_id": 1}
        )
    ]
    user_journal_ids = [
        str(j["_id"])
        async for j in db["journals"].find(
            {"workspace_id": {"$in": user_ws_ids}}, {"_id": 1}
        )
    ]

    if not user_journal_ids:
        return []

    match: dict = {"journal_id": {"$in": user_journal_ids}}
    if journal_id:
        if journal_id not in user_journal_ids:
            raise HTTPException(403, "Access denied")
        match["journal_id"] = journal_id
    if entry_type:
        match["type"] = entry_type
    if name:
        match["name"] = {"$regex": name, "$options": "i"}
    if from_date or to_date:
        date_filter: dict = {}
        if from_date:
            date_filter["$gte"] = from_date
        if to_date:
            date_filter["$lte"] = to_date
        match["date_created"] = date_filter

    # Atlas Search using $search — falls back to $regex if no search index exists
    try:
        pipeline = [
            {
                "$search": {
                    "index": "entries_search",
                    "text": {"query": q, "path": ["type", "custom_metadata.value"]},
                }
            },
            {"$match": match},
            {"$sort": {"date_created": -1}},
            {"$limit": 100},
        ]
        cursor = db["entries"].aggregate(pipeline)
        results = [EntryModel(**doc) async for doc in cursor]
    except Exception:
        # Fallback: simple regex search
        match["$or"] = [
            {"type": {"$regex": q, "$options": "i"}},
            {"custom_metadata.value": {"$regex": q, "$options": "i"}},
        ]
        cursor = db["entries"].find(match).sort("date_created", -1).limit(100)
        results = [EntryModel(**doc) async for doc in cursor]

    return results
