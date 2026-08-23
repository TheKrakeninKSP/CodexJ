from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    create_engine,
    inspect,
)
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    mapped_column,
    relationship,
    sessionmaker,
)

from backend.constants import (
    ENTRY_TABLE_NAME,
    JOURNAL_TABLE_NAME,
    MEDIA_TABLE_NAME,
    SQLITE_DB_URL,
    TAG_TABLE_NAME,
    USER_TABLE_NAME,
    WORKSPACE_TABLE_NAME,
)


class Base(DeclarativeBase):
    pass


class UserModel(Base):
    __tablename__ = USER_TABLE_NAME

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String, nullable=False)
    hashkey_hash: Mapped[str] = mapped_column(String, nullable=False)
    dump_key: Mapped[str] = mapped_column(String, nullable=False)
    theme: Mapped[str] = mapped_column(String, nullable=False, default="light")
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)

    workspaces: Mapped[list["WorkspaceModel"]] = relationship(back_populates="user")


class WorkspaceModel(Base):
    __tablename__ = WORKSPACE_TABLE_NAME

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey(f"{USER_TABLE_NAME}.id"), nullable=False
    )
    name: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)

    user: Mapped["UserModel"] = relationship(back_populates="workspaces")
    journals: Mapped[list["JournalModel"]] = relationship(back_populates="workspace")


class JournalModel(Base):
    __tablename__ = JOURNAL_TABLE_NAME

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    workspace_id: Mapped[int] = mapped_column(
        ForeignKey(f"{WORKSPACE_TABLE_NAME}.id"), nullable=False
    )
    name: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)

    workspace: Mapped["WorkspaceModel"] = relationship(back_populates="journals")
    entries: Mapped[list["EntryModel"]] = relationship(back_populates="journal")


class TagModel(Base):
    __tablename__ = TAG_TABLE_NAME

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)


class EntryModel(Base):
    __tablename__ = ENTRY_TABLE_NAME

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    journal_id: Mapped[int] = mapped_column(
        ForeignKey(f"{JOURNAL_TABLE_NAME}.id"), nullable=False
    )
    tags: Mapped[str] = mapped_column(Text, default="[]")
    name: Mapped[str | None] = mapped_column(String, nullable=True)
    timezone: Mapped[str | None] = mapped_column(String, nullable=True)
    body: Mapped[str] = mapped_column(Text, default="{}")
    custom_metadata: Mapped[str] = mapped_column(Text, default="[]")
    media_refs: Mapped[str] = mapped_column(Text, default="[]")
    date_created: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    deleted_from_workspace_id: Mapped[int | None] = mapped_column(
        Integer, nullable=True
    )
    deleted_from_journal_id: Mapped[int | None] = mapped_column(Integer, nullable=True)

    journal: Mapped["JournalModel"] = relationship(back_populates="entries")
    media: Mapped[list["MediaModel"]] = relationship(back_populates="entry")


class MediaModel(Base):
    __tablename__ = MEDIA_TABLE_NAME

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    entry_id: Mapped[int] = mapped_column(
        ForeignKey(f"{ENTRY_TABLE_NAME}.id"), nullable=False
    )
    original_filename: Mapped[str] = mapped_column(String, nullable=False)
    stored_filename: Mapped[str] = mapped_column(String, nullable=False)
    media_type: Mapped[str] = mapped_column(String, nullable=False)
    file_size: Mapped[int] = mapped_column(Integer, nullable=False)
    resource_path: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    custom_metadata: Mapped[str] = mapped_column(Text, default="{}", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)

    entry: Mapped["EntryModel"] = relationship(back_populates="media")


engine = create_engine(SQLITE_DB_URL, future=True)
Session = sessionmaker(bind=engine, future=True)


def init_db():
    Base.metadata.create_all(engine)


def db_exists() -> bool:
    insp = inspect(engine)
    # consider DB existing if the user table exists
    return insp.has_table(USER_TABLE_NAME)
