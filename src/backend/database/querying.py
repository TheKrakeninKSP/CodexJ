# an abstraction layer to query the database
# SQLite database implementation

from sqlalchemy import (
    Column,
    Integer,
    String,
    Text,
    create_engine,
    inspect,
)
from sqlalchemy.orm import declarative_base, sessionmaker

from backend.constants import SQLITE_DB_URL
from backend.database.structural import UserModel
from backend.models.entry import Entry
from backend.models.journal import Journal
from backend.models.media import Media
from backend.models.tag import Tag
from backend.models.user import User
from backend.models.workspace import Workspace
from backend.types import id_type

engine = create_engine(SQLITE_DB_URL, future=True)
Session = sessionmaker(bind=engine, future=True)


def get_user_by_id(user_id: id_type):
    with Session() as session:
        return session.get(UserModel, user_id)


def get_workspace_by_id(workspace_id: id_type):
    with Session() as session:
        return session.get(Workspace, workspace_id)


def get_journal_by_id(journal_id: id_type):
    with Session() as session:
        return session.get(Journal, journal_id)


def get_entry_by_id(entry_id: id_type):
    with Session() as session:
        return session.get(Entry, entry_id)
