from datetime import datetime, timezone

from app.database import get_db
from app.models.entry_type import EntryTypeCreate, EntryTypeOut
from app.utils.auth import get_current_user
from bson import ObjectId
from bson.errors import InvalidId
from fastapi import APIRouter, Depends, HTTPException

router = APIRouter(prefix="/workspaces", tags=["entry_types"])


def _now():
    return datetime.now(timezone.utc)


def _oid(value: str, field_name: str) -> ObjectId:
    try:
        return ObjectId(value)
    except InvalidId as exc:
        raise HTTPException(400, f"Invalid {field_name}") from exc


async def _assert_workspace_owner(workspace_id: str, user_id: str, db):
    workspace = await db["workspaces"].find_one(
        {"_id": _oid(workspace_id, "workspace_id"), "user_id": user_id}
    )
    if not workspace:
        raise HTTPException(404, "Workspace not found")
    return workspace


async def _workspace_journal_ids(workspace_id: str, db) -> list[str]:
    return [
        str(doc["_id"])
        async for doc in db["journals"].find({"workspace_id": workspace_id}, {"_id": 1})
    ]


async def _backfill_workspace_entry_types(workspace_id: str, user_id: str, db) -> None:
    existing_names = {
        doc["name"]
        async for doc in db["entry_types"].find(
            {"user_id": user_id, "workspace_id": workspace_id},
            {"name": 1},
        )
        if isinstance(doc.get("name"), str) and doc["name"].strip()
    }

    journal_ids = await _workspace_journal_ids(workspace_id, db)
    if not journal_ids:
        return

    missing_names: set[str] = set()
    pipeline = [
        {"$match": {"journal_id": {"$in": journal_ids}}},
        {"$unwind": "$tags"},
        {"$group": {"_id": "$tags"}},
    ]
    async for doc in db["entries"].aggregate(pipeline):
        tag = doc.get("_id")
        if not isinstance(tag, str):
            continue
        normalized = tag.strip()
        if not normalized or normalized in existing_names:
            continue
        missing_names.add(normalized)

    if missing_names:
        await db["entry_types"].insert_many(
            [
                {
                    "user_id": user_id,
                    "workspace_id": workspace_id,
                    "name": name,
                    "created_at": _now(),
                }
                for name in sorted(missing_names)
            ]
        )


async def _entry_counts_by_type(workspace_id: str, db) -> dict[str, int]:
    journal_ids = await _workspace_journal_ids(workspace_id, db)
    if not journal_ids:
        return {}

    pipeline = [
        {"$match": {"journal_id": {"$in": journal_ids}, "is_deleted": {"$ne": True}}},
        {"$unwind": "$tags"},
        {"$group": {"_id": "$tags", "entry_count": {"$addToSet": "$_id"}}},
        {"$project": {"entry_count": {"$size": "$entry_count"}}},
    ]

    counts: dict[str, int] = {}
    async for doc in db["entries"].aggregate(pipeline):
        name = doc.get("_id")
        if isinstance(name, str) and name.strip():
            counts[name] = int(doc.get("entry_count", 0))
    return counts


@router.get("/{workspace_id}/entry-types", response_model=list[EntryTypeOut])
async def list_entry_types(
    workspace_id: str,
    current_user: dict = Depends(get_current_user),
    db=Depends(get_db),
):
    await _assert_workspace_owner(workspace_id, current_user["id"], db)
    await _backfill_workspace_entry_types(workspace_id, current_user["id"], db)
    entry_counts = await _entry_counts_by_type(workspace_id, db)
    cursor = (
        db["entry_types"]
        .find({"user_id": current_user["id"], "workspace_id": workspace_id})
        .sort("name", 1)
    )
    return [
        EntryTypeOut(
            id=str(doc["_id"]),
            name=doc["name"],
            entry_count=entry_counts.get(doc["name"], 0),
        )
        async for doc in cursor
    ]


@router.post(
    "/{workspace_id}/entry-types", response_model=EntryTypeOut, status_code=201
)
async def create_entry_type(
    workspace_id: str,
    payload: EntryTypeCreate,
    current_user: dict = Depends(get_current_user),
    db=Depends(get_db),
):
    await _assert_workspace_owner(workspace_id, current_user["id"], db)
    # Idempotent — return existing if the name already exists for this workspace
    existing = await db["entry_types"].find_one(
        {
            "user_id": current_user["id"],
            "workspace_id": workspace_id,
            "name": payload.name,
        }
    )
    if existing:
        return EntryTypeOut(
            id=str(existing["_id"]), name=existing["name"], entry_count=0
        )

    doc = {
        "user_id": current_user["id"],
        "workspace_id": workspace_id,
        "name": payload.name,
        "created_at": _now(),
    }
    result = await db["entry_types"].insert_one(doc)
    return EntryTypeOut(id=str(result.inserted_id), name=payload.name, entry_count=0)


@router.delete("/{workspace_id}/entry-types/{type_id}", status_code=204)
async def delete_entry_type(
    workspace_id: str,
    type_id: str,
    current_user: dict = Depends(get_current_user),
    db=Depends(get_db),
):
    await _assert_workspace_owner(workspace_id, current_user["id"], db)
    entry_type = await db["entry_types"].find_one(
        {
            "_id": _oid(type_id, "type_id"),
            "user_id": current_user["id"],
            "workspace_id": workspace_id,
        }
    )
    if not entry_type:
        raise HTTPException(404, "Entry type not found")

    journal_ids = await _workspace_journal_ids(workspace_id, db)
    if journal_ids:
        in_use = await db["entries"].find_one(
            {
                "journal_id": {"$in": journal_ids},
                "tags": entry_type["name"],
            },
            {"_id": 1},
        )
        if in_use:
            raise HTTPException(
                409,
                "Cannot delete entry type: still referenced by one or more entries",
            )

    result = await db["entry_types"].delete_one({"_id": entry_type["_id"]})
    if result.deleted_count == 0:
        raise HTTPException(404, "Entry type not found")
