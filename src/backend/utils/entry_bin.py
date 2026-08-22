from datetime import datetime, timezone

from backend.database.querying import get_entries_by_journal_id, update_entry
from backend.database.structural import EntryModel, JournalModel, WorkspaceModel


def _now() -> datetime:
    return datetime.now(timezone.utc)


def soft_delete_entry(
    entry: EntryModel,
    *,
    workspace_id: int,
    journal_id: int,
    deleted_at: datetime | None = None,
) -> EntryModel | None:
    timestamp = deleted_at or _now()
    return update_entry(
        entry.id,
        is_deleted=True,
        deleted_at=timestamp,
        deleted_from_workspace_id=workspace_id,
        deleted_from_journal_id=journal_id,
        updated_at=timestamp,
    )


def soft_delete_entries_for_journal(
    journal: JournalModel,
    *,
    workspace: WorkspaceModel,
    deleted_at: datetime | None = None,
) -> int:
    deleted_count = 0
    for entry in get_entries_by_journal_id(journal.id):
        if entry.is_deleted:
            continue
        if soft_delete_entry(
            entry,
            workspace_id=workspace.id,
            journal_id=journal.id,
            deleted_at=deleted_at,
        ):
            deleted_count += 1
    return deleted_count
