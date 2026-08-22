import os
import secrets
import shutil
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from pydantic import BaseModel

from backend.constants import DEFAULT_COLOR_THEME, DEFAULT_WORKSPACE_NAME, MEDIA_PATH
from backend.database.querying import (
    create_user,
    create_workspace,
    delete_entry_by_id,
    delete_journal_by_id,
    delete_media_by_id,
    delete_user_by_id,
    delete_workspace_by_id,
    get_entries_by_journal_id,
    get_journals_by_workspace_id,
    get_media_by_entry_id,
    get_user_by_username,
    get_workspaces_by_user_id,
    update_user_theme,
)
from backend.database.structural import UserModel, WorkspaceModel
from backend.models.user import UserCreate
from backend.type_defs import theme_type
from backend.utils.auth import (
    create_access_token,
    get_current_user,
    hash_secret,
    require_privileged_mode,
    set_privileged_mode,
    verify_secret,
)
from backend.utils.data_management import (
    derive_dump_key,
    import_dump_data,
    read_dump_meta,
    read_encrypted_dump,
    validate_dump_structure,
)

router = APIRouter(prefix="/auth", tags=["auth"])


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


@router.post("/register", response_model=RegisterResponse, status_code=201)
async def register(payload: UserCreate):
    if get_user_by_username(payload.username) is not None:
        raise HTTPException(status_code=409, detail="Username already taken")

    # Generate a one-time hashkey (32 random bytes → 64-char hex string)
    plaintext_hashkey = secrets.token_hex(32)
    # Generate a dump key derived from the hashkey and username for exports
    dump_key = derive_dump_key(plaintext_hashkey, payload.username)

    user = UserModel(
        username=payload.username,
        password=hash_secret(payload.password),
        hashkey_hash=hash_secret(plaintext_hashkey),
        dump_key=dump_key,
        theme=DEFAULT_COLOR_THEME,
        created_at=datetime.now(timezone.utc),
    )
    user_id = create_user(user)

    default_workspace = WorkspaceModel(
        user_id=user_id,
        name=DEFAULT_WORKSPACE_NAME,
        created_at=datetime.now(timezone.utc),
    )
    create_workspace(default_workspace)

    token = create_access_token(user_id, payload.username)
    return RegisterResponse(
        username=payload.username,
        access_token=token,
        hashkey=plaintext_hashkey,
    )


@router.post("/login", response_model=TokenResponse)
async def login(payload: LoginRequest):
    user = get_user_by_username(LoginRequest.username)
    if not user or not verify_secret(payload.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password",
        )
    token = create_access_token(user.id, user.username)
    return TokenResponse(access_token=token)


@router.post("/unlock", response_model=TokenResponse)
async def unlock(payload: UnlockRequest):
    user = get_user_by_username(UnlockRequest.username)
    if not user or not verify_secret(payload.hashkey, user.hashkey_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or hashkey",
        )
    token = create_access_token(user.id, user.username)
    return TokenResponse(access_token=token)


@router.post("/privileged", response_model=PrivilegedModeResponse)
async def enable_privileged_mode(
    payload: PrivilegedModeRequest,
    user: UserModel = Depends(get_current_user),
):
    if not verify_secret(payload.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid password",
        )
    set_privileged_mode(True)
    return PrivilegedModeResponse(status="Privileged mode enabled")


@router.post("/privileged/disable", response_model=PrivilegedModeResponse)
async def disable_privileged_mode():
    set_privileged_mode(False)
    return PrivilegedModeResponse(status="Privileged mode disabled")


@router.get("/preferences", response_model=UserPreferencesResponse)
async def get_user_preferences(
    user: UserModel = Depends(get_current_user),
):
    return UserPreferencesResponse(theme=user.theme)


@router.patch("/preferences", response_model=UserPreferencesResponse)
async def update_user_preferences(
    payload: UpdateUserPreferencesRequest,
    user: UserModel = Depends(get_current_user),
):
    theme = payload.theme
    user_id = user.id
    updated = update_user_theme(user_id, theme)
    if not updated:
        raise HTTPException(
            status_code=404, detail="Failed to updated user preferences"
        )
    return UserPreferencesResponse(theme=theme)


