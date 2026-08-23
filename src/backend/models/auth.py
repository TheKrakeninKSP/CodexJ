from pydantic import BaseModel

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


class RegisterResponse(BaseModel):
    username: str
    access_token: str
    token_type: str = "bearer"
    hashkey: str  # shown only once for user to save


class DeleteUserResponse(BaseModel):
    status: str
    message: str


class UserPreferencesResponse(BaseModel):
    theme: theme_type


class UpdateUserPreferencesRequest(BaseModel):
    theme: theme_type


class ImportResult(BaseModel):
    status: str
    workspaces_imported: int = 0
    journals_imported: int = 0
    entries_imported: int = 0
    entry_types_imported: int = 0
    skipped: int = 0


class RegisterWithImportResponse(BaseModel):
    username: str
    access_token: str
    token_type: str = "bearer"
    import_result: ImportResult
