from datetime import datetime, timezone
from typing import Literal, Optional

from app.constants import (
    PASSWORD_MAX_LENGTH,
    PASSWORD_MIN_LENGTH,
    USERNAME_MAX_LENGTH,
    USERNAME_MIN_LENGTH,
)
from bson import ObjectId
from pydantic import BaseModel, Field

ThemeName = Literal["light", "solarized-dark"]

DEFAULT_THEME: ThemeName = "light"
SUPPORTED_THEMES: set[str] = {"light", "solarized-dark"}


def normalize_theme(value: Optional[str]) -> ThemeName:
    if value == "light" or value == "solarized-dark":
        return value
    return DEFAULT_THEME


class PyObjectId(ObjectId):
    @classmethod
    def __get_validators__(cls):
        yield cls.validate

    @classmethod
    def validate(cls, v, info=None):
        if not ObjectId.is_valid(v):
            raise ValueError("Invalid ObjectId")
        return ObjectId(v)

    @classmethod
    def __get_pydantic_core_schema__(cls, source_type, handler):
        from pydantic_core import core_schema

        return core_schema.no_info_plain_validator_function(cls.validate)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class UserCreate(BaseModel):
    username: str = Field(
        ..., min_length=USERNAME_MIN_LENGTH, max_length=USERNAME_MAX_LENGTH
    )
    password: str = Field(
        ..., min_length=PASSWORD_MIN_LENGTH, max_length=PASSWORD_MAX_LENGTH
    )


class DB_User(BaseModel):
    username: str
    password_hash: str
    hashkey_hash: str
    theme: ThemeName = DEFAULT_THEME
    created_at: datetime = Field(default_factory=utcnow)

    model_config = {"arbitrary_types_allowed": True}


class UserOut(BaseModel):
    id: str
    username: str
    theme: ThemeName = DEFAULT_THEME
    created_at: datetime