@router.delete("/delete", response_model=DeleteUserResponse)
async def delete_user(
    user: UserModel = Depends(get_current_user),
    _=Depends(require_privileged_mode),
):
    """Delete user account and all associated data."""
    user_id = user.id

    workspaces_of_user = get_workspaces_by_user_id(user_id)
    journals_of_user = []
    entries_of_user = []
    media_of_user = []
    for workspace in workspaces_of_user:
        journals_in_workspace = get_journals_by_workspace_id(workspace.id)
        journals_of_user.extend(journals_in_workspace)
        for journal in journals_in_workspace:
            entries_in_journal = get_entries_by_journal_id(journal.id)
            entries_of_user.extend(entries_in_journal)
            for entry in entries_in_journal:
                media_in_entry = get_media_by_entry_id(entry.id)
                media_of_user.extend(media_in_entry)

    for media in media_of_user:
        delete_media_by_id(media.id)
    for entry in entries_of_user:
        delete_entry_by_id(entry.id)
    for journal in journals_of_user:
        delete_journal_by_id(journal.id)
    for workspace in workspaces_of_user:
        delete_workspace_by_id(workspace.id)

    # Delete user's media directory if it exists
    user_media_dir = os.path.join(MEDIA_PATH, str(user_id))
    if os.path.exists(user_media_dir):
        shutil.rmtree(user_media_dir)

    delete_user_by_id(user_id)

    return DeleteUserResponse(
        status="success", message="Account and all data deleted successfully"
    )


@router.post(
    "/register-with-import", response_model=RegisterWithImportResponse, status_code=201
)
async def register_with_import(
    hashkey: str = Form(...),
    file: UploadFile = File(...),
):
    """Recreate a user from encrypted dump and import all data."""
    # Read dump file
    content = await file.read()

    # Extract unencrypted meta to get the source user_id for key derivation
    meta = read_dump_meta(content)
    if meta is None:
        raise HTTPException(
            400,
            "Unrecognised dump format. This may be a legacy dump created before version 1.0.",
        )

    source_user_id = meta.get("user_id")
    if not source_user_id:
        raise HTTPException(400, "Dump meta is missing user_id.")

    fernet_key = derive_dump_key(hashkey, source_user_id)
    data = read_encrypted_dump(content, fernet_key)

    if data is None:
        raise HTTPException(
            400, "Failed to decrypt dump. Invalid hashkey or corrupted file."
        )

    valid, msg = validate_dump_structure(data)
    if not valid:
        raise HTTPException(400, f"Invalid dump structure: {msg}")

    dump_username = data.get("username")
    dump_password_hash = data.get("password_hash")
    dump_hashkey_hash = data.get("hashkey_hash")

    if not dump_username or not isinstance(dump_username, str):
        raise HTTPException(
            400,
            "Dump does not contain username. Re-export data with a newer version.",
        )

    if not dump_password_hash or not isinstance(dump_password_hash, str):
        raise HTTPException(
            400,
            "Dump does not contain password hash. Re-export data with a newer version.",
        )

    existing = await db["users"].find_one({"username": dump_username})
    if existing:
        raise HTTPException(status_code=409, detail="Username from dump already exists")

    # Create user
    user_doc = {
        "username": dump_username,
        "password_hash": dump_password_hash,
        "hashkey_hash": dump_hashkey_hash or hash_secret(secrets.token_hex(32)),
        "theme": normalize_theme(data.get("theme")),
    }
    result = await db["users"].insert_one(user_doc)
    user_id = str(result.inserted_id)

    # Derive and store the dump encryption key for future exports
    new_dump_key = derive_dump_key(hashkey, user_id)
    await db["users"].update_one(
        {"_id": result.inserted_id}, {"$set": {"dump_key": new_dump_key}}
    )

    # Import the data using the shared utility
    import_result = await import_dump_data(data, user_id, db)

    token = create_access_token(user_id, dump_username)

    return RegisterWithImportResponse(
        username=dump_username,
        access_token=token,
        import_result=ImportResult(
            status=import_result.status,
            workspaces_imported=import_result.workspaces_imported,
            journals_imported=import_result.journals_imported,
            entries_imported=import_result.entries_imported,
            entry_types_imported=import_result.entry_types_imported,
            skipped=import_result.skipped,
        ),
    )
