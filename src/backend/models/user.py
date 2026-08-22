from datetime import datetime

from pydantic import BaseModel, Field

from backend.constants import (
    PASSWORD_MAX_LENGTH,
    PASSWORD_MIN_LENGTH,
    USERNAME_MAX_LENGTH,
    USERNAME_MIN_LENGTH,
)
from backend.settings import ColorTheme
from backend.type_defs import id_type
from backend.utils.common import utcnow


def normalize_theme(value: str | ColorTheme | None) -> ColorTheme:
    if isinstance(value, ColorTheme):
        return value
    try:
        return ColorTheme(value or ColorTheme.light.value)
    except ValueError:
        return ColorTheme.light


class User(BaseModel):
    id: id_type
    username: str
    password_hash: str
    hashkey_hash: str
    dump_key: str
    theme: ColorTheme = ColorTheme.light
    created_at: datetime = Field(default_factory=utcnow)


class UserCreate(BaseModel):
    username: str = Field(
        ..., min_length=USERNAME_MIN_LENGTH, max_length=USERNAME_MAX_LENGTH
    )
    password: str = Field(
        ..., min_length=PASSWORD_MIN_LENGTH, max_length=PASSWORD_MAX_LENGTH
    )


class UserOut(BaseModel):
    username: str
    theme: ColorTheme = ColorTheme.light
