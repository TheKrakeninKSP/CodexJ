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
