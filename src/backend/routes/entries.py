import json
from datetime import datetime
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from backend.database.querying import (
    count_deleted_entries,
    create_entry,
    get_entries_by_journal_id,
    get_entries_for_user,
    get_entry_by_id,
)
from backend.database.querying import search_entries as search_entry_records
from backend.database.querying import update_entry as update_entry_record
from backend.database.structural import EntryModel, UserModel
from backend.models.entry import (
    BinCountOut,
    EntryCreate,
    EntryMove,
    EntryMoveRequest,
    EntryOut,
    EntryPreview,
    EntryRestore,
    EntryRestoreRequest,
    EntrySoftDelete,
    EntryUpdate,
)
from backend.type_defs import id_type
from backend.utils.auth import (
    assert_journal_access,
    get_current_user,
    require_privileged_mode,
)
from backend.utils.common import utcnow
from backend.utils.data_management import recursive_delete_entry
from backend.utils.entry_utils import extract_media_refs

router = APIRouter(tags=["entries"])


def _json_value(value: str | None, default: Any) -> Any:
    if not value:
        return default
    try:
        return json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return default


def _fmt(entry: EntryModel) -> EntryOut:
    return EntryOut(
        id=entry.id,
        journal_id=entry.journal_id,
        tags=_json_value(entry.tags, []),
        name=entry.name,
        timezone=entry.timezone,
        body=_json_value(entry.body, {}),
        custom_metadata=_json_value(entry.custom_metadata, []),
        media_refs=_json_value(entry.media_refs, []),
        date_created=entry.date_created,
        updated_at=entry.updated_at,
        is_deleted=entry.is_deleted,
        deleted_at=entry.deleted_at,
        deleted_from_workspace_id=entry.deleted_from_workspace_id,
        deleted_from_journal_id=entry.deleted_from_journal_id,
    )


def _get_live_entry(entry_id: id_type) -> EntryModel:
    entry = get_entry_by_id(entry_id)
    if not entry or entry.is_deleted:
        raise HTTPException(404, "Entry not found")
    return entry


@router.get("/journals/{journal_id}/entries", response_model=list[EntryPreview])
async def list_entries(
    journal_id: id_type,
    user: UserModel = Depends(get_current_user),
):
    assert_journal_access(journal_id, user.id)
    entries = [
        entry for entry in get_entries_by_journal_id(journal_id) if not entry.is_deleted
    ]
    return [
        EntryPreview(
            id=entry.id,
            journal_id=entry.journal_id,
            tags=_json_value(entry.tags, []),
            name=entry.name,
            date_created=entry.date_created,
            updated_at=entry.updated_at,
        )
        for entry in entries
    ]


@router.post("/journals/{journal_id}/entries", response_model=EntryOut, status_code=201)
async def add_entry(
    journal_id: id_type,
    payload: EntryCreate,
    user: UserModel = Depends(get_current_user),
):
    assert_journal_access(journal_id, user.id)
    now = utcnow()
    entry = EntryModel(
        journal_id=journal_id,
        tags=json.dumps(payload.tags),
        name=payload.name,
        timezone=payload.timezone,
        body=json.dumps(payload.body),
        custom_metadata=json.dumps(
            [item.model_dump() for item in payload.custom_metadata]
        ),
        media_refs=json.dumps(extract_media_refs(payload.body)),
        date_created=payload.date_created or now,
        updated_at=now,
    )
    create_entry(entry)
    return _fmt(entry)


@router.get("/entries/search", response_model=list[EntryOut])
async def search_entries(
    q: Optional[str] = Query(None, min_length=1),
    journal_id: Optional[id_type] = Query(None),
    entry_type: Optional[str] = Query(None),
    name: Optional[str] = Query(None),
    from_date: Optional[datetime] = Query(None, alias="from"),
    to_date: Optional[datetime] = Query(None, alias="to"),
    limit: int = Query(100, ge=1, le=200),
    offset: int = Query(0, ge=0),
    user: UserModel = Depends(get_current_user),
):
    search_query = (q or "").strip()
    if q is not None and not search_query:
        raise HTTPException(422, "Query cannot be empty")
    if from_date and to_date and from_date > to_date:
        raise HTTPException(400, "Invalid date range: 'from' must be <= 'to'")
    if journal_id is not None:
        assert_journal_access(journal_id, user.id)
    entries = search_entry_records(
        user.id,
        query=search_query,
        journal_id=journal_id,
        entry_type=entry_type,
        name=name,
        from_date=from_date,
        to_date=to_date,
        offset=offset,
        limit=limit,
    )
    return [_fmt(entry) for entry in entries]


