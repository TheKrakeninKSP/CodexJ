# an abstraction layer to query the database
# SQLite database implementation

from sqlalchemy import (
    Column,
    Integer,
    String,
    Text,
    create_engine,
    inspect,
    update,
)
from sqlalchemy.orm import declarative_base, sessionmaker

from backend.constants import SQLITE_DB_URL
from backend.database.structural import (
    EntryModel,
    JournalModel,
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
from backend.types import id_type

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


def update_user_theme(user_id: id_type, theme: ColorTheme) -> bool:
    with Session.begin() as session:
        result = session.execute(
            update(UserModel).where(UserModel.id == user_id).values(theme=theme.value)
        )
        return result.rowcount == 1
