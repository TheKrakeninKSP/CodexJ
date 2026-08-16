from datetime import datetime, timezone


def _now() -> datetime:
    return datetime.now(timezone.utc)


async def soft_delete_entry_document(
    entry_doc: dict,
    *,
    user_id: str,
    workspace_id: str,
    workspace_name: str | None,
    journal_name: str | None,
    db,
    deleted_at: datetime | None = None,
) -> None:
    timestamp = deleted_at or _now()
    await db["entries"].update_one(
        {"_id": entry_doc["_id"]},
        {
            "$set": {
                "user_id": user_id,
                "is_deleted": True,
                "deleted_at": timestamp,
                "deleted_from_workspace_id": workspace_id,
                "deleted_from_workspace_name": workspace_name,
                "deleted_from_journal_id": entry_doc.get("journal_id"),
                "deleted_from_journal_name": journal_name,
                "updated_at": timestamp,
            }
        },
    )


async def soft_delete_entries_for_journal(
    journal_doc: dict,
    *,
    user_id: str,
    workspace_id: str,
    workspace_name: str | None,
    db,
    deleted_at: datetime | None = None,
) -> int:
    journal_id = str(journal_doc["_id"])
    deleted_count = 0

    async for entry_doc in db["entries"].find(
        {"journal_id": journal_id, "is_deleted": {"$ne": True}}
    ):
        await soft_delete_entry_document(
            entry_doc,
            user_id=user_id,
            workspace_id=workspace_id,
            workspace_name=workspace_name,
            journal_name=journal_doc.get("name"),
            db=db,
            deleted_at=deleted_at,
        )
        deleted_count += 1

    return deleted_count


async def soft_delete_entries_for_workspace(
    workspace_doc: dict,
    journal_docs: list[dict],
    *,
    user_id: str,
    db,
    deleted_at: datetime | None = None,
) -> int:
    deleted_count = 0
    workspace_id = str(workspace_doc["_id"])
    workspace_name = workspace_doc.get("name")

    for journal_doc in journal_docs:
        deleted_count += await soft_delete_entries_for_journal(
            journal_doc,
            user_id=user_id,
            workspace_id=workspace_id,
            workspace_name=workspace_name,
            db=db,
            deleted_at=deleted_at,
        )

    return deleted_count
