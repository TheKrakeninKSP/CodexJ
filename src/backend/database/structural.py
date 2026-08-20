from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    create_engine,
    inspect,
)
from sqlalchemy.orm import declarative_base, relationship, sessionmaker

from backend.constants import (
    ENTRY_TABLE_NAME,
    JOURNAL_TABLE_NAME,
    MEDIA_TABLE_NAME,
    SQLITE_DB_URL,
    TAG_TABLE_NAME,
    USER_TABLE_NAME,
    WORKSPACE_TABLE_NAME,
)

Base = declarative_base()


class UserModel(Base):
    __tablename__ = USER_TABLE_NAME

    id = Column(Integer, primary_key=True)
    username = Column(String, unique=True, nullable=False)
    password_hash = Column(String, nullable=False)
    hashkey_hash = Column(String, nullable=False)
    theme = Column(String, nullable=False, default="light")
    created_at = Column(DateTime, nullable=False)

    workspaces = relationship("WorkspaceModel", back_populates="user")


class WorkspaceModel(Base):
    __tablename__ = WORKSPACE_TABLE_NAME

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey(f"{USER_TABLE_NAME}.id"), nullable=False)
    name = Column(String, nullable=False)
    created_at = Column(DateTime, nullable=False)

    user = relationship("UserModel", back_populates="workspaces")
    journals = relationship("JournalModel", back_populates="workspace")


class JournalModel(Base):
    __tablename__ = JOURNAL_TABLE_NAME

    id = Column(Integer, primary_key=True)
    workspace_id = Column(
        Integer, ForeignKey(f"{WORKSPACE_TABLE_NAME}.id"), nullable=False
    )
    name = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    created_at = Column(DateTime, nullable=False)

    workspace = relationship("WorkspaceModel", back_populates="journals")
    entries = relationship("EntryModel", back_populates="journal")


class TagModel(Base):
    __tablename__ = TAG_TABLE_NAME

    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    created_at = Column(DateTime, nullable=False)


class EntryModel(Base):
    __tablename__ = ENTRY_TABLE_NAME

    id = Column(Integer, primary_key=True)
    journal_id = Column(Integer, ForeignKey(f"{JOURNAL_TABLE_NAME}.id"), nullable=False)
    tags = Column(Text, default="[]")
    name = Column(String, nullable=True)
    timezone = Column(String, nullable=True)
    body = Column(Text, default="{}")
    custom_metadata = Column(Text, default="[]")
    media_refs = Column(Text, default="[]")
    date_created = Column(DateTime, nullable=False)
    updated_at = Column(DateTime, nullable=False)
    is_deleted = Column(Boolean, default=False, nullable=False)
    deleted_at = Column(DateTime, nullable=True)
    deleted_from_workspace_id = Column(Integer, nullable=True)
    deleted_from_journal_id = Column(Integer, nullable=True)

    journal = relationship("JournalModel", back_populates="entries")


class MediaModel(Base):
    __tablename__ = MEDIA_TABLE_NAME

    id = Column(Integer, primary_key=True)
    entry_id = Column(Integer, ForeignKey(f"{ENTRY_TABLE_NAME}.id"), nullable=False)
    filename = Column(String, nullable=False)
    media_type = Column(String, nullable=False)
    file_size = Column(Integer, nullable=False)
    resource_path = Column(String, nullable=False)
    status = Column(String, nullable=False)
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime, nullable=False)


engine = create_engine(SQLITE_DB_URL, future=True)
Session = sessionmaker(bind=engine, future=True)


def init_db():
    Base.metadata.create_all(engine)


def db_exists() -> bool:
    insp = inspect(engine)
    # consider DB existing if the user table exists
    return insp.has_table(USER_TABLE_NAME)
