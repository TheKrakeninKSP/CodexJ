import json
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException, Query

from backend.database.querying import (
    count_deleted_entries,
    create_entry,
    create_tag,
    get_entries_by_journal_id,
    get_entries_for_user,
    get_entry_by_id,
    get_tag_by_name,
)
from backend.database.querying import search_entries as search_entry_records
from backend.database.querying import update_entry as update_entry_record
from backend.database.structural import EntryModel, TagModel, UserModel
from backend.models.entry import (
    BinCountOut,
    EntryCreate,
    EntryMove,
    EntryMoveRequest,
    EntryOut,
    EntryPreview,
    EntryRestore,
    EntryRestoreRequest,
    EntrySearch,
    EntrySearchRequest,
    EntryUpdate,
    EntryUpdateRequest,
)
from backend.type_defs import id_type
from backend.utils.auth import (
    assert_journal_access,
    get_current_user,
    require_privileged_mode,
)
from backend.utils.common import utcnow
from backend.utils.data_management import recursive_delete_entry, soft_delete_entry
from backend.utils.entry_utils import extract_media_refs

router = APIRouter(tags=["entries"])


def _json_value(value: str | None, default: Any) -> Any:
    if not value:
        return default
    try:
        return json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return default


def _ensure_utc(dt: datetime) -> datetime:
    """Ensure a datetime is timezone-aware with UTC timezone."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


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
        date_created=_ensure_utc(entry.date_created),
        updated_at=_ensure_utc(entry.updated_at),
        is_deleted=entry.is_deleted,
        deleted_at=_ensure_utc(entry.deleted_at) if entry.deleted_at else None,
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
            date_created=_ensure_utc(entry.date_created),
            updated_at=_ensure_utc(entry.updated_at),
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
    tags = json.dumps(payload.tags)
    for name in payload.tags:
        if get_tag_by_name(name) is not None:
            continue
        tag = TagModel(name=name, created_at=utcnow())
        create_tag(tag)
    entry = EntryModel(
        journal_id=journal_id,
        tags=tags,
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


@router.post("/entries/search", response_model=list[EntryOut])
async def search_entries(
    search_filter: EntrySearchRequest = Body(...),
    limit: int = Query(100, ge=1, le=200),
    offset: int = Query(0, ge=0),
    user: UserModel = Depends(get_current_user),
):
    search_query = (search_filter.q or "").strip()
    if search_filter.q is not None and not search_query:
        raise HTTPException(422, "Query cannot be empty")
    if (
        search_filter.from_date
        and search_filter.to_date
        and search_filter.from_date > search_filter.to_date
    ):
        raise HTTPException(400, "Invalid date range: 'from' must be <= 'to'")
    if search_filter.journal_id is not None:
        assert_journal_access(search_filter.journal_id, user.id)
    entries = search_entry_records(
        user_id=user.id,
        search_filter=EntrySearch(
            q=search_query,
            journal_id=search_filter.journal_id,
            tags=search_filter.tags,
            name=search_filter.name,
            from_date=search_filter.from_date,
            to_date=search_filter.to_date,
        ),
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
    payload: EntryUpdateRequest,
    user: UserModel = Depends(get_current_user),
):
    entry = _get_live_entry(entry_id)
    assert_journal_access(entry.journal_id, user.id)

    # check media refs validity
    payload.media_refs = extract_media_refs(payload.body)

    # Build update object with only explicitly set fields
    update_dict = {}
    if payload.tags is not None:
        update_dict["tags"] = json.dumps(payload.tags)
    if payload.body is not None:
        update_dict["body"] = json.dumps(payload.body)
    if payload.name is not None:
        update_dict["name"] = payload.name
    if payload.custom_metadata is not None:
        update_dict["custom_metadata"] = json.dumps(payload.custom_metadata)
    if payload.timezone is not None:
        update_dict["timezone"] = payload.timezone
    if payload.date_created is not None:
        update_dict["date_created"] = payload.date_created
    if payload.media_refs is not None:
        update_dict["media_refs"] = json.dumps(payload.media_refs)

    update_object = EntryUpdate(**update_dict)
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
    journal, _ = assert_journal_access(payload.journal_id, user.id)
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
    _, _ = assert_journal_access(entry.journal_id, user.id)
    is_deleted = await soft_delete_entry(entry.id)
    if not is_deleted:
        raise HTTPException(400, "Failed to delete entry")


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
    await recursive_delete_entry(entry.id, hard=True)


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