@router.get("/entries/bin", response_model=list[EntryOut])
async def list_deleted_entries(user: UserModel = Depends(get_current_user)):
    return [_fmt(entry) for entry in get_entries_for_user(user.id, deleted=True)]


@router.get("/entries/bin/count", response_model=BinCountOut)
async def count_deleted_entries_route(user: UserModel = Depends(get_current_user)):
    return BinCountOut(count=count_deleted_entries(user.id))


@router.get("/entries/{entry_id}", response_model=EntryOut)
async def get_entry(entry_id: id_type, user: UserModel = Depends(get_current_user)):
    entry = _get_live_entry(entry_id)
    assert_journal_access(entry.journal_id, user.id)
    return _fmt(entry)


@router.patch("/entries/{entry_id}", response_model=EntryOut)
async def update_entry(
    entry_id: id_type,
    payload: EntryUpdate,
    user: UserModel = Depends(get_current_user),
):
    entry = _get_live_entry(entry_id)
    assert_journal_access(entry.journal_id, user.id)
    updates: dict[str, Any] = {"updated_at": utcnow()}
    if payload.tags is not None:
        updates["tags"] = json.dumps(payload.tags)
    if payload.name is not None:
        updates["name"] = payload.name
    if payload.body is not None:
        updates["body"] = json.dumps(payload.body)
        updates["media_refs"] = json.dumps(extract_media_refs(payload.body))
    if payload.custom_metadata is not None:
        updates["custom_metadata"] = json.dumps(
            [item.model_dump() for item in payload.custom_metadata]
        )
    if payload.timezone is not None:
        updates["timezone"] = payload.timezone
    if payload.date_created is not None:
        updates["date_created"] = payload.date_created
    update_object = EntryUpdate.model_validate(updates)
    updated = update_entry_record(entry.id, update_object)
    return _fmt(updated) if updated else _fmt(entry)


@router.post("/entries/{entry_id}/restore", response_model=EntryOut)
async def restore_entry(
    entry_id: id_type,
    payload: EntryRestoreRequest,
    user: UserModel = Depends(get_current_user),
    _=Depends(require_privileged_mode),
):
    entry = get_entry_by_id(entry_id)
    if not entry or not entry.is_deleted:
        raise HTTPException(404, "Deleted entry not found")
    journal, workspace = assert_journal_access(payload.journal_id, user.id)
    update_object = EntryRestore(journal_id=journal.id)
    updated = update_entry_record(entry.id, update_object)
    if not updated:
        raise HTTPException(400, "Did not restore entry")
    return _fmt(updated)


@router.delete("/entries/{entry_id}", status_code=204)
async def delete_entry(
    entry_id: id_type,
    user: UserModel = Depends(get_current_user),
    _=Depends(require_privileged_mode),
):
    entry = _get_live_entry(entry_id)
    journal, workspace = assert_journal_access(entry.journal_id, user.id)
    timestamp = utcnow()
    soft_delete_object = EntrySoftDelete(
        is_deleted=True,
        deleted_at=timestamp,
        deleted_from_workspace_id=workspace.id,
        deleted_from_journal_id=journal.id,
        updated_at=timestamp,
    )
    update_entry_record(entry.id, soft_delete_object)


@router.delete("/entries/{entry_id}/purge", status_code=204)
async def purge_entry(
    entry_id: id_type,
    user: UserModel = Depends(get_current_user),
    _=Depends(require_privileged_mode),
):
    entry = get_entry_by_id(entry_id)
    if not entry or not entry.is_deleted:
        raise HTTPException(404, "Deleted entry not found")
    if not entry.deleted_from_journal_id:
        raise HTTPException(400, "Entry cannot be purged: no associated journal")
    if not assert_journal_access(entry.deleted_from_journal_id, user.id):
        raise HTTPException(403, "Access denied to the associated journal")
    await recursive_delete_entry(entry.id)


@router.patch("/entries/{entry_id}/move", response_model=EntryOut)
async def move_entry(
    entry_id: id_type,
    payload: EntryMoveRequest,
    user: UserModel = Depends(get_current_user),
    _=Depends(require_privileged_mode),
):
    entry = _get_live_entry(entry_id)
    assert_journal_access(entry.journal_id, user.id)
    assert_journal_access(payload.journal_id, user.id)
    move_object = EntryMove(journal_id=payload.journal_id)
    updated = update_entry_record(entry.id, move_object)
    if not updated:
        raise HTTPException(400, "Did not move entry")
    return _fmt(updated)
