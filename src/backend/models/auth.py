from datetime import datetime, timezone

from pydantic import BaseModel, field_validator

from backend.type_defs import id_type, theme_type


class JWT_Payload(BaseModel):
    user_id: id_type
    username: str
    expire: str


class LoginRequest(BaseModel):
    username: str
    password: str


class UnlockRequest(BaseModel):
    username: str
    hashkey: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class PrivilegedModeRequest(BaseModel):
    password: str


class PrivilegedModeResponse(BaseModel):
    status: str


class PrivilegedStatusResponse(BaseModel):
    is_privileged: bool


class RegisterResponse(BaseModel):
    username: str
    access_token: str
    token_type: str = "bearer"
    hashkey: str  # shown only once for user to save


class DeleteUserResponse(BaseModel):
    status: str
    message: str


class CurrentUserResponse(BaseModel):
    username: str
    is_admin: bool


class AccountStatsResponse(BaseModel):
    created_at: datetime
    workspace_count: int
    journal_count: int
    entry_count: int
    tag_count: int
    media_count: int
    media_bytes: int  # on-disk size of media/<user_id>/, orphans included
    text_bytes: int  # entry body/metadata/tags + saved versions, binned included
    total_bytes: int

    @field_validator("created_at")
    @classmethod
    def _assume_utc(cls, value: datetime) -> datetime:
        # SQLite drops tzinfo; stored timestamps are UTC.
        return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


class UserPreferencesResponse(BaseModel):
    theme: theme_type


class UpdateUserPreferencesRequest(BaseModel):
    theme: theme_type


class ImportResult(BaseModel):
    status: str
    workspaces_imported: int = 0
    journals_imported: int = 0
    entries_imported: int = 0
    tags_imported: int = 0
    skipped: int = 0


class RegisterWithImportResponse(BaseModel):
    username: str
    access_token: str
    token_type: str = "bearer"
    import_result: ImportResult
