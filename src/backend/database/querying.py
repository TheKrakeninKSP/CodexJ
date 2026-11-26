# an abstraction layer to query the database
# SQLite database implementation

from collections.abc import Iterable
from datetime import datetime
from typing import Union

from sqlalchemy import (
    LargeBinary,
    cast,
    create_engine,
    delete,
    func,
    or_,
    select,
)
from sqlalchemy.orm import sessionmaker

from backend.constants import SQLITE_DB_URL
from backend.database.structural import (
    EntryModel,
    EntryVersionModel,
    JournalModel,
    MediaModel,
    TagModel,
    UserModel,
    WorkspaceModel,
)
from backend.models.entry import (
    EntryMove,
    EntryRestore,
    EntrySearch,
    EntrySoftDelete,
    EntryUpdate,
)
from backend.type_defs import id_type, theme_type
from backend.utils.common import utcnow

engine = create_engine(SQLITE_DB_URL, future=True)
# expire_on_commit=False: sessions here are short-lived per call and objects
# are returned for use after the session closes, so attributes must not expire.
Session = sessionmaker(bind=engine, future=True, expire_on_commit=False)


# User functions
def create_user(user: UserModel) -> id_type:
    """takes in object of User class and returns user id of the newly created user"""
    with Session() as session:
        session.add(user)
        session.commit()
        return user.id


def get_user_by_username(username: str) -> UserModel | None:
    with Session() as session:
        return session.query(UserModel).filter_by(username=username).first()


def update_user_theme(user_id: id_type, theme: theme_type) -> bool:
    with Session() as session:
        user = session.get(UserModel, user_id)

        if user is None:
            return False

        user.theme = theme
        session.commit()
        return True


def record_user_login(user_id: id_type) -> None:
    with Session() as session:
        user = session.get(UserModel, user_id)
        if user is None:
            return
        user.last_login_at = utcnow()
        session.commit()


def set_user_admin(username: str, is_admin: bool) -> bool:
    """Grant or revoke admin. Returns False if the user doesn't exist."""
    with Session() as session:
        user = session.query(UserModel).filter_by(username=username).first()
        if user is None:
            return False
        user.is_admin = is_admin
        session.commit()
        return True


def get_all_users() -> list[UserModel]:
    with Session() as session:
        return list(session.scalars(select(UserModel).order_by(UserModel.created_at)))


def _byte_len(column):
    # SQLite length() on TEXT counts characters; casting to BLOB counts bytes.
    return func.coalesce(func.length(cast(column, LargeBinary)), 0)


def get_entry_stats_by_user() -> dict[id_type, tuple[int, int]]:
    """Map user_id -> (entry_count, text_bytes) across all their entries
    (including binned ones) and saved entry versions."""
    with Session() as session:
        entry_rows = session.execute(
            select(
                WorkspaceModel.user_id,
                func.count(EntryModel.id),
                func.sum(
                    _byte_len(EntryModel.body)
                    + _byte_len(EntryModel.custom_metadata)
                    + _byte_len(EntryModel.tags)
                ),
            )
            .join(JournalModel, EntryModel.journal_id == JournalModel.id)
            .join(WorkspaceModel, JournalModel.workspace_id == WorkspaceModel.id)
            .group_by(WorkspaceModel.user_id)
        ).all()
        version_rows = session.execute(
            select(
                WorkspaceModel.user_id,
                func.sum(_byte_len(EntryVersionModel.body)),
            )
            .join(EntryModel, EntryVersionModel.entry_id == EntryModel.id)
            .join(JournalModel, EntryModel.journal_id == JournalModel.id)
            .join(WorkspaceModel, JournalModel.workspace_id == WorkspaceModel.id)
            .group_by(WorkspaceModel.user_id)
        ).all()

    stats: dict[id_type, tuple[int, int]] = {
        user_id: (count, int(text_bytes or 0))
        for user_id, count, text_bytes in entry_rows
    }
    for user_id, version_bytes in version_rows:
        count, text_bytes = stats.get(user_id, (0, 0))
        stats[user_id] = (count, text_bytes + int(version_bytes or 0))
    return stats


def delete_user_by_id(user_id: id_type) -> bool:
    with Session() as session:
        user = session.get(UserModel, user_id)
        if user is None:
            return False

        session.delete(user)
        session.commit()
        return True


# Workspace functions
def create_workspace(workspace: WorkspaceModel) -> id_type:
    """takes in object of Workspace class and returns workspace id of the newly created workspace"""
    with Session() as session:
        session.add(workspace)
        session.commit()
        return workspace.id


