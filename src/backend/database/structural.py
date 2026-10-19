from datetime import datetime

from alembic import command
from alembic.config import Config
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
    ENTRY_VERSION_TABLE_NAME,
    JOURNAL_TABLE_NAME,
    MEDIA_TABLE_NAME,
    MIGRATIONS_PATH,
    SQLITE_DB_URL,
    TAG_TABLE_NAME,
    USER_TABLE_NAME,
    WORKSPACE_TABLE_NAME,
)
from backend.type_defs import id_type, new_id


class Base(DeclarativeBase):
    pass


class UserModel(Base):
    __tablename__ = USER_TABLE_NAME

    id: Mapped[id_type] = mapped_column(String(36), primary_key=True, default=new_id)
    username: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String, nullable=False)
    hashkey_hash: Mapped[str] = mapped_column(String, nullable=False)
    dump_key: Mapped[str] = mapped_column(String, nullable=False)
    theme: Mapped[str] = mapped_column(String, nullable=False, default="light")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )

    workspaces: Mapped[list["WorkspaceModel"]] = relationship(back_populates="user")


class WorkspaceModel(Base):
    __tablename__ = WORKSPACE_TABLE_NAME

    id: Mapped[id_type] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[id_type] = mapped_column(
        String(36), ForeignKey(f"{USER_TABLE_NAME}.id"), nullable=False
    )
    name: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )

    user: Mapped["UserModel"] = relationship(back_populates="workspaces")
    journals: Mapped[list["JournalModel"]] = relationship(back_populates="workspace")


class JournalModel(Base):
    __tablename__ = JOURNAL_TABLE_NAME

    id: Mapped[id_type] = mapped_column(String(36), primary_key=True, default=new_id)
    workspace_id: Mapped[id_type] = mapped_column(
        String(36), ForeignKey(f"{WORKSPACE_TABLE_NAME}.id"), nullable=False
    )
    name: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )

    workspace: Mapped["WorkspaceModel"] = relationship(back_populates="journals")
    entries: Mapped[list["EntryModel"]] = relationship(back_populates="journal")


class TagModel(Base):
    __tablename__ = TAG_TABLE_NAME

    id: Mapped[id_type] = mapped_column(String(36), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )


class EntryModel(Base):
    __tablename__ = ENTRY_TABLE_NAME

    id: Mapped[id_type] = mapped_column(String(36), primary_key=True, default=new_id)
    journal_id: Mapped[id_type] = mapped_column(
        String(36), ForeignKey(f"{JOURNAL_TABLE_NAME}.id"), nullable=False
    )
    tags: Mapped[str] = mapped_column(Text, default="[]")
    name: Mapped[str | None] = mapped_column(String, nullable=True)
    timezone: Mapped[str | None] = mapped_column(String, nullable=True)
    body: Mapped[str] = mapped_column(Text, default="{}")
    custom_metadata: Mapped[str] = mapped_column(Text, default="[]")
    theme: Mapped[str] = mapped_column(Text, nullable=True)
    media_refs: Mapped[str] = mapped_column(Text, default="[]")
    date_created: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    deleted_from_workspace_id: Mapped[id_type | None] = mapped_column(
        String(36), nullable=True
    )
    deleted_from_journal_id: Mapped[id_type | None] = mapped_column(
        String(36), nullable=True
    )

    journal: Mapped["JournalModel"] = relationship(back_populates="entries")
    media: Mapped[list["MediaModel"]] = relationship(back_populates="entry")
    versions: Mapped[list["EntryVersionModel"]] = relationship(
        back_populates="entry", order_by="EntryVersionModel.created_at"
    )


class EntryVersionModel(Base):
    __tablename__ = ENTRY_VERSION_TABLE_NAME

    id: Mapped[id_type] = mapped_column(String(36), primary_key=True, default=new_id)
    entry_id: Mapped[id_type] = mapped_column(
        String(36), ForeignKey(f"{ENTRY_TABLE_NAME}.id"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False, default="")
    tags: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    media_refs: Mapped[str] = mapped_column(Text, nullable=False, default="[]")

    entry: Mapped["EntryModel"] = relationship(back_populates="versions")


class MediaModel(Base):
    __tablename__ = MEDIA_TABLE_NAME

    id: Mapped[id_type] = mapped_column(String(36), primary_key=True, default=new_id)
    entry_id: Mapped[id_type] = mapped_column(
        String(36), ForeignKey(f"{ENTRY_TABLE_NAME}.id"), nullable=False
    )
    original_filename: Mapped[str] = mapped_column(String, nullable=False)
    stored_filename: Mapped[str] = mapped_column(String, nullable=False)
    media_type: Mapped[str] = mapped_column(String, nullable=False)
    file_size: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    custom_metadata: Mapped[str] = mapped_column(Text, default="{}", nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )

    entry: Mapped["EntryModel"] = relationship(back_populates="media")


engine = create_engine(SQLITE_DB_URL, future=True)
Session = sessionmaker(bind=engine, future=True)


def init_db():
    Base.metadata.create_all(engine)


def db_exists() -> bool:
    insp = inspect(engine)
    # consider DB existing if the user table exists
    return insp.has_table(USER_TABLE_NAME)


def run_migrations() -> None:
    """Bring the database up to the latest schema on startup.

    Fresh installs get the current schema straight from the ORM models and are
    stamped as being at the latest revision. Existing databases (including
    ones that pre-date Alembic, which have no alembic_version table) are
    walked through the migration chain with `upgrade head` - each migration
    guards its own DDL so this is safe to run against a database that's
    already partway there.
    """
    cfg = Config()
    cfg.set_main_option("script_location", str(MIGRATIONS_PATH))

    if db_exists():
        command.upgrade(cfg, "head")
    else:
        init_db()
        command.stamp(cfg, "head")
