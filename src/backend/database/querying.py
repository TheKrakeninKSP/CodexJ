# an abstraction layer to query the database
# SQLite database implementation

from sqlalchemy import (
    Column,
    Integer,
    String,
    Text,
    create_engine,
    inspect,
    select,
    update,
)
from sqlalchemy.orm import declarative_base, sessionmaker

from backend.constants import SQLITE_DB_URL
from backend.database.structural import (
    EntryModel,
    JournalModel,
    MediaModel,
    TagModel,
    UserModel,
    WorkspaceModel,
)
from backend.models.entry import Entry
from backend.models.journal import Journal
from backend.models.media import Media
from backend.models.tag import Tag
from backend.models.user import User
from backend.models.workspace import Workspace
from backend.settings import ColorTheme
from backend.types import id_type, theme_type

engine = create_engine(SQLITE_DB_URL, future=True)
Session = sessionmaker(bind=engine, future=True)


def get_user_by_username(username: str) -> UserModel | None:
    with Session() as session:
        return session.query(UserModel).filter_by(username=username).first()


def get_workspace_by_id(workspace_id: id_type) -> WorkspaceModel | None:
    with Session() as session:
        return session.get(WorkspaceModel, workspace_id)


def get_journal_by_id(journal_id: id_type) -> JournalModel | None:
    with Session() as session:
        return session.get(JournalModel, journal_id)


def get_entry_by_id(entry_id: id_type) -> EntryModel | None:
    with Session() as session:
        return session.get(EntryModel, entry_id)


def create_entry(entry: EntryModel) -> id_type:
    with Session() as session:
        session.add(entry)
        session.commit()
        return entry.id


def get_all_tags() -> list[TagModel]:
    with Session() as session:
        statement = select(TagModel)
        return list(session.scalars(statement).all())


def update_entry(entry_id: id_type, **values) -> EntryModel | None:
    with Session() as session:
        entry = session.get(EntryModel, entry_id)
        if entry is None:
            return None
        for key, value in values.items():
            setattr(entry, key, value)
        session.commit()
        session.refresh(entry)
        return entry


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
            .order_by(EntryModel.date_created.desc(), EntryModel.id.desc())
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


def search_entries(
    user_id: id_type,
    *,
    query: str = "",
    journal_id: id_type | None = None,
    entry_type: str | None = None,
    name: str | None = None,
    from_date=None,
    to_date=None,
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
        if journal_id is not None:
            statement = statement.where(EntryModel.journal_id == journal_id)
        if entry_type:
            statement = statement.where(EntryModel.tags.like(f'%"{entry_type}"%'))
        if name:
            statement = statement.where(EntryModel.name.ilike(f"%{name}%"))
        if from_date is not None:
            statement = statement.where(EntryModel.date_created >= from_date)
        if to_date is not None:
            statement = statement.where(EntryModel.date_created <= to_date)
        if query:
            pattern = f"%{query}%"
            statement = statement.where(
                EntryModel.tags.ilike(pattern)
                | EntryModel.name.ilike(pattern)
                | EntryModel.custom_metadata.ilike(pattern)
                | EntryModel.body.ilike(pattern)
            )
        statement = (
            statement.order_by(EntryModel.date_created.desc(), EntryModel.id.desc())
            .offset(offset)
            .limit(limit)
        )
        return list(session.scalars(statement).all())


def delete_user_by_id(user_id: id_type) -> bool:
    with Session() as session:
        user = session.get(UserModel, user_id)
        if user is None:
            return False

        session.delete(user)
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


def delete_journal_by_id(journal_id: id_type) -> bool:
    with Session() as session:
        journal = session.get(JournalModel, journal_id)
        if journal is None:
            return False

        session.delete(journal)
        session.commit()
        return True


def delete_entry_by_id(entry_id: id_type) -> bool:
    with Session() as session:
        entry = session.get(EntryModel, entry_id)
        if entry is None:
            return False

        session.delete(entry)
        session.commit()
        return True


def delete_media_by_id(media_id: id_type) -> bool:
    with Session() as session:
        media = session.get(MediaModel, media_id)
        if media is None:
            return False

        session.delete(media)
        session.commit()
        return True


def create_user(user: UserModel) -> id_type:
    """takes in object of User class and returns user id of the newly created user"""
    with Session() as session:
        session.add(user)
        session.commit()
        return user.id


def create_workspace(workspace: WorkspaceModel) -> id_type:
    """takes in object of Workspace class and returns workspace id of the newly created workspace"""
    with Session() as session:
        session.add(workspace)
        session.commit()
        return workspace.id


def create_journal(journal: JournalModel) -> id_type:
    with Session() as session:
        session.add(journal)
        session.commit()
        return journal.id


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


def update_user_theme(user_id: id_type, theme: theme_type) -> bool:
    with Session() as session:
        user = session.get(UserModel, user_id)

        if user is None:
            return False

        user.theme = theme
        session.commit()
        return True


def update_workspace_name(workspace_id: id_type, name: str) -> bool:
    with Session() as session:
        workspace = session.get(WorkspaceModel, workspace_id)

        if workspace is None:
            return False

        workspace.name = name
        session.commit()
        return True


def get_workspaces_by_user_id(user_id: id_type) -> list[WorkspaceModel]:
    with Session() as session:
        statement = select(WorkspaceModel).where(WorkspaceModel.user_id == user_id)
        return list(session.scalars(statement).all())


def get_journals_by_workspace_id(workspace_id: id_type) -> list[JournalModel]:
    with Session() as session:
        statement = select(JournalModel).where(
            JournalModel.workspace_id == workspace_id
        )
        return list(session.scalars(statement).all())


def get_entries_by_journal_id(journal_id: id_type) -> list[EntryModel]:
    with Session() as session:
        statement = select(EntryModel).where(EntryModel.journal_id == journal_id)
        return list(session.scalars(statement).all())


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


def get_media_by_resource_path(
    resource_path: str, user_id: id_type
) -> MediaModel | None:
    with Session() as session:
        statement = select(MediaModel).where(
            MediaModel.resource_path == resource_path,
            MediaModel.user_id == user_id,
        )
        return session.scalar(statement)


def get_media_by_user_id(user_id: id_type) -> list[MediaModel]:
    with Session() as session:
        statement = select(MediaModel).where(MediaModel.user_id == user_id)
        return list(session.scalars(statement).all())


def update_media(media_id: id_type, user_id: id_type, **values) -> MediaModel | None:
    with Session() as session:
        media = session.get(MediaModel, media_id)
        if media is None or media.user_id != user_id:
            return None
        for key, value in values.items():
            setattr(media, key, value)
        session.commit()
        session.refresh(media)
        return media


def entry_references_media(resource_path: str) -> bool:
    with Session() as session:
        statement = select(EntryModel.id).where(
            EntryModel.media_refs.like(f'%"{resource_path}"%')
        )
        return session.scalar(statement) is not None