def get_workspace_by_id(workspace_id: id_type) -> WorkspaceModel | None:
    with Session() as session:
        return session.get(WorkspaceModel, workspace_id)


def get_workspaces_by_user_id(
    user_id: id_type, *, include_deleted: bool = False
) -> list[WorkspaceModel]:
    """Live workspaces only, unless include_deleted (binned ones too)."""
    with Session() as session:
        statement = select(WorkspaceModel).where(WorkspaceModel.user_id == user_id)
        if not include_deleted:
            statement = statement.where(WorkspaceModel.deleted_at.is_(None))
        return list(session.scalars(statement).all())


def set_workspace_deleted_at(workspace_id: id_type, deleted_at: datetime | None) -> None:
    with Session() as session:
        workspace = session.get(WorkspaceModel, workspace_id)
        if workspace is not None:
            workspace.deleted_at = deleted_at
            session.commit()


def update_workspace_name(workspace_id: id_type, name: str) -> bool:
    with Session() as session:
        workspace = session.get(WorkspaceModel, workspace_id)

        if workspace is None:
            return False

        workspace.name = name
        session.commit()
        return True


def delete_workspace_by_id(workspace_id: id_type) -> bool:
    with Session() as session:
        workspace = session.get(WorkspaceModel, workspace_id)
        if workspace is None:
            return False

        session.delete(workspace)
        session.commit()
        return True


# Journal functions
def create_journal(journal: JournalModel) -> id_type:
    with Session() as session:
        session.add(journal)
        session.commit()
        return journal.id


def get_journal_by_id(journal_id: id_type) -> JournalModel | None:
    with Session() as session:
        return session.get(JournalModel, journal_id)


def get_journals_by_workspace_id(
    workspace_id: id_type, *, include_deleted: bool = False
) -> list[JournalModel]:
    """Live journals only, unless include_deleted (binned ones too)."""
    with Session() as session:
        statement = select(JournalModel).where(
            JournalModel.workspace_id == workspace_id
        )
        if not include_deleted:
            statement = statement.where(JournalModel.deleted_at.is_(None))
        return list(session.scalars(statement).all())


def set_journal_deleted_at(journal_id: id_type, deleted_at: datetime | None) -> None:
    with Session() as session:
        journal = session.get(JournalModel, journal_id)
        if journal is not None:
            journal.deleted_at = deleted_at
            session.commit()


def count_entries_in_journal(journal_id: id_type) -> int:
    """All entries pointing at the journal, live and binned."""
    with Session() as session:
        return session.scalar(
            select(func.count(EntryModel.id)).where(EntryModel.journal_id == journal_id)
        ) or 0


def update_journal_name_and_description(
    journal_id: id_type,
    name: str | None = None,
    description: str | None = None,
) -> JournalModel | None:
    with Session() as session:
        journal = session.get(JournalModel, journal_id)
        if journal is None:
            return None

        if name is not None:
            journal.name = name
        if description is not None:
            journal.description = description
        session.commit()
        return journal


def move_journal(journal_id: id_type, workspace_id: id_type) -> JournalModel | None:
    with Session() as session:
        journal = session.get(JournalModel, journal_id)
        if journal is None:
            return None

        journal.workspace_id = workspace_id
        session.commit()
        return journal


def delete_journal_by_id(journal_id: id_type) -> bool:
    with Session() as session:
        journal = session.get(JournalModel, journal_id)
        if journal is None:
            return False

        session.delete(journal)
        session.commit()
        return True


# Entry functions
def create_entry(entry: EntryModel) -> id_type:
    with Session() as session:
        session.add(entry)
        session.commit()
        return entry.id


def get_entry_by_id(entry_id: id_type) -> EntryModel | None:
    with Session() as session:
        return session.get(EntryModel, entry_id)


def get_entries_by_journal_id(journal_id: id_type) -> list[EntryModel]:
    with Session() as session:
        statement = select(EntryModel).where(EntryModel.journal_id == journal_id)
        return list(session.scalars(statement).all())


def get_entries_for_user(
    user_id: id_type, *, deleted: bool = False
) -> list[EntryModel]:
    with Session() as session:
        statement = (
            select(EntryModel)
            .join(JournalModel)
            .join(WorkspaceModel)
            .where(
                WorkspaceModel.user_id == user_id,
                EntryModel.is_deleted == deleted,
            )
            .order_by(
                EntryModel.date_created.desc(),
                EntryModel.updated_at.desc(),
                EntryModel.id.desc(),
            )
        )
        return list(session.scalars(statement).all())


def update_entry(
    entry_id: id_type,
    update_object: Union[EntryUpdate, EntrySoftDelete, EntryRestore, EntryMove],
) -> EntryModel | None:
    with Session() as session:
        entry = session.get(EntryModel, entry_id)
        if entry is None:
            return None
        # For certain models (like EntryRestore, EntrySoftDelete), we want to include
        # fields with default values. For others (like EntryUpdate), we skip unset fields.
        if isinstance(update_object, (EntrySoftDelete, EntryRestore)):
            model_data = update_object.model_dump()
        else:
            model_data = update_object.model_dump(exclude_unset=True)
        for key, value in model_data.items():
            if value is None and not isinstance(
                update_object, (EntrySoftDelete, EntryRestore)
            ):
                continue
            setattr(entry, key, value)
        session.commit()
        session.refresh(entry)
        return entry


def search_entries(
    user_id: id_type,
    search_filter: EntrySearch,
    offset: int = 0,
    limit: int = 100,
) -> list[EntryModel]:
    with Session() as session:
        statement = (
            select(EntryModel)
            .join(JournalModel)
            .join(WorkspaceModel)
            .where(WorkspaceModel.user_id == user_id, EntryModel.is_deleted.is_(False))
        )
        if search_filter.journal_id is not None:
            statement = statement.where(
                EntryModel.journal_id == search_filter.journal_id
            )
        if search_filter.tags:
            tag_clauses = [EntryModel.tags.like(f'%"{tag}"%') for tag in search_filter.tags]
            if search_filter.tag_mode == "any":
                statement = statement.where(or_(*tag_clauses))
            else:
                statement = statement.where(*tag_clauses)
        if search_filter.name:
            statement = statement.where(
                EntryModel.name.ilike(f"%{search_filter.name}%")
            )
        if search_filter.from_date is not None:
            statement = statement.where(
                EntryModel.date_created >= search_filter.from_date
            )
        if search_filter.to_date is not None:
            statement = statement.where(
                EntryModel.date_created <= search_filter.to_date
            )
        if search_filter.q:
            pattern = f"%{search_filter.q}%"
            statement = statement.where(
                EntryModel.tags.ilike(pattern)
                | EntryModel.name.ilike(pattern)
                | EntryModel.custom_metadata.ilike(pattern)
                | EntryModel.body.ilike(pattern)
            )
        statement = (
            statement.order_by(
                EntryModel.date_created.desc(),
                EntryModel.updated_at.desc(),
                EntryModel.id.desc(),
            )
            .offset(offset)
            .limit(limit)
        )
        return list(session.scalars(statement).all())


def count_deleted_entries(user_id: id_type) -> int:
    with Session() as session:
        statement = (
            select(EntryModel.id)
            .join(JournalModel)
            .join(WorkspaceModel)
            .where(WorkspaceModel.user_id == user_id, EntryModel.is_deleted.is_(True))
        )
        return len(session.scalars(statement).all())


def delete_entry_by_id(entry_id: id_type) -> bool:
    with Session() as session:
        entry = session.get(EntryModel, entry_id)
        if entry is None:
            return False

        session.delete(entry)
        session.commit()
        return True


# Tag functions
def create_tag(tag: TagModel) -> id_type:
    with Session() as session:
        session.add(tag)
        session.commit()
        return tag.id


def get_tags_by_user(user_id: id_type) -> list[TagModel]:
    with Session() as session:
        statement = (
            select(TagModel).where(TagModel.user_id == user_id).order_by(TagModel.name)
        )
        return list(session.scalars(statement).all())


def get_tag_by_name(user_id: id_type, name: str) -> TagModel | None:
    with Session() as session:
        statement = select(TagModel).where(
            TagModel.user_id == user_id, TagModel.name == name
        )
        return session.scalar(statement)


def ensure_user_tags(user_id: id_type, names: Iterable[str]) -> int:
    """Create whichever of `names` the user doesn't have yet. Returns how many
    were created."""
    wanted = {name for name in names if name}
    if not wanted:
        return 0
    with Session() as session:
        existing = set(
            session.scalars(
                select(TagModel.name).where(
                    TagModel.user_id == user_id, TagModel.name.in_(wanted)
                )
            )
        )
        missing = sorted(wanted - existing)
        now = utcnow()
        session.add_all(
            TagModel(user_id=user_id, name=name, created_at=now) for name in missing
        )
        session.commit()
        return len(missing)


def update_tag_created_at(tag_id: id_type, created_at: datetime) -> None:
    with Session() as session:
        tag = session.get(TagModel, tag_id)
        if tag is not None:
            tag.created_at = created_at
            session.commit()


def delete_tag(tag: TagModel) -> None:
    with Session() as session:
        session.delete(tag)
        session.commit()


def delete_tags_by_user_id(user_id: id_type) -> None:
    with Session() as session:
        session.execute(delete(TagModel).where(TagModel.user_id == user_id))
        session.commit()


# Media functions
def delete_media_by_id(media_id: id_type) -> bool:
    with Session() as session:
        media = session.get(MediaModel, media_id)
        if media is None:
            return False

        session.delete(media)
        session.commit()
        return True


def get_media_by_entry_id(entry_id: id_type) -> list[MediaModel]:
    with Session() as session:
        statement = select(MediaModel).where(MediaModel.entry_id == entry_id)
        return list(session.scalars(statement).all())


def get_media_by_id(media_id: id_type) -> MediaModel | None:
    with Session() as session:
        return session.get(MediaModel, media_id)


def create_media(media: MediaModel) -> id_type:
    with Session() as session:
        session.add(media)
        session.commit()
        return media.id


def get_media_by_resource_path(resource_path: str) -> MediaModel | None:
    """Resolve media from its derived URL (http://host/media/{user_id}/{stored_filename}).

    resource_path is never stored; it's parsed back into (user_id, stored_filename)
    and matched via the entry->journal->workspace ownership chain.
    """
    parts = resource_path.rstrip("/").rsplit("/", 2)
    if len(parts) != 3:
        return None
    _, owner_id, stored_filename = parts
    with Session() as session:
        statement = (
            select(MediaModel)
            .join(MediaModel.entry)
            .join(EntryModel.journal)
            .join(JournalModel.workspace)
            .where(
                MediaModel.stored_filename == stored_filename,
                WorkspaceModel.user_id == owner_id,
            )
        )
        return session.scalar(statement)


def update_media(media_id: id_type, **values) -> MediaModel | None:
    with Session() as session:
        media = session.get(MediaModel, media_id)
        if media is None:
            return None
        for key, value in values.items():
            setattr(media, key, value)
        session.commit()
        session.refresh(media)
        return media


def get_media_by_user_id(user_id: id_type) -> list[MediaModel]:
    """Get all media files for a user."""
    with Session() as session:
        statement = (
            select(MediaModel)
            .join(MediaModel.entry)
            .join(EntryModel.journal)
            .join(JournalModel.workspace)
            .where(WorkspaceModel.user_id == user_id)
        )
        return list(session.scalars(statement).all())


def media_belongs_to_user(media_id: id_type, user_id: id_type) -> bool:
    """Check if a media file belongs to a specific user."""
    with Session() as session:
        statement = (
            select(MediaModel.id)
            .join(MediaModel.entry)
            .join(EntryModel.journal)
            .join(JournalModel.workspace)
            .where(MediaModel.id == media_id, WorkspaceModel.user_id == user_id)
        )
        return session.scalar(statement) is not None


def entry_references_media(resource_path: str) -> bool:
    with Session() as session:
        statement = select(EntryModel.id).where(
            EntryModel.media_refs.like(f'%"{resource_path}"%')
        )
        return session.scalar(statement) is not None


# ── Entry version functions ────────────────────────────────────────────────────

def create_entry_version(
    entry_id: id_type, body: str, tags: str, media_refs: str
) -> EntryVersionModel:
    from datetime import datetime, timezone
    version = EntryVersionModel(
        entry_id=entry_id,
        created_at=datetime.now(timezone.utc),
        body=body,
        tags=tags,
        media_refs=media_refs,
    )
    with Session() as session:
        session.add(version)
        session.commit()
        return version


def get_latest_entry_version(entry_id: id_type) -> EntryVersionModel | None:
    with Session() as session:
        return (
            session.query(EntryVersionModel)
            .filter_by(entry_id=entry_id)
            .order_by(EntryVersionModel.created_at.desc())
            .first()
        )


def get_entry_versions(entry_id: id_type) -> list[EntryVersionModel]:
    with Session() as session:
        return (
            session.query(EntryVersionModel)
            .filter_by(entry_id=entry_id)
            .order_by(EntryVersionModel.created_at.desc())
            .all()
        )


def get_entry_version_by_id(version_id: id_type) -> EntryVersionModel | None:
    with Session() as session:
        return session.query(EntryVersionModel).filter_by(id=version_id).first()
